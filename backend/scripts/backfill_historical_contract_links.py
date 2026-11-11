"""Run after backup/review: python -m scripts.backfill_historical_contract_links.

Default is dry run. --apply commits. Optional --period-selectors JSON is a list
of {scenic_id, source_kind, period_key, selected_by}, based on reviewed evidence.
No selector is invented when this file is absent. No fund records are changed.
"""
import argparse
import json
from pathlib import Path

import app.db.init_db  # noqa: F401
from app.db.session import SessionLocal
from app.services.historical_contract_links import backfill_historical_contract_links


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--period-selectors", type=Path)
    args = parser.parse_args()
    selectors = {}
    if args.period_selectors:
        for row in json.loads(args.period_selectors.read_text(encoding="utf-8")):
            key = (row["scenic_id"], row["source_kind"], row["period_key"])
            if key in selectors:
                raise ValueError(f"Duplicate selector evidence: {key}")
            selectors[key] = int(row["selected_by"])
    with SessionLocal() as db:
        report = backfill_historical_contract_links(db, apply=args.apply, period_selectors=selectors)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
