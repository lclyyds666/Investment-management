"""法务钉钉失败投递补偿命令。"""
from app.db.session import SessionLocal
from app.services.legal_alerts import dispatch_pending_deliveries


def main() -> int:
    with SessionLocal() as db:
        try:
            processed = dispatch_pending_deliveries(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
    print(f"deliveries_processed={processed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
