from __future__ import annotations

import argparse
import asyncio
import hmac
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .models import (
    ClaimRequest,
    ClaimResponse,
    Heartbeat,
    JobCreate,
    JobType,
    JobView,
    JobWorkerContribution,
    Message,
    TaskAssignment,
    TaskComplete,
    TaskFailure,
    WorkerRegistration,
    WorkerView,
    utc_now,
)


@dataclass
class WorkerState:
    registration: WorkerRegistration
    registered_at: datetime
    last_seen: datetime
    current_task_id: str | None = None


@dataclass
class TaskState:
    task_id: str
    job_id: str
    start: int
    end: int
    status: str = "pending"
    attempts: int = 0
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    result: int | None = None
    last_error: str | None = None
    claim_counts: dict[str, int] = field(default_factory=dict)
    failure_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class JobState:
    job_id: str
    request: JobCreate
    created_at: datetime
    task_ids: list[str] = field(default_factory=list)
    status: str = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: int | None = None
    error: str | None = None


class InMemoryCoordinator:
    def __init__(
        self,
        lease_seconds: float = 30.0,
        max_attempts: int = 3,
        worker_timeout_seconds: float = 30.0,
    ) -> None:
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.worker_timeout_seconds = worker_timeout_seconds
        self.workers: dict[str, WorkerState] = {}
        self.jobs: dict[str, JobState] = {}
        self.tasks: dict[str, TaskState] = {}
        self.lock = asyncio.Lock()

    async def register(self, registration: WorkerRegistration) -> WorkerView:
        now = utc_now()
        async with self.lock:
            previous = self.workers.get(registration.worker_id)
            worker = WorkerState(
                registration=registration,
                registered_at=previous.registered_at if previous else now,
                last_seen=now,
                current_task_id=previous.current_task_id if previous else None,
            )
            self.workers[registration.worker_id] = worker
            return self._worker_view(worker, now)

    async def heartbeat(self, worker_id: str, heartbeat: Heartbeat) -> WorkerView:
        now = utc_now()
        async with self.lock:
            worker = self._require_worker(worker_id)
            self._expire_leases(now)
            updated = worker.registration.model_copy(update=heartbeat.model_dump())
            worker.registration = updated
            worker.last_seen = now
            if worker.current_task_id:
                task = self.tasks.get(worker.current_task_id)
                if task and task.status == "leased" and task.worker_id == worker_id:
                    task.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            return self._worker_view(worker, now)

    async def list_workers(self) -> list[WorkerView]:
        now = utc_now()
        async with self.lock:
            self._expire_leases(now)
            return [self._worker_view(worker, now) for worker in self.workers.values()]

    async def create_job(self, request: JobCreate) -> JobView:
        now = utc_now()
        async with self.lock:
            job_id = str(uuid.uuid4())
            job = JobState(job_id=job_id, request=request, created_at=now)
            for chunk_start in range(request.start, request.end, request.chunk_size):
                task_id = str(uuid.uuid4())
                task = TaskState(
                    task_id=task_id,
                    job_id=job_id,
                    start=chunk_start,
                    end=min(chunk_start + request.chunk_size, request.end),
                )
                self.tasks[task_id] = task
                job.task_ids.append(task_id)
            self.jobs[job_id] = job
            return self._job_view(job)

    async def list_jobs(self) -> list[JobView]:
        async with self.lock:
            self._expire_leases(utc_now())
            return [self._job_view(job) for job in self.jobs.values()]

    async def get_job(self, job_id: str) -> JobView:
        async with self.lock:
            self._expire_leases(utc_now())
            return self._job_view(self._require_job(job_id))

    async def claim(self, request: ClaimRequest) -> ClaimResponse:
        now = utc_now()
        async with self.lock:
            worker = self._require_worker(request.worker_id)
            worker.registration = worker.registration.model_copy(
                update={
                    "logical_cpu_cores": request.logical_cpu_cores,
                    "available_ram_bytes": request.available_ram_bytes,
                    "cpu_usage_percent": request.cpu_usage_percent,
                }
            )
            worker.last_seen = now
            self._expire_leases(now)

            if worker.current_task_id:
                current = self.tasks.get(worker.current_task_id)
                if current and current.status == "leased":
                    return ClaimResponse(task=self._assignment(current))
                worker.current_task_id = None

            pending = next(
                (
                    task
                    for task in self.tasks.values()
                    if task.status == "pending"
                    and self.jobs[task.job_id].status not in {"failed", "completed"}
                ),
                None,
            )
            if pending is None:
                return ClaimResponse(task=None)

            pending.status = "leased"
            pending.attempts += 1
            pending.worker_id = request.worker_id
            pending.claim_counts[request.worker_id] = pending.claim_counts.get(request.worker_id, 0) + 1
            pending.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
            worker.current_task_id = pending.task_id
            job = self.jobs[pending.job_id]
            if job.status == "pending":
                job.status = "running"
                if job.started_at is None:
                    job.started_at = now
            return ClaimResponse(task=self._assignment(pending))

    async def complete(self, task_id: str, completion: TaskComplete) -> Message:
        async with self.lock:
            task = self._require_task(task_id)
            if task.status == "completed":
                if task.worker_id == completion.worker_id and task.result == completion.result:
                    return Message(message="result already accepted")
                raise HTTPException(status_code=409, detail="task is already completed")
            self._validate_active_lease(task, completion.worker_id)
            task.status = "completed"
            task.result = completion.result
            task.lease_expires_at = None
            worker = self.workers.get(completion.worker_id)
            if worker and worker.current_task_id == task_id:
                worker.current_task_id = None
                worker.last_seen = utc_now()
            self._refresh_job(self.jobs[task.job_id])
            return Message(message="result accepted")

    async def fail(self, task_id: str, failure: TaskFailure) -> Message:
        async with self.lock:
            task = self._require_task(task_id)
            self._validate_active_lease(task, failure.worker_id)
            task.last_error = failure.error
            task.failure_counts[failure.worker_id] = task.failure_counts.get(failure.worker_id, 0) + 1
            task.lease_expires_at = None
            worker = self.workers.get(failure.worker_id)
            if worker and worker.current_task_id == task_id:
                worker.current_task_id = None
                worker.last_seen = utc_now()
            if task.attempts >= self.max_attempts:
                task.status = "failed"
            else:
                task.status = "pending"
                task.worker_id = None
            self._refresh_job(self.jobs[task.job_id])
            return Message(message="failure recorded")

    def _expire_leases(self, now: datetime) -> None:
        affected_jobs: set[str] = set()
        for task in self.tasks.values():
            if (
                task.status == "leased"
                and task.lease_expires_at is not None
                and task.lease_expires_at <= now
            ):
                if task.worker_id:
                    task.failure_counts[task.worker_id] = task.failure_counts.get(task.worker_id, 0) + 1
                    worker = self.workers.get(task.worker_id)
                    if worker and worker.current_task_id == task.task_id:
                        worker.current_task_id = None
                task.last_error = "task lease expired"
                task.lease_expires_at = None
                if task.attempts >= self.max_attempts:
                    task.status = "failed"
                else:
                    task.status = "pending"
                    task.worker_id = None
                affected_jobs.add(task.job_id)
        for job_id in affected_jobs:
            self._refresh_job(self.jobs[job_id])

    def _refresh_job(self, job: JobState) -> None:
        tasks = [self.tasks[task_id] for task_id in job.task_ids]
        failed = [task for task in tasks if task.status == "failed"]
        if failed:
            job.status = "failed"
            job.error = failed[0].last_error or "task failed"
            job.completed_at = utc_now()
        elif all(task.status == "completed" for task in tasks):
            job.status = "completed"
            job.result = sum(task.result or 0 for task in tasks)
            job.completed_at = utc_now()
        elif any(task.status in {"leased", "completed"} for task in tasks):
            job.status = "running"
        else:
            job.status = "pending"

    def _worker_view(self, worker: WorkerState, now: datetime) -> WorkerView:
        return WorkerView(
            **worker.registration.model_dump(),
            registered_at=worker.registered_at,
            last_seen=worker.last_seen,
            online=(now - worker.last_seen).total_seconds() <= self.worker_timeout_seconds,
            current_task_id=worker.current_task_id,
        )

    def _job_view(self, job: JobState) -> JobView:
        tasks = [self.tasks[task_id] for task_id in job.task_ids]
        counts = {name: sum(task.status == name for task in tasks) for name in ("pending", "leased", "completed", "failed")}
        contribution_data: dict[str, dict[str, int | str]] = {}
        for task in tasks:
            for worker_id, claimed_attempts in task.claim_counts.items():
                worker = self.workers.get(worker_id)
                registration = worker.registration if worker else None
                contribution = contribution_data.setdefault(
                    worker_id,
                    {
                        "worker_id": worker_id,
                        "device_name": registration.device_name if registration else worker_id,
                        "node": registration.node if registration else "unknown",
                        "os_name": registration.os_name if registration else "unknown",
                        "logical_cpu_cores": registration.logical_cpu_cores if registration else 0,
                        "claimed_attempts": 0,
                        "completed_tasks": 0,
                        "active_tasks": 0,
                        "failed_attempts": 0,
                    },
                )
                contribution["claimed_attempts"] = int(contribution["claimed_attempts"]) + claimed_attempts
                contribution["failed_attempts"] = int(contribution["failed_attempts"]) + task.failure_counts.get(worker_id, 0)
                if task.status == "completed" and task.worker_id == worker_id:
                    contribution["completed_tasks"] = int(contribution["completed_tasks"]) + 1
                if task.status == "leased" and task.worker_id == worker_id:
                    contribution["active_tasks"] = int(contribution["active_tasks"]) + 1
        contributions = [JobWorkerContribution.model_validate(data) for data in contribution_data.values()]
        contributions.sort(key=lambda item: (-item.completed_tasks, -item.claimed_attempts, item.device_name.lower()))
        return JobView(
            job_id=job.job_id,
            job_type=job.request.job_type,
            start=job.request.start,
            end=job.request.end,
            chunk_size=job.request.chunk_size,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            total_tasks=len(tasks),
            pending_tasks=counts["pending"],
            leased_tasks=counts["leased"],
            completed_tasks=counts["completed"],
            failed_tasks=counts["failed"],
            worker_count=len(contributions),
            workers=contributions,
            result=job.result,
            error=job.error,
        )

    def _assignment(self, task: TaskState) -> TaskAssignment:
        job = self.jobs[task.job_id]
        assert task.lease_expires_at is not None
        return TaskAssignment(
            task_id=task.task_id,
            job_id=task.job_id,
            job_type=job.request.job_type,
            start=task.start,
            end=task.end,
            attempt=task.attempts,
            lease_expires_at=task.lease_expires_at,
        )

    def _require_worker(self, worker_id: str) -> WorkerState:
        worker = self.workers.get(worker_id)
        if worker is None:
            raise HTTPException(status_code=404, detail="worker is not registered")
        return worker

    def _require_job(self, job_id: str) -> JobState:
        job = self.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    def _require_task(self, task_id: str) -> TaskState:
        task = self.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return task

    @staticmethod
    def _validate_active_lease(task: TaskState, worker_id: str) -> None:
        if task.status != "leased":
            raise HTTPException(status_code=409, detail="task does not have an active lease")
        if task.worker_id != worker_id:
            raise HTTPException(status_code=409, detail="task is leased to another worker")
        if task.lease_expires_at is None or task.lease_expires_at <= utc_now():
            raise HTTPException(status_code=409, detail="task lease has expired")


