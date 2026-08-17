"""每日 09:00 法务预警全量扫描命令。"""
from app.db.session import SessionLocal
from app.services.legal_alerts import dispatch_pending_deliveries, scan_alerts


def main() -> int:
    with SessionLocal() as db:
        try:
            result = scan_alerts(db)
            deliveries = dispatch_pending_deliveries(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
    print(
        f"cases={result.cases_scanned} alerts={result.alerts_created} "
        f"deliveries_created={result.deliveries_created} deliveries_processed={deliveries}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
