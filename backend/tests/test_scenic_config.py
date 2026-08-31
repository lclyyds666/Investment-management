import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from app.api.v1.endpoints import scenic as scenic_endpoint
from app.models.scenic_config import ScenicConfig
from app.schemas.scenic_config import HotelScenicConfigUpdate, ScenicConfigUpdate
from app.services.scenic_config import get_effective_config, list_effective_configs


class _ConfigSession:
    def __init__(self):
        self.row = None

    def get(self, _model, _scenic_id):
        return self.row

    def add(self, row):
        self.row = row

    def commit(self):
        return None

    def refresh(self, _row):
        return None


class _MissingMigrationSession:
    @staticmethod
    def _error():
        return OperationalError(
            "SELECT biz_scenic_config.hotel_rate_hexiao",
            {},
            Exception("Unknown column 'hotel_rate_hexiao'"),
        )

    def get(self, _model, _scenic_id):
        raise self._error()

    def scalars(self, _statement):
        raise self._error()


class ScenicConfigTest(unittest.TestCase):
    def test_orm_uses_existing_production_rate_columns(self):
        self.assertEqual(ScenicConfig.ticket_rate_hexiao.property.columns[0].name, "rate_hexiao")
        self.assertEqual(ScenicConfig.ticket_rate_settle.property.columns[0].name, "rate_settle")
        self.assertEqual(
            ScenicConfig.ticket_commission_rate.property.columns[0].name,
            "commission_rate",
        )

    def test_target_scenic_fallbacks_match_initial_configuration(self):
        fuzhou = get_effective_config(None, "fuzhou-ouleb")
        self.assertEqual(fuzhou.ticket_rate_hexiao, Decimal("0.91"))
        self.assertEqual(fuzhou.ticket_rate_settle, Decimal("0.95"))
        self.assertEqual(fuzhou.ticket_commission_rate, Decimal("0.08"))

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

    def test_hotel_seed_defaults_snapshot_each_scenics_ticket_rates(self):
        expected_rates = {
            "fuzhou-ouleb": ("0.91", "0.95", "0.08"),
            "zunyi-zoo": ("0.84", "0.87", "0"),
            "nanyang-wildlife": ("0.80", "0.85", "0"),
        }

        for scenic_id, expected in expected_rates.items():
            with self.subTest(scenic_id=scenic_id):
                config = get_effective_config(None, scenic_id)
                rates = tuple(Decimal(value) for value in expected)
                self.assertEqual(config.hotel_rate_hexiao, rates[0])
                self.assertEqual(config.hotel_rate_settle, rates[1])
                self.assertEqual(config.hotel_commission_rate, rates[2])
                self.assertEqual(config.hotel_rate_hexiao, config.ticket_rate_hexiao)
                self.assertEqual(config.hotel_rate_settle, config.ticket_rate_settle)
                self.assertEqual(
                    config.hotel_commission_rate,
                    config.ticket_commission_rate,
                )
                self.assertEqual(config.hotel_fee_per_night, Decimal("44"))
                self.assertEqual(config.hotel_fee_algo, 1)
                self.assertEqual(config.hotel_platforms, ("抖音", "美团", "携程"))

        unknown = get_effective_config(None, "unknown-scenic")
        self.assertEqual(unknown.hotel_rate_hexiao, Decimal("0.90"))
        self.assertEqual(unknown.hotel_rate_settle, Decimal("0.94"))
        self.assertEqual(unknown.hotel_commission_rate, Decimal("0.06"))
        self.assertEqual(unknown.hotel_rate_hexiao, unknown.ticket_rate_hexiao)

    def test_persisted_hotel_snapshots_do_not_follow_later_ticket_changes(self):
        for scenic_id in ("fuzhou-ouleb", "zunyi-zoo", "nanyang-wildlife"):
            with self.subTest(scenic_id=scenic_id):
                seed = get_effective_config(None, scenic_id)
                row = SimpleNamespace(
                    **{
                        **seed.__dict__,
                        "ticket_rate_hexiao": seed.ticket_rate_hexiao - Decimal("0.01"),
                        "ticket_rate_settle": seed.ticket_rate_settle - Decimal("0.01"),
                        "ticket_commission_rate": Decimal("0.01"),
                        "hotel_platforms": ",".join(seed.hotel_platforms),
                        "updated_by": 7,
                        "updated_at": None,
                    }
                )
                config = get_effective_config(
                    SimpleNamespace(get=lambda _model, _scenic_id: row),
                    scenic_id,
                )

                self.assertEqual(config.hotel_rate_hexiao, seed.hotel_rate_hexiao)
                self.assertEqual(config.hotel_rate_settle, seed.hotel_rate_settle)
                self.assertEqual(
                    config.hotel_commission_rate,
                    seed.hotel_commission_rate,
                )
                self.assertNotEqual(config.hotel_rate_hexiao, config.ticket_rate_hexiao)

    def test_hotel_migration_only_backfills_new_rate_columns(self):
        migration = (
            Path(__file__).resolve().parents[1]
            / "migrations"
            / "20260828_hotel_config.sql"
        ).read_text(encoding="utf-8")

        expected_backfills = {
            "hotel_rate_hexiao": "rate_hexiao",
            "hotel_rate_settle": "rate_settle",
            "hotel_commission_rate": "commission_rate",
        }
        for hotel_column, ticket_column in expected_backfills.items():
            with self.subTest(hotel_column=hotel_column):
                self.assertIn(
                    f"@has_{hotel_column} = 0",
                    migration,
                )
                self.assertIn(
                    f"SET `{hotel_column}` = `{ticket_column}`",
                    migration,
                )
        self.assertNotIn("COALESCE(`hotel_rate_", migration)

    def test_config_list_endpoint_falls_back_when_hotel_columns_are_missing(self):
        response = scenic_endpoint.get_configs(_MissingMigrationSession(), None)
        configs = response.data

        self.assertEqual(
            [config.scenic_id for config in configs],
            [
                "quancheng-ouleb",
                "quanzhou-ouleb",
                "fuzhou-ouleb",
                "zunyi-zoo",
                "nanyang-wildlife",
                "guanquelou",
            ],
        )
        fuzhou = configs[2]
        self.assertFalse(fuzhou.configured)
        self.assertEqual(fuzhou.hotel_rate_hexiao, Decimal("0.91"))
        self.assertEqual(fuzhou.hotel_platforms, ("抖音", "美团", "携程"))

    def test_list_does_not_hide_non_database_errors(self):
        db = SimpleNamespace(
            scalars=lambda _statement: (_ for _ in ()).throw(RuntimeError("programming bug"))
        )

        with self.assertRaisesRegex(RuntimeError, "programming bug"):
            list_effective_configs(db)

    def test_hotel_update_does_not_hide_missing_migration_error(self):
        payload = HotelScenicConfigUpdate(
            default_hotel_name="郑和海洋酒店",
            hotel_rate_hexiao=Decimal("0.82"),
            hotel_rate_settle=Decimal("0.93"),
            hotel_commission_rate=Decimal("0.05"),
            hotel_fee_per_night=Decimal("52"),
            hotel_fee_algo=2,
            hotel_platforms=["抖音", "携程"],
        )

        with self.assertRaises(OperationalError):
            scenic_endpoint.update_hotel_config(
                "fuzhou-ouleb", payload, _MissingMigrationSession(), SimpleNamespace(id=7)
            )

    def test_hotel_update_schema_normalizes_name_and_platforms(self):
        payload = HotelScenicConfigUpdate(
            default_hotel_name="  郑和海洋酒店  ",
            hotel_rate_hexiao=Decimal("0.82"),
            hotel_rate_settle=Decimal("0.93"),
            hotel_commission_rate=Decimal("0.05"),
            hotel_fee_per_night=Decimal("52"),
            hotel_fee_algo=2,
            hotel_platforms=[" 抖音 ", "携程"],
        )

        self.assertEqual(payload.default_hotel_name, "郑和海洋酒店")
        self.assertEqual(payload.hotel_platforms, ("抖音", "携程"))

        for platforms in ([], ["抖音", "抖音"], ["同程"]):
            with self.subTest(platforms=platforms), self.assertRaises(ValidationError):
                HotelScenicConfigUpdate(
                    default_hotel_name="郑和海洋酒店",
                    hotel_rate_hexiao=Decimal("0.82"),
                    hotel_rate_settle=Decimal("0.93"),
                    hotel_commission_rate=Decimal("0.05"),
                    hotel_fee_per_night=Decimal("52"),
                    hotel_fee_algo=2,
                    hotel_platforms=platforms,
                )

    def test_hotel_update_endpoint_creates_complete_independent_config(self):
        db = _ConfigSession()
        payload = HotelScenicConfigUpdate(
            default_hotel_name="郑和海洋酒店",
            hotel_rate_hexiao=Decimal("0.82"),
            hotel_rate_settle=Decimal("0.93"),
            hotel_commission_rate=Decimal("0.05"),
            hotel_fee_per_night=Decimal("52"),
            hotel_fee_algo=2,
            hotel_platforms=["抖音", "携程"],
        )

        response = scenic_endpoint.update_hotel_config(
            "fuzhou-ouleb", payload, db, SimpleNamespace(id=7)
        )

        self.assertEqual(db.row.ticket_rate_hexiao, Decimal("0.91"))
        self.assertEqual(db.row.hotel_rate_hexiao, Decimal("0.82"))
        self.assertEqual(db.row.hotel_platforms, "抖音,携程")
        self.assertEqual(response.data.hotel_platforms, ("抖音", "携程"))
        self.assertEqual(response.data.updated_by, 7)

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
            default_hotel_name="测试酒店",
            hotel_rate_hexiao=Decimal("0.81"),
            hotel_rate_settle=Decimal("0.92"),
            hotel_commission_rate=Decimal("0.04"),
            hotel_fee_per_night=Decimal("50"),
            hotel_fee_algo=2,
            hotel_platforms="抖音,携程",
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
        self.assertEqual(config.default_hotel_name, "测试酒店")
        self.assertEqual(config.hotel_rate_hexiao, Decimal("0.81"))
        self.assertEqual(config.hotel_platforms, ("抖音", "携程"))


if __name__ == "__main__":
    unittest.main()
