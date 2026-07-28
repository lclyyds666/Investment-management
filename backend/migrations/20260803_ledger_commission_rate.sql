-- =============================================================
--  台账·服务商佣金率 迁移脚本（2026-08-03）
--  biz_ticket_ledger / biz_hotel_ledger 新增 commission_rate（服务商佣金率）。
--    仅抖音生效；佣金 = 订单实收 × 佣金率 − 达人 − 团长（逐日累加）。
--    默认 0.0600（= 旧硬编码 6%），历史/现有台账数值完全不变。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。幂等，可重复执行。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__ledger_add_col_if_absent`;
DELIMITER $$
CREATE PROCEDURE `__ledger_add_col_if_absent`(IN tbl VARCHAR(64), IN col VARCHAR(64), IN ddl VARCHAR(500))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = tbl
      AND COLUMN_NAME = col
  ) THEN
    SET @s = CONCAT('ALTER TABLE `', tbl, '` ADD COLUMN ', ddl);
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__ledger_add_col_if_absent`('biz_ticket_ledger', 'commission_rate',
  "`commission_rate` DECIMAL(6,4) NOT NULL DEFAULT 0.0600 COMMENT '服务商佣金率(仅抖音;佣金=订单实收×佣金率−达人−团长)' AFTER `supplier_commission`");

CALL `__ledger_add_col_if_absent`('biz_hotel_ledger', 'commission_rate',
  "`commission_rate` DECIMAL(6,4) NOT NULL DEFAULT 0.0600 COMMENT '服务商佣金率(仅抖音;佣金=订单实收×佣金率−达人−团长)' AFTER `supplier_commission`");

DROP PROCEDURE IF EXISTS `__ledger_add_col_if_absent`;

-- 说明：ADD COLUMN NOT NULL DEFAULT 0.0600 已把存量行 commission_rate 填为默认 6%，
--       与旧硬编码佣金率一致，历史台账数值不变；佣金率仅在下次编辑重算时生效。

SELECT '台账·服务商佣金率 迁移完成（commission_rate 默认 0.06）。' AS message;
