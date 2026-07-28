-- =============================================================
--  门票/酒店台账·跟投金额迁移脚本（2026-08-04）
--  两类台账新增 co_investment_amount，历史行统一默认为 0.00。
--  不修改历史付款、核销、结算、服务费或待核销余额。幂等，可重复执行。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__ledger_add_co_investment`;
DELIMITER $$
CREATE PROCEDURE `__ledger_add_co_investment`(IN tbl VARCHAR(64), IN after_col VARCHAR(64))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = tbl
      AND COLUMN_NAME = 'co_investment_amount'
  ) THEN
    SET @s = CONCAT(
      'ALTER TABLE `', tbl,
      '` ADD COLUMN `co_investment_amount` DECIMAL(18,2) NOT NULL DEFAULT 0.00 ',
      'COMMENT ''跟投金额(元)'' AFTER `', after_col, '`'
    );
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__ledger_add_co_investment`('biz_ticket_ledger', 'payment_amount');
CALL `__ledger_add_co_investment`('biz_hotel_ledger', 'payment_amount');

DROP PROCEDURE IF EXISTS `__ledger_add_co_investment`;

SELECT '门票/酒店台账跟投金额列迁移完成，历史值为 0.00。' AS message;
