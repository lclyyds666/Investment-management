-- Organization, position, assignment, and permission domain.
USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `sys_organization` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `code` VARCHAR(64) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `organization_type` VARCHAR(16) NOT NULL,
  `parent_id` INT NULL,
  `company_code` VARCHAR(32) NULL,
  `sort_order` INT NOT NULL DEFAULT 0,
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_organization_code` (`code`),
  KEY `idx_organization_parent_id` (`parent_id`),
  KEY `idx_organization_company_code` (`company_code`),
  CONSTRAINT `fk_organization_parent`
    FOREIGN KEY (`parent_id`) REFERENCES `sys_organization` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Organizations and departments';

CREATE TABLE IF NOT EXISTS `sys_position` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `code` VARCHAR(96) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `category` VARCHAR(16) NOT NULL,
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_position_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Assignable positions';

CREATE TABLE IF NOT EXISTS `sys_permission` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `code` VARCHAR(128) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `resource` VARCHAR(96) NOT NULL,
  `action` VARCHAR(16) NOT NULL,
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_permission_code` (`code`),
  KEY `idx_permission_resource` (`resource`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Permission catalog';

CREATE TABLE IF NOT EXISTS `sys_user_assignment` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NOT NULL,
  `organization_id` INT NOT NULL,
  `position_id` INT NOT NULL,
  `valid_from` DATE NOT NULL,
  `valid_until` DATE NULL,
  `status` VARCHAR(16) NOT NULL DEFAULT 'active',
  `source` VARCHAR(32) NOT NULL DEFAULT 'manual',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_assignment_user_id` (`user_id`),
  KEY `idx_assignment_user_status_dates` (`user_id`, `status`, `valid_from`, `valid_until`),
  KEY `idx_assignment_org_position` (`organization_id`, `position_id`),
  CONSTRAINT `fk_assignment_user`
    FOREIGN KEY (`user_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_assignment_organization`
    FOREIGN KEY (`organization_id`) REFERENCES `sys_organization` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_assignment_position`
    FOREIGN KEY (`position_id`) REFERENCES `sys_position` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='User position assignments';

CREATE TABLE IF NOT EXISTS `sys_position_permission` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `position_id` INT NOT NULL,
  `permission_id` INT NOT NULL,
  `data_scope` VARCHAR(24) NOT NULL,
  `scope_ref` VARCHAR(96) NOT NULL DEFAULT '',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_position_permission_scope` (`position_id`, `permission_id`, `data_scope`, `scope_ref`),
  CONSTRAINT `fk_position_permission_position`
    FOREIGN KEY (`position_id`) REFERENCES `sys_position` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_position_permission_permission`
    FOREIGN KEY (`permission_id`) REFERENCES `sys_permission` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Permissions granted to positions';

CREATE TABLE IF NOT EXISTS `sys_governance_scope` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `assignment_id` INT NOT NULL,
  `scope_type` VARCHAR(32) NOT NULL,
  `scope_ref` VARCHAR(96) NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_assignment_governance_scope` (`assignment_id`, `scope_type`, `scope_ref`),
  CONSTRAINT `fk_governance_scope_assignment`
    FOREIGN KEY (`assignment_id`) REFERENCES `sys_user_assignment` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Governance scopes for assignments';

CREATE TABLE IF NOT EXISTS `sys_external_assignment` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `assignment_id` INT NOT NULL,
  `provider_name` VARCHAR(128) NOT NULL DEFAULT '',
  `service_scopes` JSON NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_external_assignment_assignment_id` (`assignment_id`),
  CONSTRAINT `fk_external_assignment_assignment`
    FOREIGN KEY (`assignment_id`) REFERENCES `sys_user_assignment` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='External assignment details';