bearer = HTTPBearer(auto_error=False)


async def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    expected = request.app.state.api_token
    if not credentials or credentials.scheme.lower() != "bearer" or not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def create_app(
    api_token: str | None = None,
    store: InMemoryCoordinator | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    configured_token = api_token if api_token is not None else os.getenv("DISTRIBUTED_COMPUTE_TOKEN", "")
    if cors_origins is None:
        cors_origins = [
            origin.strip()
            for origin in os.getenv(
                "DISTRIBUTED_COMPUTE_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ]

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not configured_token:
            raise RuntimeError("DISTRIBUTED_COMPUTE_TOKEN must be set")
        yield

    application = FastAPI(title="Distributed Compute POC", version="0.1.0", lifespan=lifespan)
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )
    application.state.api_token = configured_token
    application.state.store = store or InMemoryCoordinator()
    protected = [Depends(require_token)]

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/v1/workers/register", response_model=WorkerView, dependencies=protected)
    async def register_worker(body: WorkerRegistration) -> WorkerView:
        return await application.state.store.register(body)

    @application.post("/api/v1/workers/{worker_id}/heartbeat", response_model=WorkerView, dependencies=protected)
    async def heartbeat(worker_id: str, body: Heartbeat) -> WorkerView:
        return await application.state.store.heartbeat(worker_id, body)

    @application.get("/api/v1/workers", response_model=list[WorkerView], dependencies=protected)
    async def list_workers() -> list[WorkerView]:
        return await application.state.store.list_workers()

    @application.post("/api/v1/jobs", response_model=JobView, status_code=201, dependencies=protected)
    async def create_job(body: JobCreate) -> JobView:
        return await application.state.store.create_job(body)

    @application.get("/api/v1/jobs", response_model=list[JobView], dependencies=protected)
    async def list_jobs() -> list[JobView]:
        return await application.state.store.list_jobs()

    @application.get("/api/v1/jobs/{job_id}", response_model=JobView, dependencies=protected)
    async def get_job(job_id: str) -> JobView:
        return await application.state.store.get_job(job_id)

    @application.post("/api/v1/tasks/claim", response_model=ClaimResponse, dependencies=protected)
    async def claim_task(body: ClaimRequest) -> ClaimResponse:
        return await application.state.store.claim(body)

    @application.post("/api/v1/tasks/{task_id}/complete", response_model=Message, dependencies=protected)
    async def complete_task(task_id: str, body: TaskComplete) -> Message:
        return await application.state.store.complete(task_id, body)

    @application.post("/api/v1/tasks/{task_id}/fail", response_model=Message, dependencies=protected)
    async def fail_task(task_id: str, body: TaskFailure) -> Message:
        return await application.state.store.fail(task_id, body)

    return application


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the distributed compute coordinator")
    parser.add_argument("--host", default=os.getenv("COORDINATOR_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("COORDINATOR_PORT", "8000")))
    parser.add_argument("--token", default=os.getenv("DISTRIBUTED_COMPUTE_TOKEN"))
    parser.add_argument(
        "--cors-origin",
        action="append",
        dest="cors_origins",
        help="Allowed dashboard origin; repeat for multiple origins",
    )
    args = parser.parse_args()
    if not args.token:
        parser.error("--token or DISTRIBUTED_COMPUTE_TOKEN is required")
    uvicorn.run(
        create_app(api_token=args.token, cors_origins=args.cors_origins),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
