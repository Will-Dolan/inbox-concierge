import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    user_id: uuid.UUID | None = None
    status: JobStatus = JobStatus.PENDING
    result: Any = None
    error: str | None = None
    progress: list[dict] = field(default_factory=list)


class LocalQueue:
    """In-process async job queue.

    Same enqueue/get interface an SQS-backed adapter would expose later, so
    callers (routes) don't change when this swaps out for the cloud queue.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def reserve(self, user_id: uuid.UUID | None = None) -> str:
        """Allocate a job id before the work is known, so a closure can push
        progress events under its own job id while it runs (see the rule
        agent's step-by-step activity feed)."""
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = Job(id=job_id, user_id=user_id)
        return job_id

    def start(self, job_id: str, coro_factory: Callable[[], Awaitable[Any]]) -> None:
        job = self._jobs[job_id]

        async def runner() -> None:
            job.status = JobStatus.RUNNING
            try:
                job.result = await coro_factory()
                job.status = JobStatus.DONE
            except Exception as exc:  # noqa: BLE001 - job errors surface via status, not a crash
                job.status = JobStatus.FAILED
                job.error = str(exc)

        asyncio.create_task(runner())

    def enqueue(self, coro_factory: Callable[[], Awaitable[Any]], user_id: uuid.UUID | None = None) -> str:
        job_id = self.reserve(user_id)
        self.start(job_id, coro_factory)
        return job_id

    def push_progress(self, job_id: str, event: dict) -> None:
        job = self._jobs.get(job_id)
        if job is not None:
            job.progress.append(event)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)


queue = LocalQueue()
