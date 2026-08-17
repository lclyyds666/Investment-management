"""清理超过七天仍未确认的法务 Excel 预检数据。"""
from app.db.session import SessionLocal
from app.services.legal_imports import expire_unconfirmed_batches


def main() -> int:
    with SessionLocal() as db:
        try:
            deleted = expire_unconfirmed_batches(db)
            db.commit()
        except Exception:
            db.rollback()
            raise
    print(f"batches_deleted={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
