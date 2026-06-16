import pytest

from SwiftProPDF.web_app.celery_app import (
    ASYNC_WORKER_CONCURRENCY_ENV,
    DEFAULT_ASYNC_WORKER_CONCURRENCY,
    worker_concurrency,
)


def test_worker_concurrency_defaults_to_two(monkeypatch) -> None:
    monkeypatch.delenv(ASYNC_WORKER_CONCURRENCY_ENV, raising=False)

    assert worker_concurrency() == DEFAULT_ASYNC_WORKER_CONCURRENCY


def test_worker_concurrency_uses_configured_value(monkeypatch) -> None:
    monkeypatch.setenv(ASYNC_WORKER_CONCURRENCY_ENV, "4")

    assert worker_concurrency() == 4


@pytest.mark.parametrize("configured", ["0", "-1", "not-a-number"])
def test_worker_concurrency_requires_positive_integer(
    monkeypatch,
    configured: str,
) -> None:
    monkeypatch.setenv(ASYNC_WORKER_CONCURRENCY_ENV, configured)

    with pytest.raises(ValueError, match=ASYNC_WORKER_CONCURRENCY_ENV):
        worker_concurrency()
