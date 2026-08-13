import argparse
import json

from app.db.session import SessionLocal
from app.services.legacy_assignment_migration import migrate_legacy_assignments


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", default="legacy-assignment-migration.json")
    args = parser.parse_args()
    with SessionLocal() as db:
        report = migrate_legacy_assignments(db, dry_run=not args.apply)
    with open(args.report, "w", encoding="utf-8") as stream:
        json.dump(report.model_dump(), stream, ensure_ascii=False, indent=2)
    print(report.model_dump_json(indent=2))
    return 0 if not report.unresolved else 2


if __name__ == "__main__":
    raise SystemExit(main())
