import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import init_db
from app.models.organization import UserAssignment
from app.models.user import User


class DatabaseInitializationTest(unittest.TestCase):
    def test_init_creates_normalized_assignment_for_seeded_legacy_user(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        session_factory = sessionmaker(bind=engine)
        try:
            with (
                patch.object(init_db, "engine", engine),
                patch.object(init_db, "SessionLocal", session_factory),
                patch.object(init_db, "seed_operation"),
                patch.object(init_db, "seed_customers"),
                patch.object(init_db, "seed_channels"),
                patch.object(init_db, "seed_scenic_configs"),
                patch.object(init_db, "seed_channel_data"),
                patch.object(init_db, "seed_invoices"),
            ):
                init_db.init()

            with Session(engine) as db:
                risk_user = db.scalar(select(User).where(User.username == "risk"))
                assignment = db.scalar(
                    select(UserAssignment).where(UserAssignment.user_id == risk_user.id)
                )

                self.assertEqual(
                    assignment.position.code,
                    "investment.duty.supply_risk_review",
                )
                self.assertEqual(assignment.source, "legacy")
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
