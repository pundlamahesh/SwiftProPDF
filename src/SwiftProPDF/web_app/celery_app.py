import os

from celery import Celery

ASYNC_WORKER_CONCURRENCY_ENV = "SWIFTPROPDF_ASYNC_WORKER_CONCURRENCY"
DEFAULT_ASYNC_WORKER_CONCURRENCY = 2


def redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://redis:6379/0")


def worker_concurrency() -> int:
    configured = os.getenv(
        ASYNC_WORKER_CONCURRENCY_ENV,
        str(DEFAULT_ASYNC_WORKER_CONCURRENCY),
    )
    try:
        value = int(configured)
    except ValueError as exc:
        raise ValueError(f"{ASYNC_WORKER_CONCURRENCY_ENV} must be a positive integer.") from exc
    if value < 1:
        raise ValueError(f"{ASYNC_WORKER_CONCURRENCY_ENV} must be a positive integer.")
    return value


celery_app = Celery(
    "SwiftProPDF",
    broker=redis_url(),
    backend=os.getenv("CELERY_RESULT_BACKEND", redis_url()),
    include=["SwiftProPDF.web_app.tasks"],
)

celery_app.conf.update(
    result_expires=int(os.getenv("SWIFTPROPDF_JOB_RESULT_EXPIRES", "86400")),
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_concurrency=worker_concurrency(),
)
