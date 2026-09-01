from datetime import timedelta

from fastapi.testclient import TestClient

from distributed_compute.computations import execute
from distributed_compute.coordinator import InMemoryCoordinator, create_app
from distributed_compute.models import utc_now


TOKEN = "test-secret"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}


def worker_payload(worker_id: str) -> dict:
    return {
        "worker_id": worker_id,
        "device_name": f"device-{worker_id}",
        "node": f"node-{worker_id}",
        "os_name": "TestOS",
        "os_release": "1",
        "logical_cpu_cores": 4,
        "available_ram_bytes": 1_000_000,
        "cpu_usage_percent": 10,
        "benchmark": {
            "elapsed_seconds": 0.1,
            "operations": 1000,
            "operations_per_second": 10_000,
        },
    }


def claim_payload(worker_id: str) -> dict:
    return {
        "worker_id": worker_id,
        "logical_cpu_cores": 4,
        "available_ram_bytes": 900_000,
        "cpu_usage_percent": 20,
    }


def register(client: TestClient, worker_id: str) -> None:
    response = client.post("/api/v1/workers/register", headers=HEADERS, json=worker_payload(worker_id))
    assert response.status_code == 200


def test_authentication_and_registration() -> None:
    with TestClient(create_app(api_token=TOKEN)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/workers").status_code == 401
        register(client, "worker-1")
        workers = client.get("/api/v1/workers", headers=HEADERS).json()
        assert workers[0]["worker_id"] == "worker-1"
        assert workers[0]["online"] is True


def test_sum_squares_job_runs_across_multiple_workers() -> None:
    with TestClient(create_app(api_token=TOKEN)) as client:
        register(client, "worker-1")
        register(client, "worker-2")
        created = client.post(
            "/api/v1/jobs",
            headers=HEADERS,
            json={"job_type": "sum_squares", "start": 1, "end": 101, "chunk_size": 17},
        )
        assert created.status_code == 201
        job = created.json()
        assert job["total_tasks"] == 6

        used_workers = set()
        index = 0
        while True:
            worker_id = f"worker-{index % 2 + 1}"
            claimed = client.post("/api/v1/tasks/claim", headers=HEADERS, json=claim_payload(worker_id)).json()["task"]
            if claimed is None:
                break
            used_workers.add(worker_id)
            result = execute(claimed["job_type"], claimed["start"], claimed["end"])
            completed = client.post(
                f"/api/v1/tasks/{claimed['task_id']}/complete",
                headers=HEADERS,
                json={"worker_id": worker_id, "result": result},
            )
            assert completed.status_code == 200
            index += 1

        finished = client.get(f"/api/v1/jobs/{job['job_id']}", headers=HEADERS).json()
        assert used_workers == {"worker-1", "worker-2"}
        assert finished["status"] == "completed"
        assert finished["result"] == execute("sum_squares", 1, 101)


def test_prime_count_job_and_idempotent_completion() -> None:
    with TestClient(create_app(api_token=TOKEN)) as client:
        register(client, "worker-1")
        job = client.post(
            "/api/v1/jobs",
            headers=HEADERS,
            json={"job_type": "prime_count", "start": 0, "end": 100, "chunk_size": 100},
        ).json()
        task = client.post("/api/v1/tasks/claim", headers=HEADERS, json=claim_payload("worker-1")).json()["task"]
        result = execute("prime_count", task["start"], task["end"])
        body = {"worker_id": "worker-1", "result": result}
        assert client.post(f"/api/v1/tasks/{task['task_id']}/complete", headers=HEADERS, json=body).status_code == 200
        duplicate = client.post(f"/api/v1/tasks/{task['task_id']}/complete", headers=HEADERS, json=body)
        assert duplicate.status_code == 200
        assert client.get(f"/api/v1/jobs/{job['job_id']}", headers=HEADERS).json()["result"] == 25


def test_failure_retries_then_fails_job() -> None:
    store = InMemoryCoordinator(max_attempts=2)
    with TestClient(create_app(api_token=TOKEN, store=store)) as client:
        register(client, "worker-1")
        job = client.post(
            "/api/v1/jobs",
            headers=HEADERS,
            json={"job_type": "prime_count", "start": 0, "end": 10, "chunk_size": 10},
        ).json()
        for attempt in (1, 2):
            task = client.post("/api/v1/tasks/claim", headers=HEADERS, json=claim_payload("worker-1")).json()["task"]
            assert task["attempt"] == attempt
            response = client.post(
                f"/api/v1/tasks/{task['task_id']}/fail",
                headers=HEADERS,
                json={"worker_id": "worker-1", "error": "test failure"},
            )
            assert response.status_code == 200
        failed = client.get(f"/api/v1/jobs/{job['job_id']}", headers=HEADERS).json()
        assert failed["status"] == "failed"
        assert failed["failed_tasks"] == 1


def test_expired_lease_is_reassigned() -> None:
    store = InMemoryCoordinator(max_attempts=3)
    with TestClient(create_app(api_token=TOKEN, store=store)) as client:
        register(client, "worker-1")
        register(client, "worker-2")
        client.post(
            "/api/v1/jobs",
            headers=HEADERS,
            json={"job_type": "sum_squares", "start": 1, "end": 5, "chunk_size": 4},
        )
        first = client.post("/api/v1/tasks/claim", headers=HEADERS, json=claim_payload("worker-1")).json()["task"]
        store.tasks[first["task_id"]].lease_expires_at = utc_now() - timedelta(seconds=1)
        second = client.post("/api/v1/tasks/claim", headers=HEADERS, json=claim_payload("worker-2")).json()["task"]
        assert second["task_id"] == first["task_id"]
        assert second["attempt"] == 2


def test_heartbeat_renews_active_task_lease() -> None:
    store = InMemoryCoordinator(lease_seconds=30)
    with TestClient(create_app(api_token=TOKEN, store=store)) as client:
        register(client, "worker-1")
        client.post(
            "/api/v1/jobs",
            headers=HEADERS,
            json={"job_type": "sum_squares", "start": 1, "end": 5, "chunk_size": 4},
        )
        task = client.post("/api/v1/tasks/claim", headers=HEADERS, json=claim_payload("worker-1")).json()["task"]
        old_expiry = store.tasks[task["task_id"]].lease_expires_at
        response = client.post(
            "/api/v1/workers/worker-1/heartbeat",
            headers=HEADERS,
            json={
                "logical_cpu_cores": 4,
                "available_ram_bytes": 800_000,
                "cpu_usage_percent": 30,
            },
        )
        assert response.status_code == 200
        assert store.tasks[task["task_id"]].lease_expires_at > old_expiry


def test_job_validation() -> None:
    with TestClient(create_app(api_token=TOKEN)) as client:
        invalid = client.post(
            "/api/v1/jobs",
            headers=HEADERS,
            json={"job_type": "sum_squares", "start": 10, "end": 1, "chunk_size": 1},
        )
        assert invalid.status_code == 422
