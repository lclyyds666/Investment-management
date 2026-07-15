-- =============================================================
--  合同全生命周期 迁移脚本（2026-07-15）
--  新增：biz_contract 增加 is_internal / subject / currency /
--        payment_terms / attachment_name / attachment_stored 列，
--        支撑新建合同表单、台账导出与合同附件真实上传。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。
--        使用 information_schema 守卫，可安全重复执行（幂等）。
--        角色新增/重命名无需迁移（role 列为 VARCHAR，仅改显示名/加枚举成员）。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__add_col_if_absent`;
DELIMITER $$
CREATE PROCEDURE `__add_col_if_absent`(IN col VARCHAR(64), IN ddl VARCHAR(500))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'biz_contract'
      AND COLUMN_NAME = col
  ) THEN
    SET @s = CONCAT('ALTER TABLE `biz_contract` ADD COLUMN ', ddl);
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__add_col_if_absent`('is_internal',       "`is_internal` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否内部合同' AFTER `business_type`");
CALL `__add_col_if_absent`('subject',           "`subject` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '合同标的' AFTER `is_internal`");
CALL `__add_col_if_absent`('currency',          "`currency` VARCHAR(16) NOT NULL DEFAULT '人民币' COMMENT '币种' AFTER `subject`");
CALL `__add_col_if_absent`('payment_terms',     "`payment_terms` TEXT COMMENT '付款条件' AFTER `currency`");
CALL `__add_col_if_absent`('attachment_name',   "`attachment_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '合同附件原始文件名' AFTER `payment_terms`");
CALL `__add_col_if_absent`('attachment_stored', "`attachment_stored` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '合同附件磁盘存储名' AFTER `attachment_name`");

DROP PROCEDURE IF EXISTS `__add_col_if_absent`;

SELECT '合同全生命周期迁移完成（is_internal/subject/currency/payment_terms/attachment_*）。' AS message;
