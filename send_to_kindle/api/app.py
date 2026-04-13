from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from send_to_kindle.auth import AuthenticationError, UserRegistry
from send_to_kindle.dependencies import get_job_store, get_settings, get_user_registry
from send_to_kindle.models import ArticleRequest, JobDetailResponse, JobResponse
from send_to_kindle.repository import JobStore
from send_to_kindle.worker import ProcessingFailure, Worker


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker = Worker(get_settings(), get_job_store(), get_user_registry())
    stop_event = asyncio.Event()
    worker_task = asyncio.create_task(worker.run_forever(stop_event))

    try:
        yield
    finally:
        stop_event.set()
        try:
            await asyncio.wait_for(worker_task, timeout=5)
        except TimeoutError:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
        if worker_task.done() and not worker_task.cancelled():
            exc = worker_task.exception()
            if exc is not None:
                logger.exception("worker task exited with an error", exc_info=exc)


app = FastAPI(title="Send to Kindle API", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/articles", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def enqueue_article(
    payload: ArticleRequest,
    authorization: str | None = Header(default=None),
    users: UserRegistry = Depends(get_user_registry),
    jobs: JobStore = Depends(get_job_store),
) -> JobResponse:
    token = _extract_bearer_token(authorization)
    try:
        user = users.get_user_for_token(token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    job = jobs.enqueue_job(user.user_id, str(payload.url))
    return JobResponse(jobId=job.job_id, status=job.status)


@app.post("/v1/articles/download")
async def download_article(
    payload: ArticleRequest,
    authorization: str | None = Header(default=None),
    users: UserRegistry = Depends(get_user_registry),
) -> FileResponse:
    token = _extract_bearer_token(authorization)
    try:
        users.get_user_for_token(token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    worker = Worker(get_settings(), get_job_store(), users)
    try:
        _, epub_path = await worker.create_epub(str(payload.url))
    except Exception as exc:
        raise _map_processing_exception(exc) from exc

    return FileResponse(
        path=epub_path,
        media_type="application/epub+zip",
        filename=epub_path.name,
        background=BackgroundTask(_delete_file, epub_path),
    )


@app.get("/v1/jobs/{job_id}", response_model=JobDetailResponse)
def get_job(
    job_id: str,
    authorization: str | None = Header(default=None),
    users: UserRegistry = Depends(get_user_registry),
    jobs: JobStore = Depends(get_job_store),
) -> JobDetailResponse:
    token = _extract_bearer_token(authorization)
    try:
        user = users.get_user_for_token(token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if job.user_id != user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return JobDetailResponse(
        jobId=job.job_id,
        status=job.status,
        sourceUrl=job.source_url,
        normalizedTitle=job.normalized_title,
        failureReason=job.failure_reason,
        retryCount=job.retry_count,
        createdAt=job.created_at,
        updatedAt=job.updated_at,
        sentAt=job.sent_at,
    )


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header")
    return token


def _map_processing_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, ProcessingFailure):
        detail = str(exc)
        status_code = status.HTTP_502_BAD_GATEWAY if exc.transient else status.HTTP_422_UNPROCESSABLE_ENTITY
        return HTTPException(status_code=status_code, detail=detail)

    detail = "Unexpected processing failure"
    logger.exception("download endpoint failed", exc_info=exc)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)


def _delete_file(path: Path) -> None:
    path.unlink(missing_ok=True)
