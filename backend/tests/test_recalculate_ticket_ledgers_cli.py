import unittest
from unittest.mock import MagicMock, patch

from scripts import recalculate_ticket_ledgers as cli


class RecalculateTicketLedgersCliTest(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()
        self.items = [MagicMock()]
        self.session_local = patch.object(
            cli, "SessionLocal", return_value=self.session
        )
        self.build = patch.object(
            cli, "build_repair_plan", return_value=self.items
        )
        self.format = patch.object(
            cli, "format_repair_plan", return_value="repair plan"
        )
        self.apply = patch.object(cli, "apply_repair_plan")
        self.session_local.start()
        self.build_mock = self.build.start()
        self.format_mock = self.format.start()
        self.apply_mock = self.apply.start()
        self.addCleanup(patch.stopall)

    def test_dry_run_does_not_apply_or_commit(self):
        result = cli.main([])

        self.assertEqual(result, 0)
        self.apply_mock.assert_not_called()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_called_once()
        self.session.close.assert_called_once()

    def test_apply_commits_once(self):
        result = cli.main(["--apply"])

        self.assertEqual(result, 0)
        self.apply_mock.assert_called_once_with(self.session, self.items)
        self.session.commit.assert_called_once()
        self.session.rollback.assert_not_called()
        self.session.close.assert_called_once()

    def test_plan_failure_rolls_back_and_returns_one(self):
        self.build_mock.side_effect = ValueError("missing source")

        result = cli.main([])

        self.assertEqual(result, 1)
        self.apply_mock.assert_not_called()
        self.session.commit.assert_not_called()
        self.session.rollback.assert_called_once()
        self.session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
