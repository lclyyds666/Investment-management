-- =============================================================
--  文旅业务景区默认配置（2026-08-05）
--  仅新增配置表和初始配置，不修改任何历史门票台账。
-- =============================================================
USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `biz_scenic_config` (
  `scenic_id` VARCHAR(64) NOT NULL COMMENT '景区ID(作用域键)',
  `scenic_name` VARCHAR(128) NOT NULL COMMENT '景区名称',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '展示顺序',
  `default_ticket_product` VARCHAR(200) NOT NULL COMMENT '门票台账默认产品名称',
  `rate_hexiao` DECIMAL(6,4) NOT NULL DEFAULT 0.9000 COMMENT '门票默认核销率',
  `rate_settle` DECIMAL(6,4) NOT NULL DEFAULT 0.9400 COMMENT '门票默认结算费率',
  `commission_rate` DECIMAL(6,4) NOT NULL DEFAULT 0.0600 COMMENT '门票默认服务商佣金率',
  `ticket_default_commission` DECIMAL(18,2) NULL COMMENT '门票默认服务商佣金(NULL=按佣金率计算)',
  `updated_by` INT NULL COMMENT '最后修改人',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`scenic_id`),
  KEY `idx_scenic_config_updated_by` (`updated_by`),
  CONSTRAINT `fk_scenic_config_updated_by` FOREIGN KEY (`updated_by`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文旅业务景区默认配置';

-- 兼容生产环境已有的通用景区配置表：仅补充本次新增字段，不改动已有列和数据。
SET @has_ticket_default_commission = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'ticket_default_commission'
);
SET @add_ticket_default_commission = IF(
  @has_ticket_default_commission = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `ticket_default_commission` DECIMAL(18,2) NULL COMMENT ''门票默认服务商佣金(NULL=按佣金率计算)'' AFTER `commission_rate`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_ticket_default_commission;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

SET @has_updated_by = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'updated_by'
);
SET @add_updated_by = IF(
  @has_updated_by = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `updated_by` INT NULL COMMENT ''最后修改人'' AFTER `ticket_default_commission`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_updated_by;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

INSERT IGNORE INTO `biz_scenic_config`
  (`scenic_id`, `scenic_name`, `sort_order`, `default_ticket_product`,
   `rate_hexiao`, `rate_settle`, `commission_rate`, `ticket_default_commission`)
VALUES
  ('quancheng-ouleb', '泉城欧乐堡', 10, '水上世界/童话世界/海洋王国', 0.9000, 0.9400, 0.0600, NULL),
  ('quanzhou-ouleb', '泉州欧乐堡', 20, '水上世界/童话世界/海洋王国', 0.9000, 0.9400, 0.0600, NULL),
  ('fuzhou-ouleb', '福州欧乐堡', 30, '水上世界/童话世界/海洋王国', 0.9000, 0.9400, 0.0600, NULL),
  ('zunyi-zoo', '遵义动物园', 40, '遵义动物园', 0.8400, 0.8700, 0.0000, 0.00),
  ('nanyang-wildlife', '南阳森林野生动物世界', 50, '南阳森林野生动物世界', 0.8000, 0.8500, 0.0000, 0.00),
  ('guanquelou', '鹳雀楼', 60, '水上世界/童话世界/海洋王国', 0.9000, 0.9400, 0.0600, NULL);

-- 已有生产行仅在仍为旧默认状态时初始化；后续前端修改后再次执行不会覆盖。
UPDATE `biz_scenic_config`
SET `default_ticket_product` = '遵义动物园',
    `rate_hexiao` = 0.8400,
    `rate_settle` = 0.8700,
    `commission_rate` = 0.0000,
    `ticket_default_commission` = 0.00
WHERE `scenic_id` = 'zunyi-zoo'
  AND `default_ticket_product` = ''
  AND `rate_hexiao` = 0.9000
  AND `rate_settle` = 0.9400
  AND `commission_rate` = 0.0600
  AND `ticket_default_commission` IS NULL;

UPDATE `biz_scenic_config`
SET `default_ticket_product` = '南阳森林野生动物世界',
    `rate_hexiao` = 0.8000,
    `rate_settle` = 0.8500,
    `commission_rate` = 0.0000,
    `ticket_default_commission` = 0.00
WHERE `scenic_id` = 'nanyang-wildlife'
  AND `default_ticket_product` = ''
  AND `rate_hexiao` = 0.9000
  AND `rate_settle` = 0.9400
  AND `commission_rate` = 0.0600
  AND `ticket_default_commission` IS NULL;

UPDATE `biz_scenic_config`
SET `default_ticket_product` = '水上世界/童话世界/海洋王国'
WHERE `default_ticket_product` = ''
  AND `scenic_id` NOT IN ('zunyi-zoo', 'nanyang-wildlife');

SELECT '景区默认配置表迁移完成，历史门票台账未修改。' AS message;
