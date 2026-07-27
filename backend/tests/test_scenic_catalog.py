from __future__ import annotations

import unittest
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.v1.endpoints import scenic as scenic_api
from app.db.base import Base
from app.models.scenic_config import ScenicConfig
from app.schemas.scenic_config import ScenicConfigPutIn


class ScenicCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=[ScenicConfig.__table__])
        self.db = Session(self.engine)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def _add_config(
        self,
        scenic_id: str,
        scenic_name: str,
        *,
        sort_order: int,
        ticket_enabled: bool,
        hotel_enabled: bool,
        enabled: bool = True,
    ) -> ScenicConfig:
        row = ScenicConfig(
            scenic_id=scenic_id,
            scenic_name=scenic_name,
            image_url=f"/scenic/{scenic_id}.jpg",
            ticket_enabled=ticket_enabled,
            hotel_enabled=hotel_enabled,
            sort_order=sort_order,
            rate_hexiao=Decimal("0.9000"),
            rate_settle=Decimal("0.9400"),
            commission_rate=Decimal("0.0600"),
            hotel_fee_algo=1,
            fee_per_night=Decimal("44.00"),
            enabled=enabled,
        )
        self.db.add(row)
        self.db.commit()
        return row

    def test_enabled_scenics_are_listed_with_module_switches(self) -> None:
        self._add_config(
            "test-config-001",
            "测试景区",
            sort_order=20,
            ticket_enabled=True,
            hotel_enabled=False,
        )
        self._add_config(
            "quanzhou-ouleb",
            "泉州欧乐堡",
            sort_order=10,
            ticket_enabled=True,
            hotel_enabled=True,
        )
        self._add_config(
            "disabled-scenic",
            "停用景区",
            sort_order=1,
            ticket_enabled=True,
            hotel_enabled=True,
            enabled=False,
        )

        response = scenic_api.list_scenic_spots(db=self.db, _=None)

        self.assertEqual([row.id for row in response.data], ["quanzhou-ouleb", "test-config-001"])
        self.assertEqual(response.data[0].name, "泉州欧乐堡")
        self.assertEqual(response.data[0].image, "/scenic/quanzhou-ouleb.jpg")
        self.assertTrue(response.data[0].ticket_enabled)
        self.assertTrue(response.data[0].hotel_enabled)
        self.assertTrue(response.data[1].ticket_enabled)
        self.assertFalse(response.data[1].hotel_enabled)

    def test_legacy_config_update_preserves_catalog_fields(self) -> None:
        row = self._add_config(
            "catalog-preserve",
            "原景区名称",
            sort_order=30,
            ticket_enabled=False,
            hotel_enabled=True,
        )
        original_image = row.image_url

        payload = ScenicConfigPutIn(
            scenic_name="更新后景区名称",
            default_ticket_product="成人票",
            default_hotel_name="景区酒店",
            rate_hexiao=Decimal("0.8800"),
            rate_settle=Decimal("0.9100"),
            commission_rate=Decimal("0.0500"),
            hotel_fee_algo=1,
            fee_per_night=Decimal("30.00"),
            enabled=True,
        )
        scenic_api.update_scenic_config(
            "catalog-preserve",
            payload,
            db=self.db,
            _=None,
        )
        self.db.refresh(row)

        self.assertEqual(row.image_url, original_image)
        self.assertFalse(row.ticket_enabled)
        self.assertTrue(row.hotel_enabled)
        self.assertEqual(row.sort_order, 30)
        self.assertEqual(row.rate_hexiao, Decimal("0.8800"))


if __name__ == "__main__":
    unittest.main()
