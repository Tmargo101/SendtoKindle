from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from send_to_kindle.auth import UserRegistry
from send_to_kindle.config import Settings
from send_to_kindle.models import ArticleContent, JobRecord, UserRecord
from send_to_kindle.repository import JobStore
from send_to_kindle.services.emailer import DeliveryError, send_epub
from send_to_kindle.services.epub import generate_epub
from send_to_kindle.services.extractor import ExtractionError, extract_article
from send_to_kindle.services.fetcher import (
    FetchError,
    fetch_binary,
    fetch_url,
    fetch_url_in_browser,
    should_retry_in_browser,
)

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, settings: Settings, jobs: JobStore, users: UserRegistry):
        self.settings = settings
        self.jobs = jobs
        self.users = users

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        while stop_event is None or not stop_event.is_set():
            did_work = await self.run_once()
            if not did_work:
                await self._wait_for_next_poll(stop_event)

    async def run_once(self) -> bool:
        job = self.jobs.claim_next_job()
        if job is None:
            await self.cleanup_artifacts()
            return False

        try:
            user = self._resolve_user(job.user_id)
            article, artifact_path = await self._process_job(job, user)
            self.jobs.mark_sent(job.job_id, article.title, str(artifact_path))
            logger.info("job sent", extra={"job_id": job.job_id, "user_id": user.user_id})
        except ProcessingFailure as exc:
            self.jobs.mark_failed(
                job.job_id,
                reason=str(exc),
                transient=exc.transient,
                max_retries=self.settings.worker_max_retries,
                backoff_seconds=self.settings.retry_backoff_seconds,
                normalized_title=exc.normalized_title,
            )
            logger.warning(
                "job failed",
                extra={"job_id": job.job_id, "user_id": job.user_id},
                exc_info=exc,
            )
        return True

    async def create_epub(self, source_url: str) -> tuple[ArticleContent, Path]:
        article: ArticleContent | None = None
        try:
            article = await self._retrieve_article(source_url)
            lead_image = await self._fetch_lead_image(article)
            epub_path = generate_epub(article, self.settings.artifacts_dir, lead_image=lead_image)
            return article, epub_path
        except FetchError as exc:
            raise ProcessingFailure(str(exc), transient=exc.transient) from exc
        except ExtractionError as exc:
            raise ProcessingFailure(str(exc), transient=False) from exc
        except Exception as exc:
            raise ProcessingFailure(
                "Unexpected processing failure",
                transient=True,
                normalized_title=article.title if article else None,
            ) from exc

    async def _retrieve_article(self, source_url: str) -> ArticleContent:
        tried_browser = False
        try:
            fetched_page = await fetch_url(source_url, self.settings)
        except FetchError as exc:
            if should_retry_in_browser(self.settings, status_code=exc.status_code):
                tried_browser = True
                logger.info(
                    "retrying article retrieval in browser",
                    extra={"source_url": source_url, "fallback_reason": f"status_code:{exc.status_code}"},
                )
                fetched_page = await fetch_url_in_browser(source_url, self.settings)
            else:
                raise
        else:
            if should_retry_in_browser(self.settings, page=fetched_page):
                tried_browser = True
                logger.info(
                    "retrying article retrieval in browser",
                    extra={"source_url": source_url, "fallback_reason": "interstitial"},
                )
                fetched_page = await fetch_url_in_browser(source_url, self.settings)

        try:
            return extract_article(fetched_page.html, fetched_page.url)
        except ExtractionError as exc:
            if tried_browser or not self.settings.browser_fetch_enabled:
                raise

            logger.info(
                "retrying article retrieval in browser",
                extra={"source_url": source_url, "fallback_reason": "extraction_failed"},
            )
            browser_page = await fetch_url_in_browser(source_url, self.settings)
            return extract_article(browser_page.html, browser_page.url)

    async def _process_job(self, job: JobRecord, user: UserRecord) -> tuple[ArticleContent, Path]:
        article: ArticleContent | None = None
        try:
            article, epub_path = await self.create_epub(job.source_url)
            await send_epub(self.settings, user, article, epub_path)
            return article, epub_path
        except DeliveryError as exc:
            raise ProcessingFailure(
                str(exc),
                transient=exc.transient,
                normalized_title=article.title if article else job.normalized_title,
            ) from exc
        except Exception as exc:
            raise ProcessingFailure(
                "Unexpected processing failure",
                transient=True,
                normalized_title=article.title if article else job.normalized_title,
            ) from exc

    async def _fetch_lead_image(self, article: ArticleContent) -> Optional[tuple[bytes, str]]:
        if not article.lead_image_url:
            return None
        try:
            return await fetch_binary(article.lead_image_url, self.settings)
        except FetchError:
            logger.info("lead image skipped", extra={"job_id": "-"})
            return None

    async def cleanup_artifacts(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.settings.retention_hours)
        paths = self.jobs.delete_expired_artifacts(cutoff)
        for raw_path in paths:
            path = Path(raw_path)
            if path.exists():
                path.unlink(missing_ok=True)

    async def _wait_for_next_poll(self, stop_event: asyncio.Event | None) -> None:
        if stop_event is None:
            await asyncio.sleep(self.settings.worker_poll_interval_seconds)
            return

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=self.settings.worker_poll_interval_seconds,
            )
        except TimeoutError:
            return

    def _resolve_user(self, user_id: str) -> UserRecord:
        try:
            return self.users.get_user_by_id(user_id)
        except Exception as exc:
            raise ProcessingFailure(f"Unknown user_id {user_id}", transient=False) from exc


class ProcessingFailure(Exception):
    def __init__(self, message: str, transient: bool, normalized_title: str | None = None):
        super().__init__(message)
        self.transient = transient
        self.normalized_title = normalized_title
