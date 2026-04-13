from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import aiosmtplib

from send_to_kindle.config import Settings
from send_to_kindle.filenames import build_epub_filename
from send_to_kindle.models import ArticleContent, UserRecord


class DeliveryError(Exception):
    def __init__(self, message: str, transient: bool):
        super().__init__(message)
        self.transient = transient


async def send_epub(settings: Settings, user: UserRecord, article: ArticleContent, epub_path: Path) -> None:
    message = EmailMessage()
    message["From"] = settings.smtp_sender
    message["To"] = user.kindle_email
    message["Subject"] = article.title
    message.set_content(
        f"Sent by {settings.app_name}.\n\nTitle: {article.title}\nSource: {article.source_url}\n"
    )

    epub_bytes = epub_path.read_bytes()
    message.add_attachment(
        epub_bytes,
        maintype="application",
        subtype="epub+zip",
        filename=build_epub_filename(article.title),
    )

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
        )
    except (aiosmtplib.SMTPConnectError, aiosmtplib.SMTPServerDisconnected, aiosmtplib.SMTPTimeoutError) as exc:
        raise DeliveryError("SMTP connection failed while sending the EPUB", transient=True) from exc
    except aiosmtplib.SMTPException as exc:
        raise DeliveryError("SMTP rejected the EPUB delivery", transient=False) from exc
