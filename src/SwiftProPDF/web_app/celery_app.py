import os

from celery import Celery


def redis_url() -> str:
    return os.getenv("REDIS_URL", "redis://redis:6379/0")


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
)
