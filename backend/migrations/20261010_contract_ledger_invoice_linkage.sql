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
  `id` INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='id'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `id` INT NOT NULL FIRST'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_ledger_contract_link' AND constraint_type='PRIMARY KEY'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD PRIMARY KEY (`id`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='id' AND extra LIKE '%auto_increment%'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` MODIFY COLUMN `id` INT NOT NULL AUTO_INCREMENT'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='scenic_id'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `scenic_id` VARCHAR(64) NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='source_kind'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `source_kind` VARCHAR(16) NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='period_key'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `period_key` VARCHAR(255) NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='contract_id'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `contract_id` INT NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='contract_no_snapshot'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `contract_no_snapshot` VARCHAR(64) NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='selected_by'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `selected_by` INT NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='created_at'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND column_name='updated_at'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND index_name='uq_ledger_contract_period'),
  'SELECT 1',
  'CREATE UNIQUE INDEX `uq_ledger_contract_period` ON `biz_ledger_contract_link` (`scenic_id`, `source_kind`, `period_key`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_ledger_contract_link' AND index_name='ix_biz_ledger_contract_link_scenic_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_ledger_contract_link_scenic_id` ON `biz_ledger_contract_link` (`scenic_id`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_ledger_contract_link' AND constraint_name='fk_ledger_contract_contract'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD CONSTRAINT `fk_ledger_contract_contract` FOREIGN KEY (`contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE RESTRICT'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_ledger_contract_link' AND constraint_name='fk_ledger_contract_user'),
  'SELECT 1',
  'ALTER TABLE `biz_ledger_contract_link` ADD CONSTRAINT `fk_ledger_contract_user` FOREIGN KEY (`selected_by`) REFERENCES `sys_user` (`id`) ON DELETE RESTRICT'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS `biz_scenic_contract_preference` (
  `id` INT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND column_name='id'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` ADD COLUMN `id` INT NOT NULL FIRST'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND constraint_type='PRIMARY KEY'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` ADD PRIMARY KEY (`id`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND column_name='id' AND extra LIKE '%auto_increment%'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` MODIFY COLUMN `id` INT NOT NULL AUTO_INCREMENT'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND column_name='scenic_id'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` ADD COLUMN `scenic_id` VARCHAR(64) NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND column_name='source_kind'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` ADD COLUMN `source_kind` VARCHAR(16) NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND column_name='last_contract_id'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` ADD COLUMN `last_contract_id` INT NOT NULL'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND column_name='created_at'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` ADD COLUMN `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND column_name='updated_at'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` ADD COLUMN `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND index_name='uq_scenic_contract_preference'),
  'SELECT 1',
  'CREATE UNIQUE INDEX `uq_scenic_contract_preference` ON `biz_scenic_contract_preference` (`scenic_id`, `source_kind`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND index_name='ix_biz_scenic_contract_preference_scenic_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_scenic_contract_preference_scenic_id` ON `biz_scenic_contract_preference` (`scenic_id`)'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_scenic_contract_preference' AND constraint_name='fk_scenic_contract_preference_contract'),
  'SELECT 1',
  'ALTER TABLE `biz_scenic_contract_preference` ADD CONSTRAINT `fk_scenic_contract_preference_contract` FOREIGN KEY (`last_contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE RESTRICT'
);
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
