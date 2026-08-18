-- 允许同一来源日期在多次修改后重新启用，同时保持每次预警的历史记录。
-- 新环境的 domain 脚本已包含 generation，本脚本可安全重复执行。

SET @has_legal_alert_generation = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'legal_case_alert'
      AND COLUMN_NAME = 'generation'
);
SET @add_legal_alert_generation = IF(
    @has_legal_alert_generation = 0,
    'ALTER TABLE `legal_case_alert` ADD COLUMN `generation` INT NOT NULL DEFAULT 1 AFTER `cycle_key`',
    'SELECT 1'
);
PREPARE legal_alert_generation_stmt FROM @add_legal_alert_generation;
EXECUTE legal_alert_generation_stmt;
DEALLOCATE PREPARE legal_alert_generation_stmt;

SET @legal_alert_cycle_index_columns = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'legal_case_alert'
      AND INDEX_NAME = 'uq_legal_case_alert_cycle'
);
SET @legal_alert_cycle_index_has_generation = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'legal_case_alert'
      AND INDEX_NAME = 'uq_legal_case_alert_cycle'
      AND COLUMN_NAME = 'generation'
      AND SEQ_IN_INDEX = 6
);
SET @replace_legal_alert_cycle_index = CASE
    WHEN @legal_alert_cycle_index_columns = 0 THEN
        'ALTER TABLE `legal_case_alert` ADD UNIQUE KEY `uq_legal_case_alert_cycle` (`case_id`, `source_type`, `source_id`, `alert_type`, `cycle_key`, `generation`)'
    WHEN @legal_alert_cycle_index_columns = 6
         AND @legal_alert_cycle_index_has_generation = 1 THEN
        'SELECT 1'
    ELSE
        'ALTER TABLE `legal_case_alert` DROP INDEX `uq_legal_case_alert_cycle`, ADD UNIQUE KEY `uq_legal_case_alert_cycle` (`case_id`, `source_type`, `source_id`, `alert_type`, `cycle_key`, `generation`)'
END;
PREPARE legal_alert_generation_stmt FROM @replace_legal_alert_cycle_index;
EXECUTE legal_alert_generation_stmt;
DEALLOCATE PREPARE legal_alert_generation_stmt;

SELECT '法务预警周期代次迁移完成。' AS message;
