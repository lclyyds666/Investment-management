-- =============================================================
--  景区酒店核销台账·本期确认函 迁移脚本（2026-07-28）
--  biz_hotel_ledger 加 confirm_stored / confirm_name：
--    每期一份确认函(同期各平台行共享同值)。有确认函→状态=已确认，无→未确认。
--    仅业务复核/信息维护可上传/查看/下载/删除。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。幂等。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__hl_confirm_add_col`;
DELIMITER $$
CREATE PROCEDURE `__hl_confirm_add_col`(IN col VARCHAR(64), IN ddl VARCHAR(500))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'biz_hotel_ledger' AND COLUMN_NAME = col
  ) THEN
    SET @s = CONCAT('ALTER TABLE `biz_hotel_ledger` ADD COLUMN ', ddl);
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__hl_confirm_add_col`('confirm_stored',
  "`confirm_stored` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '确认函磁盘存储名(uuid)' AFTER `daily_json`");
CALL `__hl_confirm_add_col`('confirm_name',
  "`confirm_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '确认函原始文件名' AFTER `confirm_stored`");

DROP PROCEDURE IF EXISTS `__hl_confirm_add_col`;

SELECT '酒店核销台账确认函列 confirm_stored/confirm_name 迁移完成。' AS message;
