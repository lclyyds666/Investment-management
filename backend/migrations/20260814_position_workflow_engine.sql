-- Position-aware workflow persistence for MySQL 8.
-- New tables are created in dependency order. Compatibility changes are guarded
-- so this migration can be rerun without modifying or deleting existing rows.
SET @schema_name = DATABASE();

CREATE TABLE IF NOT EXISTS `wf_definition` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `code` VARCHAR(96) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `target_type` VARCHAR(24) NOT NULL,
  `active_version_id` INT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_wf_definition_code` (`code`),
  KEY `ix_wf_definition_target_type` (`target_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `wf_version` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `definition_id` INT NOT NULL,
  `version` INT NOT NULL,
  `status` VARCHAR(16) NOT NULL DEFAULT 'draft',
  `published_at` DATETIME NULL,
  `published_by` INT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `uq_workflow_version_definition_version` UNIQUE (`definition_id`, `version`),
  KEY `ix_wf_version_definition_id` (`definition_id`),
  KEY `ix_wf_version_status` (`status`),
  CONSTRAINT `fk_workflow_version_definition` FOREIGN KEY (`definition_id`) REFERENCES `wf_definition` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_workflow_version_published_by` FOREIGN KEY (`published_by`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = @schema_name AND table_name = 'wf_definition' AND constraint_name = 'fk_workflow_definition_active_version'),
  'SELECT 1',
  'ALTER TABLE `wf_definition` ADD CONSTRAINT `fk_workflow_definition_active_version` FOREIGN KEY (`active_version_id`) REFERENCES `wf_version` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS `wf_node` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `version_id` INT NOT NULL,
  `sequence` INT NOT NULL,
  `code` VARCHAR(96) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `position_code` VARCHAR(96) NOT NULL,
  `assignee_mode` VARCHAR(24) NOT NULL,
  `auto_complete_on_submit` TINYINT(1) NOT NULL DEFAULT 0,
  `allow_reject` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `uq_workflow_node_version_sequence` UNIQUE (`version_id`, `sequence`),
  CONSTRAINT `uq_workflow_node_version_code` UNIQUE (`version_id`, `code`),
  KEY `idx_workflow_node_position` (`position_code`),
  CONSTRAINT `fk_workflow_node_version` FOREIGN KEY (`version_id`) REFERENCES `wf_version` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `wf_instance` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `definition_id` INT NOT NULL,
  `version_id` INT NOT NULL,
  `target_type` VARCHAR(24) NOT NULL,
  `target_id` INT NOT NULL,
  `status` VARCHAR(16) NOT NULL DEFAULT 'active',
  `current_sequence` INT NOT NULL DEFAULT 0,
  `submitted_by` INT NOT NULL,
  `submitted_at` DATETIME NOT NULL,
  `completed_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `uq_workflow_instance_target` UNIQUE (`target_type`, `target_id`),
  KEY `ix_wf_instance_definition_id` (`definition_id`),
  KEY `ix_wf_instance_version_id` (`version_id`),
  KEY `idx_workflow_instance_status_sequence` (`status`, `current_sequence`),
  CONSTRAINT `fk_workflow_instance_definition` FOREIGN KEY (`definition_id`) REFERENCES `wf_definition` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_workflow_instance_version` FOREIGN KEY (`version_id`) REFERENCES `wf_version` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_workflow_instance_submitted_by` FOREIGN KEY (`submitted_by`) REFERENCES `sys_user` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `wf_task` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `instance_id` INT NOT NULL,
  `node_id` INT NOT NULL,
  `sequence` INT NOT NULL,
  `status` VARCHAR(24) NOT NULL DEFAULT 'pending',
  `required_position_code` VARCHAR(96) NOT NULL,
  `assignee_mode` VARCHAR(24) NOT NULL,
  `designated_user_id` INT NULL,
  `designated_assignment_id` INT NULL,
  `activated_at` DATETIME NULL,
  `completed_at` DATETIME NULL,
  `version` INT NOT NULL DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  CONSTRAINT `uq_workflow_task_instance_node` UNIQUE (`instance_id`, `node_id`),
  KEY `idx_workflow_task_status_position` (`status`, `required_position_code`),
  KEY `idx_workflow_task_designated_user_status` (`designated_user_id`, `status`),
  CONSTRAINT `fk_workflow_task_instance` FOREIGN KEY (`instance_id`) REFERENCES `wf_instance` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_workflow_task_node` FOREIGN KEY (`node_id`) REFERENCES `wf_node` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_workflow_task_designated_user` FOREIGN KEY (`designated_user_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_workflow_task_designated_assignment` FOREIGN KEY (`designated_assignment_id`) REFERENCES `sys_user_assignment` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `wf_task_action` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` INT NOT NULL,
  `action` VARCHAR(16) NOT NULL,
  `actor_id` INT NOT NULL,
  `actor_name` VARCHAR(128) NOT NULL,
  `organization_code` VARCHAR(64) NOT NULL DEFAULT '',
  `organization_name` VARCHAR(128) NOT NULL DEFAULT '',
  `position_code` VARCHAR(96) NOT NULL DEFAULT '',
  `position_name` VARCHAR(128) NOT NULL DEFAULT '',
  `comment` TEXT NOT NULL,
  `signature_snapshot` MEDIUMTEXT NULL,
  `previous_assignee_id` INT NULL,
  `previous_assignee_name` VARCHAR(128) NULL,
  `new_assignee_id` INT NULL,
  `new_assignee_name` VARCHAR(128) NULL,
  `reason` TEXT NOT NULL,
  `returned_to_sequence` INT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_workflow_task_action_task_created` (`task_id`, `created_at`),
  CONSTRAINT `fk_workflow_task_action_task` FOREIGN KEY (`task_id`) REFERENCES `wf_task` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_workflow_task_action_actor` FOREIGN KEY (`actor_id`) REFERENCES `sys_user` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_workflow_task_action_previous_assignee` FOREIGN KEY (`previous_assignee_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_workflow_task_action_new_assignee` FOREIGN KEY (`new_assignee_id`) REFERENCES `sys_user` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'wf_task_action' AND column_name = 'previous_assignee_name'),
  'SELECT 1',
  'ALTER TABLE `wf_task_action` ADD COLUMN `previous_assignee_name` VARCHAR(128) NULL AFTER `previous_assignee_id`'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'wf_task_action' AND column_name = 'new_assignee_name'),
  'SELECT 1',
  'ALTER TABLE `wf_task_action` ADD COLUMN `new_assignee_name` VARCHAR(128) NULL AFTER `new_assignee_id`'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'workflow_instance_id'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `workflow_instance_id` INT NULL COMMENT ''新版岗位工作流实例'''
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_approval_form' AND column_name = 'workflow_instance_id'),
  'SELECT 1',
  'ALTER TABLE `biz_approval_form` ADD COLUMN `workflow_instance_id` INT NULL COMMENT ''新版岗位工作流实例'''
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_approval' AND column_name = 'workflow_task_action_id'),
  'SELECT 1',
  'ALTER TABLE `biz_approval` ADD COLUMN `workflow_task_action_id` INT NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_approval_form_action' AND column_name = 'workflow_task_action_id'),
  'SELECT 1',
  'ALTER TABLE `biz_approval_form_action` ADD COLUMN `workflow_task_action_id` INT NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND index_name = 'ix_biz_contract_workflow_instance_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_contract_workflow_instance_id` ON `biz_contract` (`workflow_instance_id`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'biz_approval_form' AND index_name = 'ix_biz_approval_form_workflow_instance_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_approval_form_workflow_instance_id` ON `biz_approval_form` (`workflow_instance_id`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'biz_approval' AND index_name = 'ix_biz_approval_workflow_task_action_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_approval_workflow_task_action_id` ON `biz_approval` (`workflow_task_action_id`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'biz_approval_form_action' AND index_name = 'ix_biz_approval_form_action_workflow_task_action_id'),
  'SELECT 1',
  'CREATE INDEX `ix_biz_approval_form_action_workflow_task_action_id` ON `biz_approval_form_action` (`workflow_task_action_id`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = @schema_name AND table_name = 'biz_contract' AND constraint_name = 'fk_contract_workflow_instance'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD CONSTRAINT `fk_contract_workflow_instance` FOREIGN KEY (`workflow_instance_id`) REFERENCES `wf_instance` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = @schema_name AND table_name = 'biz_approval_form' AND constraint_name = 'fk_approval_form_workflow_instance'),
  'SELECT 1',
  'ALTER TABLE `biz_approval_form` ADD CONSTRAINT `fk_approval_form_workflow_instance` FOREIGN KEY (`workflow_instance_id`) REFERENCES `wf_instance` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = @schema_name AND table_name = 'biz_approval' AND constraint_name = 'fk_approval_workflow_task_action'),
  'SELECT 1',
  'ALTER TABLE `biz_approval` ADD CONSTRAINT `fk_approval_workflow_task_action` FOREIGN KEY (`workflow_task_action_id`) REFERENCES `wf_task_action` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = @schema_name AND table_name = 'biz_approval_form_action' AND constraint_name = 'fk_approval_form_action_workflow_task_action'),
  'SELECT 1',
  'ALTER TABLE `biz_approval_form_action` ADD CONSTRAINT `fk_approval_form_action_workflow_task_action` FOREIGN KEY (`workflow_task_action_id`) REFERENCES `wf_task_action` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- Snapshot columns are nullable to preserve all legacy approval rows.
SET @compat_table = 'biz_approval';
SET @compat_column = 'organization_code';
SET @compat_type = 'VARCHAR(64) NULL';
SET @statement = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = @compat_table AND column_name = @compat_column), 'SELECT 1', CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `', @compat_column, '` ', @compat_type));
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @compat_column = 'organization_name'; SET @compat_type = 'VARCHAR(128) NULL';
SET @statement = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = @compat_table AND column_name = @compat_column), 'SELECT 1', CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `', @compat_column, '` ', @compat_type));
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @compat_column = 'position_code'; SET @compat_type = 'VARCHAR(96) NULL';
SET @statement = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = @compat_table AND column_name = @compat_column), 'SELECT 1', CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `', @compat_column, '` ', @compat_type));
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @compat_column = 'position_name'; SET @compat_type = 'VARCHAR(128) NULL';
SET @statement = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = @compat_table AND column_name = @compat_column), 'SELECT 1', CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `', @compat_column, '` ', @compat_type));
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @compat_table = 'biz_approval_form_action';
SET @compat_column = 'organization_code'; SET @compat_type = 'VARCHAR(64) NULL';
SET @statement = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = @compat_table AND column_name = @compat_column), 'SELECT 1', CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `', @compat_column, '` ', @compat_type));
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @compat_column = 'organization_name'; SET @compat_type = 'VARCHAR(128) NULL';
SET @statement = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = @compat_table AND column_name = @compat_column), 'SELECT 1', CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `', @compat_column, '` ', @compat_type));
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @compat_column = 'position_code'; SET @compat_type = 'VARCHAR(96) NULL';
SET @statement = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = @compat_table AND column_name = @compat_column), 'SELECT 1', CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `', @compat_column, '` ', @compat_type));
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
SET @compat_column = 'position_name'; SET @compat_type = 'VARCHAR(128) NULL';
SET @statement = IF(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = @compat_table AND column_name = @compat_column), 'SELECT 1', CONCAT('ALTER TABLE `', @compat_table, '` ADD COLUMN `', @compat_column, '` ', @compat_type));
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
