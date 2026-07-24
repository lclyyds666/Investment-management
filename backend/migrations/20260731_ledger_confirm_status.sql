-- =============================================================
--  核销台账·确认函两步流程 迁移脚本（2026-07-31）
--  biz_ticket_ledger / biz_hotel_ledger 各加 confirmed 布尔：
--    两步：业务经办上传确认函→待确认(confirmed=0)；业务复核确认→已确认(confirmed=1)。
--    状态：无 confirm_stored=未确认；有且 confirmed=0=待确认；confirmed=1=已确认。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。幂等。
--  存量已上传确认函的行 confirmed 默认 0(待确认)，需业务复核重新点「确认」。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__ledger_add_confirmed`;
DELIMITER $$
CREATE PROCEDURE `__ledger_add_confirmed`(IN tbl VARCHAR(64))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tbl AND COLUMN_NAME = 'confirmed'
  ) THEN
    SET @s = CONCAT('ALTER TABLE `', tbl, '` ADD COLUMN `confirmed` TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''业务复核是否已确认(1=已确认)'' AFTER `confirm_name`');
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__ledger_add_confirmed`('biz_ticket_ledger');
CALL `__ledger_add_confirmed`('biz_hotel_ledger');

DROP PROCEDURE IF EXISTS `__ledger_add_confirmed`;

SELECT '核销台账确认函两步(confirmed)列迁移完成。' AS message;
