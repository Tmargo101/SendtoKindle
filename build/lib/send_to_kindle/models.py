from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl

JobStatus = Literal["queued", "processing", "sent", "failed"]


class ArticleRequest(BaseModel):
    url: HttpUrl


class JobResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    status: JobStatus

    model_config = {"populate_by_name": True}


class JobDetailResponse(BaseModel):
    job_id: str = Field(alias="jobId")
    status: JobStatus
    source_url: str = Field(alias="sourceUrl")
    normalized_title: Optional[str] = Field(default=None, alias="normalizedTitle")
    failure_reason: Optional[str] = Field(default=None, alias="failureReason")
    retry_count: int = Field(alias="retryCount")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    sent_at: Optional[datetime] = Field(default=None, alias="sentAt")

    model_config = {"populate_by_name": True}


@dataclass(slots=True)
class UserRecord:
    user_id: str
    token_hash: str
    kindle_email: str
    display_name: Optional[str] = None


@dataclass(slots=True)
class ArticleContent:
    source_url: str
    title: str
    author: Optional[str]
    site_name: Optional[str]
    published_at: Optional[str]
    content_html: str
    lead_image_url: Optional[str]


@dataclass(slots=True)
class JobRecord:
    job_id: str
    user_id: str
    source_url: str
    status: JobStatus
    normalized_title: Optional[str]
    failure_reason: Optional[str]
    retry_count: int
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime]
    artifact_path: Optional[str]
    next_attempt_at: datetime
    last_error_is_transient: bool
