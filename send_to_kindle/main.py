from __future__ import annotations

import argparse
import asyncio

import uvicorn

from send_to_kindle.dependencies import get_job_store, get_settings, get_user_registry
from send_to_kindle.logging import configure_logging
from send_to_kindle.worker import Worker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send to Kindle service")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    api_parser = subparsers.add_parser("api", help="Run the HTTP API")
    api_parser.add_argument("--host", default="0.0.0.0")
    api_parser.add_argument("--port", type=int, default=6122)

    subparsers.add_parser("worker", help="Run the background worker")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level)

    if args.mode == "api":
        uvicorn.run("send_to_kindle.api.app:app", host=args.host, port=args.port)
        return

    worker = Worker(settings, get_job_store(), get_user_registry())
    asyncio.run(worker.run_forever())


if __name__ == "__main__":
    main()
