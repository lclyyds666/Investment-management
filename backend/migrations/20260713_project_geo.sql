-- =============================================================
--  项目地理点位 迁移脚本（2026-07-13）
--  新增：biz_project_metrics 增加 city / province / lng / lat 列，
--        用于「数据驱动大屏地图」——上传统计表时从项目名自动解析城市入库。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。
--        使用 information_schema 守卫，可安全重复执行（幂等）。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__add_col_if_absent`;
DELIMITER $$
CREATE PROCEDURE `__add_col_if_absent`(IN col VARCHAR(64), IN ddl VARCHAR(255))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'biz_project_metrics'
      AND COLUMN_NAME = col
  ) THEN
    SET @s = CONCAT('ALTER TABLE `biz_project_metrics` ADD COLUMN ', ddl);
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__add_col_if_absent`('city',     "`city` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '解析出的城市名' AFTER `term_months`");
CALL `__add_col_if_absent`('province', "`province` VARCHAR(50) NOT NULL DEFAULT '' COMMENT '解析出的省/直辖市' AFTER `city`");
CALL `__add_col_if_absent`('lng',      "`lng` DECIMAL(9,5) DEFAULT NULL COMMENT '经度' AFTER `province`");
CALL `__add_col_if_absent`('lat',      "`lat` DECIMAL(9,5) DEFAULT NULL COMMENT '纬度' AFTER `lng`");

DROP PROCEDURE IF EXISTS `__add_col_if_absent`;

SELECT '项目地理点位迁移完成（city/province/lng/lat）。请重新上传统计表以回填历史项目坐标。' AS message;
