import unittest
from decimal import Decimal
from types import SimpleNamespace

from app.models.scenic_config import ScenicConfig
from app.schemas.scenic_config import ScenicConfigUpdate
from app.services.scenic_config import get_effective_config


class ScenicConfigTest(unittest.TestCase):
    def test_orm_uses_existing_production_rate_columns(self):
        self.assertEqual(ScenicConfig.ticket_rate_hexiao.property.columns[0].name, "rate_hexiao")
        self.assertEqual(ScenicConfig.ticket_rate_settle.property.columns[0].name, "rate_settle")
        self.assertEqual(
            ScenicConfig.ticket_commission_rate.property.columns[0].name,
            "commission_rate",
        )

    def test_target_scenic_fallbacks_match_initial_configuration(self):
        zunyi = get_effective_config(None, "zunyi-zoo")
        self.assertEqual(zunyi.default_ticket_product, "遵义动物园")
        self.assertEqual(zunyi.ticket_rate_hexiao, Decimal("0.84"))
        self.assertEqual(zunyi.ticket_rate_settle, Decimal("0.87"))
        self.assertEqual(zunyi.ticket_commission_rate, Decimal("0"))
        self.assertEqual(zunyi.ticket_default_commission, Decimal("0"))

        nanyang = get_effective_config(None, "nanyang-wildlife")
        self.assertEqual(nanyang.default_ticket_product, "南阳森林野生动物世界")
        self.assertEqual(nanyang.ticket_rate_hexiao, Decimal("0.80"))
        self.assertEqual(nanyang.ticket_rate_settle, Decimal("0.85"))

    def test_update_schema_strips_ticket_product(self):
        payload = ScenicConfigUpdate(
            default_ticket_product="  遵义动物园  ",
            ticket_rate_hexiao=Decimal("0.84"),
            ticket_rate_settle=Decimal("0.87"),
            ticket_commission_rate=Decimal("0"),
            ticket_default_commission=Decimal("0"),
        )
        self.assertEqual(payload.default_ticket_product, "遵义动物园")

    def test_persisted_configuration_overrides_seed_defaults(self):
        persisted = SimpleNamespace(
            scenic_id="zunyi-zoo",
            scenic_name="遵义动物园",
            sort_order=40,
            default_ticket_product="遵义动物园夜场票",
            ticket_rate_hexiao=Decimal("0.82"),
            ticket_rate_settle=Decimal("0.86"),
            ticket_commission_rate=Decimal("0.01"),
            ticket_default_commission=Decimal("10"),
            updated_by=7,
            updated_at=None,
        )
        db = SimpleNamespace(get=lambda model, scenic_id: persisted)

        config = get_effective_config(db, "zunyi-zoo")

        self.assertEqual(config.default_ticket_product, "遵义动物园夜场票")
        self.assertEqual(config.ticket_rate_hexiao, Decimal("0.82"))
        self.assertEqual(config.ticket_rate_settle, Decimal("0.86"))
        self.assertEqual(config.ticket_commission_rate, Decimal("0.01"))
        self.assertEqual(config.ticket_default_commission, Decimal("10"))


if __name__ == "__main__":
    unittest.main()
