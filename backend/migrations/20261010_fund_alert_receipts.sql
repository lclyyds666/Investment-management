-- Daily per-user fund maturity alert receipts. Safe to run repeatedly on MySQL 8.
CREATE TABLE IF NOT EXISTS `biz_fund_alert_receipt` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `fund_id` INT NOT NULL,
  `alert_date` DATE NOT NULL,
  `stage` VARCHAR(16) NOT NULL,
  `shown_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_fund_alert_receipt_daily_stage` (`user_id`, `fund_id`, `alert_date`, `stage`),
  KEY `ix_fund_alert_receipt_lookup` (`user_id`, `alert_date`, `stage`),
  KEY `ix_biz_fund_alert_receipt_user_id` (`user_id`),
  KEY `ix_biz_fund_alert_receipt_fund_id` (`fund_id`),
  CONSTRAINT `fk_fund_alert_receipt_user`
    FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_fund_alert_receipt_fund`
    FOREIGN KEY (`fund_id`) REFERENCES `biz_fund_transaction` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
