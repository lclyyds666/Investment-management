-- 法务风控投递并发领取字段；适用于已先执行 domain 脚本的环境。
-- 新环境的 domain 脚本已包含这些字段，本脚本仍可安全重复执行。

SET @has_legal_claim_token = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'legal_alert_delivery'
      AND COLUMN_NAME = 'claim_token'
);
SET @add_legal_claim_token = IF(
    @has_legal_claim_token = 0,
    'ALTER TABLE `legal_alert_delivery` ADD COLUMN `claim_token` VARCHAR(64) NULL AFTER `status`',
    'SELECT 1'
);
PREPARE legal_hardening_stmt FROM @add_legal_claim_token;
EXECUTE legal_hardening_stmt;
DEALLOCATE PREPARE legal_hardening_stmt;

SET @has_legal_claim_expires = (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'legal_alert_delivery'
      AND COLUMN_NAME = 'claim_expires_at'
);
SET @add_legal_claim_expires = IF(
    @has_legal_claim_expires = 0,
    'ALTER TABLE `legal_alert_delivery` ADD COLUMN `claim_expires_at` DATETIME NULL AFTER `claim_token`',
    'SELECT 1'
);
PREPARE legal_hardening_stmt FROM @add_legal_claim_expires;
EXECUTE legal_hardening_stmt;
DEALLOCATE PREPARE legal_hardening_stmt;

SET @has_legal_claim_index = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'legal_alert_delivery'
      AND INDEX_NAME = 'ix_legal_delivery_claim'
);
SET @add_legal_claim_index = IF(
    @has_legal_claim_index = 0,
    'CREATE INDEX `ix_legal_delivery_claim` ON `legal_alert_delivery` (`claim_token`, `claim_expires_at`)',
    'SELECT 1'
);
PREPARE legal_hardening_stmt FROM @add_legal_claim_index;
EXECUTE legal_hardening_stmt;
DEALLOCATE PREPARE legal_hardening_stmt;

SELECT '法务风控并发投递字段迁移完成。' AS message;
