-- =============================================================
--  景区酒店核销台账·付款日期 迁移脚本（2026-08-02）
--  biz_hotel_ledger 加 payment_date：编辑台账行手工填写，每期各平台共享，落库。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。幂等。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__hl_add_pay_date`;
DELIMITER $$
CREATE PROCEDURE `__hl_add_pay_date`()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'biz_hotel_ledger' AND COLUMN_NAME = 'payment_date'
  ) THEN
    ALTER TABLE `biz_hotel_ledger` ADD COLUMN `payment_date` DATE NULL COMMENT '付款日期(手工,每期共享)' AFTER `payment_amount`;
  END IF;
END$$
DELIMITER ;
CALL `__hl_add_pay_date`();
DROP PROCEDURE IF EXISTS `__hl_add_pay_date`;

SELECT '酒店核销台账付款日期列 payment_date 迁移完成。' AS message;
