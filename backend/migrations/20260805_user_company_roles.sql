-- Company-role memberships for the unified portal.
USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `sys_user_company_role` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `company_code` VARCHAR(32) NOT NULL,
  `role` VARCHAR(32) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_company_role` (`user_id`, `company_code`),
  KEY `idx_user_company_role_user_id` (`user_id`),
  KEY `idx_user_company_role_company_code` (`company_code`),
  CONSTRAINT `fk_user_company_role_user`
    FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='User company role memberships';

INSERT IGNORE INTO sys_user_company_role (user_id, company_code, role)
SELECT id, 'supplymanagement', role FROM sys_user;
