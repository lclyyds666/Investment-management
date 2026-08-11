"""Dry-run or apply the validated ticket-ledger historical repair plan."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.user import User  # noqa: F401 - registers TicketLedger FK target
from app.services.ticket_ledger_repair import (
    apply_repair_plan,
    build_repair_plan,
    format_repair_plan,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recalculate affected ticket ledgers from retained source workbooks "
            "(dry-run by default)."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the validated plan in one database transaction",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    db = SessionLocal()
    try:
        items = build_repair_plan(db, Path(settings.UPLOAD_DIR))
        report = format_repair_plan(items)
        if report:
            print(report)

        if not args.apply:
            db.rollback()
            print("DRY RUN: no database changes were committed")
            return 0

        apply_repair_plan(db, items)
        db.commit()
        print(f"APPLIED: {len(items)} ticket ledger rows updated")
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
