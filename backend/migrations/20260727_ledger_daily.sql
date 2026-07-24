-- =============================================================
--  台账逐日明细持久化 迁移脚本（2026-07-27）
--  biz_ticket_ledger / biz_hotel_ledger 各加 daily_json TEXT：
--    存每天聚合后的到账/实收/达人/团长(/毛额/间夜)，供「编辑台账行改费率/佣金/算法」时
--    仍按天逐日重算再累加(不退回总额×费率)。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。幂等。
--  ⚠️ 存量台账行 daily_json 为空 → 编辑时回退「按总额」重算(period 级)；
--     建议对需要精确逐日的存量期重新上传/保存一次以回填逐日明细。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__ledger_add_col_if_absent2`;
DELIMITER $$
CREATE PROCEDURE `__ledger_add_col_if_absent2`(IN tbl VARCHAR(64), IN col VARCHAR(64), IN ddl VARCHAR(500))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tbl AND COLUMN_NAME = col
  ) THEN
    SET @s = CONCAT('ALTER TABLE `', tbl, '` ADD COLUMN ', ddl);
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__ledger_add_col_if_absent2`('biz_ticket_ledger', 'daily_json',
  "`daily_json` TEXT NULL COMMENT '逐日明细JSON(供逐日重算)' AFTER `rate_fee`");
CALL `__ledger_add_col_if_absent2`('biz_hotel_ledger', 'daily_json',
  "`daily_json` TEXT NULL COMMENT '逐日明细JSON(供逐日重算)' AFTER `order_count`");

DROP PROCEDURE IF EXISTS `__ledger_add_col_if_absent2`;

SELECT '台账逐日明细列 daily_json 迁移完成。' AS message;
