-- =============================================================
--  景区核销台账通用配置表（方案 A）
--
--  仅新增 biz_scenic_config 并初始化泉州欧乐堡。
--  不修改 biz_ticket_ledger / biz_hotel_ledger，不迁移、不重算历史数据。
--  幂等：可重复执行；已存在的景区配置不会被覆盖。
-- =============================================================

USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `biz_scenic_config` (
  `scenic_id` VARCHAR(64) NOT NULL COMMENT '景区ID(作用域键)',
  `scenic_name` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '景区名称',
  `default_ticket_product` VARCHAR(200) NOT NULL DEFAULT '' COMMENT '门票产品名默认值',
  `default_hotel_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '酒店名称默认值',
  `rate_hexiao` DECIMAL(6,4) NOT NULL DEFAULT 0.9000 COMMENT '景区核销率默认值',
  `rate_settle` DECIMAL(6,4) NOT NULL DEFAULT 0.9400 COMMENT '结算费率默认值',
  `commission_rate` DECIMAL(6,4) NOT NULL DEFAULT 0.0600 COMMENT '服务商佣金率默认值(仅抖音)',
  `hotel_fee_algo` TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT '酒店服务费算法(1=间夜算法;2=结算费率算法)',
  `fee_per_night` DECIMAL(10,2) NOT NULL DEFAULT 44.00 COMMENT '每间夜服务费默认值',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用台账配置',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`scenic_id`),
  CONSTRAINT `chk_scenic_cfg_rate_hexiao` CHECK (`rate_hexiao` >= 0 AND `rate_hexiao` <= 1),
  CONSTRAINT `chk_scenic_cfg_rate_settle` CHECK (`rate_settle` >= 0 AND `rate_settle` <= 1),
  CONSTRAINT `chk_scenic_cfg_commission_rate` CHECK (`commission_rate` >= 0 AND `commission_rate` <= 1),
  CONSTRAINT `chk_scenic_cfg_hotel_fee_algo` CHECK (`hotel_fee_algo` IN (1, 2)),
  CONSTRAINT `chk_scenic_cfg_fee_per_night` CHECK (`fee_per_night` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='景区核销台账默认配置表';

INSERT IGNORE INTO `biz_scenic_config` (
  `scenic_id`,
  `scenic_name`,
  `default_ticket_product`,
  `default_hotel_name`,
  `rate_hexiao`,
  `rate_settle`,
  `commission_rate`,
  `hotel_fee_algo`,
  `fee_per_night`,
  `enabled`
) VALUES (
  'quanzhou-ouleb',
  '泉州欧乐堡',
  '水上世界/童话世界/海洋王国',
  '郑和海洋酒店、宝船酒店、水上酒店、长颈鹿酒店',
  0.9000,
  0.9400,
  0.0600,
  1,
  44.00,
  1
);

SELECT '景区配置表 biz_scenic_config 迁移完成；历史台账未修改。' AS message;
