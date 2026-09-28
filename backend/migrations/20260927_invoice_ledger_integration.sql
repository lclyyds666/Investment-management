-- Invoice source snapshots, attachments and customer banking data.
-- All ALTER statements are guarded so this migration is safe to rerun.
SET @schema_name = DATABASE();

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='direction'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `direction` VARCHAR(16) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='source_kind'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `source_kind` VARCHAR(16) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='scenic_id'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `scenic_id` VARCHAR(64) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='period_key'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `period_key` VARCHAR(255) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='period_key' AND character_maximum_length < 255), 'ALTER TABLE `biz_invoice` MODIFY COLUMN `period_key` VARCHAR(255) NULL', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='source_revision'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `source_revision` INT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='source_fingerprint'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `source_fingerprint` VARCHAR(128) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='generated_by_source'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `generated_by_source` TINYINT(1) NULL DEFAULT 0');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='customer_id'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `customer_id` INT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='customer_social_credit_code'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `customer_social_credit_code` VARCHAR(32) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='customer_address'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `customer_address` VARCHAR(255) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='customer_phone'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `customer_phone` VARCHAR(32) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='customer_bank_name'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `customer_bank_name` VARCHAR(128) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='customer_bank_account'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `customer_bank_account` VARCHAR(64) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='workflow_instance_id'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `workflow_instance_id` INT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='approval_status'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `approval_status` VARCHAR(16) NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='generated_at'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `generated_at` DATETIME NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_invoice' AND column_name='source_synced_at'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD COLUMN `source_synced_at` DATETIME NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_invoice' AND index_name='uq_invoice_source'), 'SELECT 1', 'CREATE UNIQUE INDEX `uq_invoice_source` ON `biz_invoice` (`direction`, `source_kind`, `scenic_id`, `period_key`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_invoice' AND index_name='ix_biz_invoice_customer_id'), 'SELECT 1', 'CREATE INDEX `ix_biz_invoice_customer_id` ON `biz_invoice` (`customer_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_invoice' AND index_name='ix_biz_invoice_workflow_instance_id'), 'SELECT 1', 'CREATE INDEX `ix_biz_invoice_workflow_instance_id` ON `biz_invoice` (`workflow_instance_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_invoice' AND constraint_name='fk_invoice_customer'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD CONSTRAINT `fk_invoice_customer` FOREIGN KEY (`customer_id`) REFERENCES `biz_customer` (`id`) ON DELETE SET NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_invoice' AND constraint_name='fk_invoice_workflow_instance'), 'SELECT 1', 'ALTER TABLE `biz_invoice` ADD CONSTRAINT `fk_invoice_workflow_instance` FOREIGN KEY (`workflow_instance_id`) REFERENCES `wf_instance` (`id`) ON DELETE SET NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS `biz_invoice_attachment` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `invoice_id` INT NOT NULL,
  `original_name` VARCHAR(255) NOT NULL DEFAULT '',
  `stored_name` VARCHAR(255) NOT NULL DEFAULT '',
  `content_type` VARCHAR(128) NOT NULL DEFAULT '',
  `file_size` INT NOT NULL DEFAULT 0,
  `uploaded_by` INT NULL,
  `uploaded_at` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_biz_invoice_attachment_invoice_id` (`invoice_id`),
  CONSTRAINT `fk_invoice_attachment_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `biz_invoice` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_invoice_attachment_uploaded_by` FOREIGN KEY (`uploaded_by`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `biz_invoice_detail` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `invoice_id` INT NOT NULL,
  `line_no` INT NOT NULL DEFAULT 0,
  `source_row_id` INT NULL,
  `source_kind` VARCHAR(16) NULL,
  `platform` VARCHAR(64) NOT NULL DEFAULT '',
  `item_name` VARCHAR(255) NOT NULL DEFAULT '',
  `amount` DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_biz_invoice_detail_invoice_id` (`invoice_id`),
  CONSTRAINT `fk_invoice_detail_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `biz_invoice` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `biz_scenic_invoice_preference` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `scenic_id` VARCHAR(64) NOT NULL,
  `direction` VARCHAR(16) NOT NULL,
  `last_contract_no` VARCHAR(64) NOT NULL DEFAULT '',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_scenic_invoice_preference` (`scenic_id`, `direction`),
  KEY `ix_scenic_invoice_preference_scenic_id` (`scenic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_customer' AND column_name='bank_name'), 'SELECT 1', 'ALTER TABLE `biz_customer` ADD COLUMN `bank_name` VARCHAR(128) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_customer' AND column_name='bank_account'), 'SELECT 1', 'ALTER TABLE `biz_customer` ADD COLUMN `bank_account` VARCHAR(64) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND column_name='invoice_id'), 'SELECT 1', 'ALTER TABLE `biz_approval_form` ADD COLUMN `invoice_id` INT NULL');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND column_name='invoice_tax_no'), 'SELECT 1', 'ALTER TABLE `biz_approval_form` ADD COLUMN `invoice_tax_no` VARCHAR(64) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND column_name='invoice_customer_address'), 'SELECT 1', 'ALTER TABLE `biz_approval_form` ADD COLUMN `invoice_customer_address` VARCHAR(255) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND column_name='invoice_customer_phone'), 'SELECT 1', 'ALTER TABLE `biz_approval_form` ADD COLUMN `invoice_customer_phone` VARCHAR(32) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND column_name='invoice_type_snapshot'), 'SELECT 1', 'ALTER TABLE `biz_approval_form` ADD COLUMN `invoice_type_snapshot` VARCHAR(32) NOT NULL DEFAULT ''''');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND index_name='ix_biz_approval_form_invoice_id'), 'SELECT 1', 'CREATE INDEX `ix_biz_approval_form_invoice_id` ON `biz_approval_form` (`invoice_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema=@schema_name AND table_name='biz_approval_form' AND index_name='uq_approval_form_invoice_id'), 'SELECT 1', 'CREATE UNIQUE INDEX `uq_approval_form_invoice_id` ON `biz_approval_form` (`invoice_id`)');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @needs_invoice_fk_rebuild = IF(EXISTS(SELECT 1 FROM information_schema.referential_constraints WHERE constraint_schema=@schema_name AND table_name='biz_approval_form' AND constraint_name='fk_approval_form_invoice' AND delete_rule <> 'CASCADE'), 1, 0);
SET @ddl = IF(@needs_invoice_fk_rebuild = 1, 'ALTER TABLE `biz_approval_form` DROP FOREIGN KEY `fk_approval_form_invoice`', 'SELECT 1');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @ddl = IF(EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema=@schema_name AND table_name='biz_approval_form' AND constraint_name='fk_approval_form_invoice'), 'SELECT 1', 'ALTER TABLE `biz_approval_form` ADD CONSTRAINT `fk_approval_form_invoice` FOREIGN KEY (`invoice_id`) REFERENCES `biz_invoice` (`id`) ON DELETE CASCADE');
PREPARE stmt FROM @ddl; EXECUTE stmt; DEALLOCATE PREPARE stmt;
