"""Delete expired AI conversations in bounded, content-free audited batches."""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime

from app.db.session import SessionLocal
from app.services.ai_conversations import (
    cleanup_expired_conversations,
    preview_expired_conversations,
)

logger = logging.getLogger("app.ai_cleanup")


def run_cleanup(*, dry_run: bool = False) -> int:
    started = time.perf_counter()
    batches = 0
    conversations = 0
    messages = 0
    db = SessionLocal()
    try:
        if dry_run:
            result = preview_expired_conversations(db, now=datetime.now())
            logger.info(
                "ai_retention_cleanup_preview batches=%s conversations=%s messages=%s elapsed_ms=%s",
                1 if result.deleted_conversations else 0,
                result.deleted_conversations,
                result.deleted_messages,
                max(0, round((time.perf_counter() - started) * 1000)),
            )
            return 0

        while True:
            result = cleanup_expired_conversations(db, now=datetime.now())
            if result.deleted_conversations == 0:
                break
            batches += 1
            conversations += result.deleted_conversations
            messages += result.deleted_messages
        logger.info(
            "ai_retention_cleanup_completed batches=%s conversations=%s messages=%s elapsed_ms=%s",
            batches,
            conversations,
            messages,
            max(0, round((time.perf_counter() - started) * 1000)),
        )
        return 0
    except Exception:
        logger.exception(
            "ai_retention_cleanup_failed batches=%s conversations=%s messages=%s elapsed_ms=%s",
            batches,
            conversations,
            messages,
            max(0, round((time.perf_counter() - started) * 1000)),
        )
        return 1
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up expired AI conversations")
    parser.add_argument("--dry-run", action="store_true", help="Count one bounded batch only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    return run_cleanup(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
