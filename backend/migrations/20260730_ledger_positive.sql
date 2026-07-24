-- =============================================================
--  台账·核销率分子 positive_count 迁移脚本（2026-07-30）
--  biz_ticket_ledger / biz_hotel_ledger 各加 positive_count：
--    解析对账明细时统计「订单实收/结算价/结算金额为正数」的订单数，供景区经营卡片
--    核销率 = Σpositive_count ÷ Σorder_count × 100% 计算。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。幂等。
--  ⚠️ 存量台账 positive_count 默认 0，需重新上传对账明细回填才计入核销率。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__ledger_add_positive`;
DELIMITER $$
CREATE PROCEDURE `__ledger_add_positive`(IN tbl VARCHAR(64))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tbl AND COLUMN_NAME = 'positive_count'
  ) THEN
    SET @s = CONCAT('ALTER TABLE `', tbl, '` ADD COLUMN `positive_count` INT NOT NULL DEFAULT 0 COMMENT ''为正数订单数(核销率分子)'' AFTER `order_count`');
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__ledger_add_positive`('biz_ticket_ledger');
CALL `__ledger_add_positive`('biz_hotel_ledger');

DROP PROCEDURE IF EXISTS `__ledger_add_positive`;

SELECT '台账 positive_count 列迁移完成。' AS message;
