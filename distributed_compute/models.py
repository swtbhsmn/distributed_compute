from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobType(str, Enum):
    sum_squares = "sum_squares"
    prime_count = "prime_count"


class Benchmark(BaseModel):
    elapsed_seconds: float = Field(gt=0)
    operations: int = Field(gt=0)
    operations_per_second: float = Field(gt=0)


class ResourceSnapshot(BaseModel):
    logical_cpu_cores: int = Field(ge=1)
    available_ram_bytes: int = Field(ge=0)
    cpu_usage_percent: float = Field(ge=0, le=100)


class WorkerRegistration(ResourceSnapshot):
    worker_id: str = Field(min_length=1, max_length=128)
    device_name: str = Field(min_length=1, max_length=256)
    node: str = Field(min_length=1, max_length=256)
    os_name: str = Field(min_length=1, max_length=128)
    os_release: str = Field(max_length=256)
    benchmark: Benchmark


class Heartbeat(ResourceSnapshot):
    pass


class WorkerView(WorkerRegistration):
    registered_at: datetime
    last_seen: datetime
    online: bool
    current_task_id: str | None = None


class JobCreate(BaseModel):
    job_type: JobType
    start: int
    end: int
    chunk_size: int = Field(default=10_000, gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "JobCreate":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class JobWorkerContribution(BaseModel):
    worker_id: str
    device_name: str
    node: str
    os_name: str
    logical_cpu_cores: int
    claimed_attempts: int
    completed_tasks: int
    active_tasks: int
    failed_attempts: int


class JobView(BaseModel):
    job_id: str
    job_type: JobType
    start: int
    end: int
    chunk_size: int
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    total_tasks: int
    pending_tasks: int
    leased_tasks: int
    completed_tasks: int
    failed_tasks: int
    worker_count: int
    workers: list[JobWorkerContribution]
    result: int | None = None
    error: str | None = None


class ClaimRequest(ResourceSnapshot):
    worker_id: str = Field(min_length=1, max_length=128)


class TaskAssignment(BaseModel):
    task_id: str
    job_id: str
    job_type: JobType
    start: int
    end: int
    attempt: int
    lease_expires_at: datetime


class ClaimResponse(BaseModel):
    task: TaskAssignment | None


class TaskComplete(BaseModel):
    worker_id: str
    result: int


class TaskFailure(BaseModel):
    worker_id: str
    error: str = Field(min_length=1, max_length=2000)


class Message(BaseModel):
    message: str
