-- Fund transaction ledger. This migration is safe to run repeatedly on MySQL 8.
CREATE TABLE IF NOT EXISTS `biz_fund_transaction` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `direction` VARCHAR(16) NOT NULL,
  `category` VARCHAR(32) NOT NULL,
  `amount` DECIMAL(18,2) NOT NULL,
  `occurred_on` DATE NOT NULL,
  `counterparty` VARCHAR(200) NOT NULL DEFAULT '',
  `summary` VARCHAR(300) NOT NULL DEFAULT '',
  `maturity_date` DATE NULL,
  `settlement_status` VARCHAR(16) NOT NULL DEFAULT 'open',
  `settled_on` DATE NULL,
  `remark` TEXT NULL,
  `created_by` BIGINT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_fund_transaction_created_by`
    FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @schema_name = DATABASE();

SET @statement = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = @schema_name
      AND table_name = 'biz_fund_transaction'
      AND index_name = 'idx_fund_occurred_on'
  ),
  'SELECT 1',
  'CREATE INDEX idx_fund_occurred_on ON biz_fund_transaction (occurred_on)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(
    SELECT 1 FROM information_schema.statistics
    WHERE table_schema = @schema_name
      AND table_name = 'biz_fund_transaction'
      AND index_name = 'idx_fund_maturity_status'
  ),
  'SELECT 1',
  'CREATE INDEX idx_fund_maturity_status ON biz_fund_transaction (maturity_date, settlement_status)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
