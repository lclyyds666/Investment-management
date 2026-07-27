-- 景区动态目录 V1：扩展 biz_scenic_config，并补齐现有景区展示元数据。
-- 不修改 biz_ticket_ledger / biz_hotel_ledger，不变更任何计算参数。

USE `sd_publish_scm`;

SET @schema_name = DATABASE();

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = @schema_name AND table_name = 'biz_scenic_config' AND column_name = 'image_url'
  ),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `image_url` VARCHAR(500) NOT NULL DEFAULT '''' COMMENT ''景区展示图片地址'' AFTER `scenic_name`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = @schema_name AND table_name = 'biz_scenic_config' AND column_name = 'ticket_enabled'
  ),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `ticket_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT ''是否启用门票台账模块'' AFTER `image_url`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = @schema_name AND table_name = 'biz_scenic_config' AND column_name = 'hotel_enabled'
  ),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `hotel_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT ''是否启用酒店台账模块'' AFTER `ticket_enabled`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = @schema_name AND table_name = 'biz_scenic_config' AND column_name = 'sort_order'
  ),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_config` ADD COLUMN `sort_order` INT NOT NULL DEFAULT 0 COMMENT ''景区展示顺序'' AFTER `hotel_enabled`'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = @schema_name AND table_name = 'biz_scenic_config' AND index_name = 'idx_scenic_config_enabled_sort'
  ),
  'SELECT 1',
  'CREATE INDEX `idx_scenic_config_enabled_sort` ON `biz_scenic_config` (`enabled`, `sort_order`)'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

INSERT IGNORE INTO `biz_scenic_config` (
  `scenic_id`, `scenic_name`, `image_url`, `ticket_enabled`, `hotel_enabled`, `sort_order`,
  `default_ticket_product`, `default_hotel_name`, `rate_hexiao`, `rate_settle`,
  `commission_rate`, `hotel_fee_algo`, `fee_per_night`, `enabled`
) VALUES
  ('quancheng-ouleb', '泉城欧乐堡', '/scenic/quancheng-ouleb.png', 0, 1, 10, '', '', 0.9000, 0.9400, 0.0600, 1, 44.00, 1),
  ('quanzhou-ouleb', '泉州欧乐堡', '/scenic/quanzhou-ouleb.jpg', 1, 1, 20, '水上世界/童话世界/海洋王国', '郑和海洋酒店、宝船酒店、水上酒店、长颈鹿酒店', 0.9000, 0.9400, 0.0600, 1, 44.00, 1),
  ('fuzhou-ouleb', '福州欧乐堡', '/scenic/fuzhou-ouleb.jpg', 1, 1, 30, '', '', 0.9000, 0.9400, 0.0600, 1, 44.00, 1),
  ('zunyi-zoo', '遵义动物园', '/scenic/zunyi-zoo.jpg', 1, 0, 40, '', '', 0.9000, 0.9400, 0.0600, 1, 44.00, 1),
  ('nanyang-wildlife', '南阳森林野生动物世界', '/scenic/nanyang-wildlife.jpg', 1, 0, 50, '', '', 0.9000, 0.9400, 0.0600, 1, 44.00, 1),
  ('guanquelou', '鹳雀楼', '/scenic/guanquelou.png', 1, 0, 60, '', '', 0.9000, 0.9400, 0.0600, 1, 44.00, 1);

UPDATE `biz_scenic_config`
SET
  `scenic_name` = IF(`scenic_name` = '', '泉城欧乐堡', `scenic_name`),
  `image_url` = IF(`image_url` = '', '/scenic/quancheng-ouleb.png', `image_url`),
  `ticket_enabled` = 0,
  `hotel_enabled` = 1,
  `sort_order` = 10
WHERE `scenic_id` = 'quancheng-ouleb';

UPDATE `biz_scenic_config`
SET
  `scenic_name` = IF(`scenic_name` = '', '泉州欧乐堡', `scenic_name`),
  `image_url` = IF(`image_url` = '', '/scenic/quanzhou-ouleb.jpg', `image_url`),
  `ticket_enabled` = 1,
  `hotel_enabled` = 1,
  `sort_order` = 20
WHERE `scenic_id` = 'quanzhou-ouleb';

UPDATE `biz_scenic_config`
SET `image_url` = IF(`image_url` = '', CONCAT('/scenic/', `scenic_id`, '.jpg'), `image_url`),
    `ticket_enabled` = 1,
    `hotel_enabled` = IF(`scenic_id` = 'fuzhou-ouleb', 1, 0),
    `sort_order` = CASE `scenic_id`
      WHEN 'fuzhou-ouleb' THEN 30
      WHEN 'zunyi-zoo' THEN 40
      WHEN 'nanyang-wildlife' THEN 50
      WHEN 'guanquelou' THEN 60
      ELSE `sort_order`
    END
WHERE `scenic_id` IN ('fuzhou-ouleb', 'zunyi-zoo', 'nanyang-wildlife', 'guanquelou');

UPDATE `biz_scenic_config`
SET `image_url` = '/scenic/guanquelou.png'
WHERE `scenic_id` = 'guanquelou' AND `image_url` = '/scenic/guanquelou.jpg';

SELECT '景区动态目录 V1 迁移完成；历史门票和酒店台账未修改。' AS message;
