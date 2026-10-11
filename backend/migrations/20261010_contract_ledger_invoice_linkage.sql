-- Contract-to-ledger period linkage and contract snapshots for approvals/invoices.
-- Every ALTER is guarded so this migration is safe to rerun.
SET @schema_name = DATABASE();

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_contract' AND column_name='contract_term'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `contract_term` VARCHAR(255) NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_contract' AND column_name='scenic_id'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `scenic_id` VARCHAR(64) NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_contract' AND column_name='business_scopes'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `business_scopes` JSON NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_contract' AND index_name='ix_biz_contract_scenic_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_contract_scenic_id` ON `biz_contract` (`scenic_id`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND column_name='contract_id'),
  'SELECT 1',
  'ALTER TABLE `biz_approval_form` ADD COLUMN `contract_id` INT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND column_name='scenic_id'),
  'SELECT 1',
  'ALTER TABLE `biz_approval_form` ADD COLUMN `scenic_id` VARCHAR(64) NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND index_name='ix_biz_approval_form_contract_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_approval_form_contract_id` ON `biz_approval_form` (`contract_id`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND index_name='ix_biz_approval_form_scenic_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_approval_form_scenic_id` ON `biz_approval_form` (`scenic_id`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_approval_form' AND constraint_name='fk_approval_form_contract'),
  'SELECT 1',
  'ALTER TABLE `biz_approval_form` ADD CONSTRAINT `fk_approval_form_contract` FOREIGN KEY (`contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='contract_id'),
  'SELECT 1',
  'ALTER TABLE `biz_invoice` ADD COLUMN `contract_id` INT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_invoice' AND index_name='ix_biz_invoice_contract_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_invoice_contract_id` ON `biz_invoice` (`contract_id`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_invoice' AND constraint_name='fk_invoice_contract'),
  'SELECT 1',
  'ALTER TABLE `biz_invoice` ADD CONSTRAINT `fk_invoice_contract` FOREIGN KEY (`contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS `biz_ledger_contract_link` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `scenic_id` VARCHAR(64) NOT NULL,
  `source_kind` VARCHAR(16) NOT NULL,
  `period_key` VARCHAR(255) NOT NULL,
  `contract_id` INT NOT NULL,
  `contract_no_snapshot` VARCHAR(64) NOT NULL,
  `selected_by` INT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ledger_contract_period` (`scenic_id`, `source_kind`, `period_key`),
  KEY `ix_biz_ledger_contract_link_scenic_id` (`scenic_id`),
  CONSTRAINT `fk_ledger_contract_contract` FOREIGN KEY (`contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_ledger_contract_user` FOREIGN KEY (`selected_by`) REFERENCES `sys_user` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `biz_scenic_contract_preference` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `scenic_id` VARCHAR(64) NOT NULL,
  `source_kind` VARCHAR(16) NOT NULL,
  `last_contract_id` INT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scenic_contract_preference` (`scenic_id`, `source_kind`),
  KEY `ix_biz_scenic_contract_preference_scenic_id` (`scenic_id`),
  CONSTRAINT `fk_scenic_contract_preference_contract` FOREIGN KEY (`last_contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
