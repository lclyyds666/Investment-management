-- =============================================================
--  文旅业务景区默认配置（2026-08-05）
--  仅新增配置表和初始配置，不修改任何历史门票台账。
-- =============================================================
USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `biz_scenic_config` (
  `scenic_id` VARCHAR(64) NOT NULL COMMENT '景区ID(作用域键)',
  `scenic_name` VARCHAR(100) NOT NULL COMMENT '景区名称',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '展示顺序',
  `default_ticket_product` VARCHAR(200) NOT NULL COMMENT '门票台账默认产品名称',
  `ticket_rate_hexiao` DECIMAL(6,4) NOT NULL DEFAULT 0.9000 COMMENT '门票默认核销率',
  `ticket_rate_settle` DECIMAL(6,4) NOT NULL DEFAULT 0.9400 COMMENT '门票默认结算费率',
  `ticket_commission_rate` DECIMAL(6,4) NOT NULL DEFAULT 0.0600 COMMENT '门票默认服务商佣金率',
  `ticket_default_commission` DECIMAL(18,2) NULL COMMENT '门票默认服务商佣金(NULL=按佣金率计算)',
  `updated_by` INT NULL COMMENT '最后修改人',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`scenic_id`),
  KEY `idx_scenic_config_updated_by` (`updated_by`),
  CONSTRAINT `fk_scenic_config_updated_by` FOREIGN KEY (`updated_by`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文旅业务景区默认配置';

INSERT IGNORE INTO `biz_scenic_config`
  (`scenic_id`, `scenic_name`, `sort_order`, `default_ticket_product`,
   `ticket_rate_hexiao`, `ticket_rate_settle`, `ticket_commission_rate`, `ticket_default_commission`)
VALUES
  ('quancheng-ouleb', '泉城欧乐堡', 10, '水上世界/童话世界/海洋王国', 0.9000, 0.9400, 0.0600, NULL),
  ('quanzhou-ouleb', '泉州欧乐堡', 20, '水上世界/童话世界/海洋王国', 0.9000, 0.9400, 0.0600, NULL),
  ('fuzhou-ouleb', '福州欧乐堡', 30, '水上世界/童话世界/海洋王国', 0.9000, 0.9400, 0.0600, NULL),
  ('zunyi-zoo', '遵义动物园', 40, '遵义动物园', 0.8400, 0.8700, 0.0000, 0.00),
  ('nanyang-wildlife', '南阳森林野生动物世界', 50, '南阳森林野生动物世界', 0.8000, 0.8500, 0.0000, 0.00),
  ('guanquelou', '鹳雀楼', 60, '水上世界/童话世界/海洋王国', 0.9000, 0.9400, 0.0600, NULL);

SELECT '景区默认配置表迁移完成，历史门票台账未修改。' AS message;
