from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status

from send_to_kindle.auth import AuthenticationError, UserRegistry
from send_to_kindle.dependencies import get_job_store, get_settings, get_user_registry
from send_to_kindle.models import ArticleRequest, JobDetailResponse, JobResponse
from send_to_kindle.repository import JobStore


app = FastAPI(title="Send to Kindle API", version="0.1.0")


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
