-- =============================================================
--  模块重构 迁移脚本（2026-07-16）
--  1) biz_customer 增加 social_credit_code（社会信用代码）
--  2) biz_contract 增加 customer_credit_code；contract_type 改自由文本(加宽至 64)
--     并把旧枚举值 payment/business 转成中文文案
--  3) biz_channel 增加 biz_type（文旅业务/其他），历史行回填“文旅业务”
--  说明：information_schema 守卫，可安全重复执行（幂等）。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__add_col`;
DELIMITER $$
CREATE PROCEDURE `__add_col`(IN tbl VARCHAR(64), IN col VARCHAR(64), IN ddl VARCHAR(500))
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

CALL `__add_col`('biz_customer', 'social_credit_code',
     "`social_credit_code` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '统一社会信用代码' AFTER `name`");
CALL `__add_col`('biz_contract', 'customer_credit_code',
     "`customer_credit_code` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '客户统一社会信用代码' AFTER `customer_name`");
CALL `__add_col`('biz_channel', 'biz_type',
     "`biz_type` VARCHAR(16) NOT NULL DEFAULT '文旅业务' COMMENT '业务类型:文旅业务/其他' AFTER `name`");

DROP PROCEDURE IF EXISTS `__add_col`;

-- 合同类型改自由文本：加宽列 + 旧枚举值转中文（幂等：二次执行时已非枚举值，UPDATE 命中 0 行）
ALTER TABLE `biz_contract` MODIFY COLUMN `contract_type` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '合同类型(自由文本)';
UPDATE `biz_contract` SET `contract_type` = '业务付款审批单' WHERE `contract_type` = 'payment';
UPDATE `biz_contract` SET `contract_type` = '业务审批单'     WHERE `contract_type` = 'business';

-- 渠道业务类型历史行回填
UPDATE `biz_channel` SET `biz_type` = '文旅业务' WHERE `biz_type` IS NULL OR `biz_type` = '';

SELECT '模块重构迁移完成（social_credit_code / customer_credit_code / contract_type 文本化 / channel.biz_type）。' AS message;
