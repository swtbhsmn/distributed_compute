from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .computations import execute
from .models import Benchmark
from .resources import os_name, resource_backend, resource_snapshot


DEFAULT_STATE_PATH = Path.home() / ".distributed-compute" / "worker-state.json"


def run_benchmark(operations: int = 300_000) -> Benchmark:
    """Run a small integer workload and return a simple, comparable score."""
    started = time.perf_counter()
    accumulator = 0
    for number in range(1, operations + 1):
        accumulator = (accumulator + number * number) % 1_000_000_007
    elapsed = max(time.perf_counter() - started, 1e-9)
    if accumulator < 0:  # Keeps the loop result observable without affecting timing.
        raise AssertionError("unreachable")
    return Benchmark(
        elapsed_seconds=elapsed,
        operations=operations,
        operations_per_second=operations / elapsed,
    )


def load_or_create_state(path: Path) -> tuple[str, Benchmark]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data["worker_id"]), Benchmark.model_validate(data["benchmark"])
    except (FileNotFoundError, KeyError, ValueError, TypeError, json.JSONDecodeError):
        worker_id = str(uuid.uuid4())
        benchmark = run_benchmark()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {"worker_id": worker_id, "benchmark": benchmark.model_dump()},
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
        return worker_id, benchmark


@dataclass(frozen=True)
class WorkerConfig:
    coordinator_url: str
    token: str
    poll_interval: float = 2.0
    request_timeout: float = 15.0
    heartbeat_interval: float = 10.0
    state_path: Path = DEFAULT_STATE_PATH
    device_name: str | None = None


class ComputeWorker:
    def __init__(self, config: WorkerConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.worker_id, self.benchmark = load_or_create_state(config.state_path)
        self.node = platform.node() or socket.gethostname() or "unknown-node"
        self.device_name = config.device_name or self.node
        self.client = client or httpx.Client(
            base_url=config.coordinator_url.rstrip("/"),
            headers={"Authorization": f"Bearer {config.token}"},
            timeout=config.request_timeout,
        )
        self._owns_client = client is None

    def registration_payload(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "device_name": self.device_name,
            "node": self.node,
            "os_name": os_name(),
            "os_release": platform.release(),
            "benchmark": self.benchmark.model_dump(),
            **resource_snapshot(),
        }

    def register(self) -> None:
        response = self.client.post("/api/v1/workers/register", json=self.registration_payload())
        response.raise_for_status()

    def claim(self) -> dict[str, Any] | None:
        response = self.client.post(
            "/api/v1/tasks/claim",
            json={"worker_id": self.worker_id, **resource_snapshot()},
        )
        response.raise_for_status()
        return response.json()["task"]

    def heartbeat(self) -> None:
        response = self.client.post(
            f"/api/v1/workers/{self.worker_id}/heartbeat",
            json=resource_snapshot(),
        )
        response.raise_for_status()

    def process_task(self, task: dict[str, Any]) -> int:
        return execute(task["job_type"], int(task["start"]), int(task["end"]))

    def process_task_with_heartbeats(self, task: dict[str, Any]) -> int:
        stopped = threading.Event()

        def keep_lease_alive() -> None:
            while not stopped.wait(self.config.heartbeat_interval):
                try:
                    self.heartbeat()
                except httpx.HTTPError as exc:
                    print(f"Heartbeat failed while task is running: {exc}", flush=True)

        thread = threading.Thread(target=keep_lease_alive, name="worker-heartbeat", daemon=True)
        thread.start()
        try:
            return self.process_task(task)
        finally:
            stopped.set()
            thread.join(timeout=self.config.request_timeout + 1)

    def complete(self, task_id: str, result: int) -> None:
        response = self.client.post(
            f"/api/v1/tasks/{task_id}/complete",
            json={"worker_id": self.worker_id, "result": result},
        )
        response.raise_for_status()

    def report_failure(self, task_id: str, error: str) -> None:
        response = self.client.post(
            f"/api/v1/tasks/{task_id}/fail",
            json={"worker_id": self.worker_id, "error": error[:2000]},
        )
        response.raise_for_status()

    def run_forever(self) -> None:
        backoff = 1.0
        registered = False
        try:
            while True:
                try:
                    if not registered:
                        self.register()
                        registered = True
                        backoff = 1.0
                        print(
                            f"Registered worker {self.worker_id} as {self.device_name} "
                            f"(resources: {resource_backend()})",
                            flush=True,
                        )

                    task = self.claim()
                    if task is None:
                        time.sleep(self.config.poll_interval)
                        continue

                    task_id = task["task_id"]
                    print(
                        f"Running {task['job_type']} task {task_id}: [{task['start']}, {task['end']})",
                        flush=True,
                    )
                    try:
                        result = self.process_task_with_heartbeats(task)
                    except Exception as exc:
                        self.report_failure(task_id, f"{type(exc).__name__}: {exc}")
                        print(f"Task {task_id} failed: {exc}", flush=True)
                    else:
                        self.complete(task_id, result)
                        print(f"Completed task {task_id}; partial result={result}", flush=True)
                    backoff = 1.0
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        registered = False
                    elif exc.response.status_code in {401, 403}:
                        raise RuntimeError("Coordinator rejected the API token") from exc
                    print(f"Coordinator HTTP error: {exc}; retrying in {backoff:.0f}s", flush=True)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
                except httpx.RequestError as exc:
                    registered = False
                    print(f"Coordinator unavailable: {exc}; retrying in {backoff:.0f}s", flush=True)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
        except KeyboardInterrupt:
            print("Worker stopped", flush=True)
        finally:
            if self._owns_client:
                self.client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a distributed compute worker")
    parser.add_argument(
        "--coordinator",
        default=os.getenv("COORDINATOR_URL", "http://127.0.0.1:8000"),
        help="Coordinator base URL",
    )
    parser.add_argument("--token", default=os.getenv("DISTRIBUTED_COMPUTE_TOKEN"))
    parser.add_argument("--poll-interval", type=float, default=float(os.getenv("WORKER_POLL_INTERVAL", "2")))
    parser.add_argument("--request-timeout", type=float, default=float(os.getenv("WORKER_REQUEST_TIMEOUT", "15")))
    parser.add_argument("--heartbeat-interval", type=float, default=float(os.getenv("WORKER_HEARTBEAT_INTERVAL", "10")))
    parser.add_argument("--state-path", type=Path, default=Path(os.getenv("WORKER_STATE_PATH", DEFAULT_STATE_PATH)))
    parser.add_argument("--name", default=os.getenv("WORKER_DEVICE_NAME"))
    args = parser.parse_args()
    if not args.token:
        parser.error("--token or DISTRIBUTED_COMPUTE_TOKEN is required")
    if args.poll_interval <= 0 or args.request_timeout <= 0 or args.heartbeat_interval <= 0:
        parser.error("poll interval, request timeout, and heartbeat interval must be positive")
    worker = ComputeWorker(
        WorkerConfig(
            coordinator_url=args.coordinator,
            token=args.token,
            poll_interval=args.poll_interval,
            request_timeout=args.request_timeout,
            heartbeat_interval=args.heartbeat_interval,
            state_path=args.state_path,
            device_name=args.name,
        )
    )
    worker.run_forever()


if __name__ == "__main__":
    main()
