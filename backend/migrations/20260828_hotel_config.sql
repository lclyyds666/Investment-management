-- =============================================================
--  景区酒店独立默认配置（2026-08-28）
--  仅补充配置字段，不修改任何历史酒店台账快照。
-- =============================================================
USE `sd_publish_scm`;

SET @has_default_hotel_name = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'default_hotel_name'
);
SET @add_default_hotel_name = IF(
  @has_default_hotel_name = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `default_hotel_name` VARCHAR(255) NOT NULL DEFAULT ''郑和海洋酒店、宝船酒店、水上酒店、长颈鹿酒店'' COMMENT ''酒店台账默认酒店名称'' AFTER `ticket_default_commission`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_default_hotel_name;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

SET @has_hotel_rate_hexiao = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'hotel_rate_hexiao'
);
SET @add_hotel_rate_hexiao = IF(
  @has_hotel_rate_hexiao = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `hotel_rate_hexiao` DECIMAL(6,4) NOT NULL DEFAULT 0.9000 COMMENT ''酒店默认核销率'' AFTER `default_hotel_name`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_hotel_rate_hexiao;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

SET @has_hotel_rate_settle = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'hotel_rate_settle'
);
SET @add_hotel_rate_settle = IF(
  @has_hotel_rate_settle = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `hotel_rate_settle` DECIMAL(6,4) NOT NULL DEFAULT 0.9400 COMMENT ''酒店默认结算费率'' AFTER `hotel_rate_hexiao`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_hotel_rate_settle;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

SET @has_hotel_commission_rate = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'hotel_commission_rate'
);
SET @add_hotel_commission_rate = IF(
  @has_hotel_commission_rate = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `hotel_commission_rate` DECIMAL(6,4) NOT NULL DEFAULT 0.0600 COMMENT ''酒店默认服务商佣金率'' AFTER `hotel_rate_settle`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_hotel_commission_rate;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

SET @has_hotel_fee_per_night = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'hotel_fee_per_night'
);
SET @add_hotel_fee_per_night = IF(
  @has_hotel_fee_per_night = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `hotel_fee_per_night` DECIMAL(18,2) NOT NULL DEFAULT 44.00 COMMENT ''酒店默认每间夜服务费'' AFTER `hotel_commission_rate`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_hotel_fee_per_night;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

SET @has_hotel_fee_algo = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'hotel_fee_algo'
);
SET @add_hotel_fee_algo = IF(
  @has_hotel_fee_algo = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `hotel_fee_algo` TINYINT NOT NULL DEFAULT 1 COMMENT ''酒店默认服务费算法(1=间夜;2=结算费率)'' AFTER `hotel_fee_per_night`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_hotel_fee_algo;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

SET @has_hotel_platforms = (
  SELECT COUNT(*) FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'biz_scenic_config'
    AND COLUMN_NAME = 'hotel_platforms'
);
SET @add_hotel_platforms = IF(
  @has_hotel_platforms = 0,
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `hotel_platforms` VARCHAR(64) NOT NULL DEFAULT ''抖音,美团,携程'' COMMENT ''酒店启用平台(逗号分隔)'' AFTER `hotel_fee_algo`',
  'SELECT 1'
);
PREPARE scenic_stmt FROM @add_hotel_platforms;
EXECUTE scenic_stmt;
DEALLOCATE PREPARE scenic_stmt;

UPDATE `biz_scenic_config`
SET `default_hotel_name` = CASE
      WHEN `default_hotel_name` IS NULL OR TRIM(`default_hotel_name`) = ''
      THEN '郑和海洋酒店、宝船酒店、水上酒店、长颈鹿酒店'
      ELSE `default_hotel_name`
    END,
    `hotel_rate_hexiao` = COALESCE(`hotel_rate_hexiao`, 0.9000),
    `hotel_rate_settle` = COALESCE(`hotel_rate_settle`, 0.9400),
    `hotel_commission_rate` = COALESCE(`hotel_commission_rate`, 0.0600),
    `hotel_fee_per_night` = COALESCE(`hotel_fee_per_night`, 44.00),
    `hotel_fee_algo` = COALESCE(`hotel_fee_algo`, 1),
    `hotel_platforms` = CASE
      WHEN `hotel_platforms` IS NULL OR TRIM(`hotel_platforms`) = ''
      THEN '抖音,美团,携程'
      ELSE `hotel_platforms`
    END;

SELECT '景区酒店独立配置迁移完成，历史酒店台账未修改。' AS message;
