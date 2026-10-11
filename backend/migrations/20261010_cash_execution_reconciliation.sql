-- Cash execution tasks, real fund transaction traceability, and invoice allocations.
SET @schema_name = DATABASE();

CREATE TABLE IF NOT EXISTS `biz_cash_execution_task` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `direction` VARCHAR(16) NOT NULL,
  `approval_form_id` INT NULL,
  `invoice_id` INT NULL,
  `contract_id` INT NULL,
  `scenic_id` VARCHAR(64) NOT NULL,
  `planned_amount` DECIMAL(18,2) NOT NULL,
  `executed_amount` DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  `status` VARCHAR(16) NOT NULL DEFAULT 'pending',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_cash_task_approval` (`approval_form_id`),
  UNIQUE KEY `uq_cash_task_invoice` (`invoice_id`),
  CONSTRAINT `ck_cash_task_single_source` CHECK ((`direction`='outflow' AND `approval_form_id` IS NOT NULL AND `invoice_id` IS NULL) OR (`direction`='inflow' AND `invoice_id` IS NOT NULL AND `approval_form_id` IS NULL)),
  CONSTRAINT `fk_cash_task_approval` FOREIGN KEY (`approval_form_id`) REFERENCES `biz_approval_form` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_cash_task_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `biz_invoice` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_cash_task_contract` FOREIGN KEY (`contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `biz_invoice_fund_allocation` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `fund_transaction_id` INT NOT NULL,
  `invoice_id` INT NOT NULL,
  `amount` DECIMAL(18,2) NOT NULL,
  `allocated_by` INT NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_invoice_fund_allocation_fund` (`fund_transaction_id`),
  KEY `ix_invoice_fund_allocation_invoice` (`invoice_id`),
  CONSTRAINT `fk_allocation_fund` FOREIGN KEY (`fund_transaction_id`) REFERENCES `biz_fund_transaction` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_allocation_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `biz_invoice` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_allocation_user` FOREIGN KEY (`allocated_by`) REFERENCES `sys_user` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND column_name='execution_task_id'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD COLUMN `execution_task_id` INT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND column_name='contract_id'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD COLUMN `contract_id` INT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND column_name='approval_form_id'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD COLUMN `approval_form_id` INT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND column_name='invoice_id'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD COLUMN `invoice_id` INT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND column_name='scenic_id'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD COLUMN `scenic_id` VARCHAR(64) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND column_name='bank_reference'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD COLUMN `bank_reference` VARCHAR(128) NOT NULL DEFAULT \'\'');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND index_name='ix_fund_execution_task'), 'SELECT 1', 'CREATE INDEX `ix_fund_execution_task` ON `biz_fund_transaction` (`execution_task_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND index_name='ix_fund_contract'), 'SELECT 1', 'CREATE INDEX `ix_fund_contract` ON `biz_fund_transaction` (`contract_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND index_name='ix_fund_approval_form'), 'SELECT 1', 'CREATE INDEX `ix_fund_approval_form` ON `biz_fund_transaction` (`approval_form_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND index_name='ix_fund_invoice'), 'SELECT 1', 'CREATE INDEX `ix_fund_invoice` ON `biz_fund_transaction` (`invoice_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_fund_transaction' AND index_name='ix_fund_scenic'), 'SELECT 1', 'CREATE INDEX `ix_fund_scenic` ON `biz_fund_transaction` (`scenic_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_fund_transaction' AND constraint_name='fk_fund_execution_task'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD CONSTRAINT `fk_fund_execution_task` FOREIGN KEY (`execution_task_id`) REFERENCES `biz_cash_execution_task` (`id`) ON DELETE SET NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_fund_transaction' AND constraint_name='fk_fund_contract'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD CONSTRAINT `fk_fund_contract` FOREIGN KEY (`contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE SET NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_fund_transaction' AND constraint_name='fk_fund_approval_form'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD CONSTRAINT `fk_fund_approval_form` FOREIGN KEY (`approval_form_id`) REFERENCES `biz_approval_form` (`id`) ON DELETE SET NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_fund_transaction' AND constraint_name='fk_fund_invoice'), 'SELECT 1', 'ALTER TABLE `biz_fund_transaction` ADD CONSTRAINT `fk_fund_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `biz_invoice` (`id`) ON DELETE SET NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
