-- Idempotent structured authorization audit context for MySQL 8.
SET @schema_name = DATABASE();

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_audit_log' AND column_name = 'organization_code'),
  'SELECT 1',
  'ALTER TABLE sys_audit_log ADD COLUMN organization_code VARCHAR(64) NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_audit_log' AND column_name = 'organization_name'),
  'SELECT 1',
  'ALTER TABLE sys_audit_log ADD COLUMN organization_name VARCHAR(128) NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_audit_log' AND column_name = 'position_code'),
  'SELECT 1',
  'ALTER TABLE sys_audit_log ADD COLUMN position_code VARCHAR(96) NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_audit_log' AND column_name = 'position_name'),
  'SELECT 1',
  'ALTER TABLE sys_audit_log ADD COLUMN position_name VARCHAR(128) NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_audit_log' AND column_name = 'before_json'),
  'SELECT 1',
  'ALTER TABLE sys_audit_log ADD COLUMN before_json JSON NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_audit_log' AND column_name = 'after_json'),
  'SELECT 1',
  'ALTER TABLE sys_audit_log ADD COLUMN after_json JSON NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_audit_log' AND column_name = 'reason'),
  'SELECT 1',
  'ALTER TABLE sys_audit_log ADD COLUMN reason TEXT NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
