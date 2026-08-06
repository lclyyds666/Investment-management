-- AI assistant conversations, messages, aggregate-only tool traces, and deletion receipts.
USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `ai_conversation` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `owner_id` INT NOT NULL,
  `title` VARCHAR(120) NOT NULL DEFAULT '新会话',
  `status` VARCHAR(24) NOT NULL DEFAULT 'active',
  `last_active_at` DATETIME NOT NULL,
  `expires_at` DATETIME NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ai_conversation_owner` (`owner_id`),
  KEY `idx_ai_conversation_status` (`status`),
  KEY `idx_ai_conversation_activity` (`last_active_at`),
  KEY `idx_ai_conversation_expiry` (`expires_at`),
  CONSTRAINT `fk_ai_conversation_owner`
    FOREIGN KEY (`owner_id`) REFERENCES `sys_user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI assistant conversations';

CREATE TABLE IF NOT EXISTS `ai_message` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `conversation_id` INT NOT NULL,
  `role` VARCHAR(16) NOT NULL,
  `content` TEXT NOT NULL,
  `status` VARCHAR(24) NOT NULL,
  `client_message_id` VARCHAR(64) NULL,
  `request_id` VARCHAR(64) NULL,
  `actions_json` JSON NOT NULL,
  `data_start_date` DATE NULL,
  `data_end_date` DATE NULL,
  `data_covered_start` DATE NULL,
  `data_covered_end` DATE NULL,
  `data_updated_at` DATETIME NULL,
  `engine` VARCHAR(24) NULL,
  `first_token_ms` INT NULL,
  `duration_ms` INT NULL,
  `error_code` VARCHAR(64) NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_ai_message_client` (`conversation_id`, `client_message_id`),
  KEY `idx_ai_message_conversation` (`conversation_id`),
  KEY `idx_ai_message_status` (`status`),
  KEY `idx_ai_message_request` (`request_id`),
  CONSTRAINT `fk_ai_message_conversation`
    FOREIGN KEY (`conversation_id`) REFERENCES `ai_conversation` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='AI assistant messages';

CREATE TABLE IF NOT EXISTS `ai_tool_call` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `message_id` INT NOT NULL,
  `tool_name` VARCHAR(64) NOT NULL,
  `arguments_json` JSON NOT NULL,
  `permission_decision` VARCHAR(24) NOT NULL,
  `status` VARCHAR(24) NOT NULL,
  `duration_ms` INT NULL,
  `result_summary_json` JSON NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ai_tool_message` (`message_id`),
  KEY `idx_ai_tool_name` (`tool_name`),
  KEY `idx_ai_tool_status` (`status`),
  CONSTRAINT `fk_ai_tool_message`
    FOREIGN KEY (`message_id`) REFERENCES `ai_message` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Sanitized AI tool traces';

CREATE TABLE IF NOT EXISTS `ai_deletion_audit` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `conversation_id` INT NOT NULL,
  `owner_id` INT NOT NULL,
  `actor_id` INT NULL,
  `mode` VARCHAR(24) NOT NULL,
  `reason` VARCHAR(200) NOT NULL,
  `deleted_message_count` INT NOT NULL DEFAULT 0,
  `deleted_at` DATETIME NOT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ai_deletion_conversation` (`conversation_id`),
  KEY `idx_ai_deletion_owner` (`owner_id`),
  KEY `idx_ai_deletion_actor` (`actor_id`),
  KEY `idx_ai_deletion_mode` (`mode`),
  KEY `idx_ai_deletion_time` (`deleted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Content-free AI deletion receipts';
