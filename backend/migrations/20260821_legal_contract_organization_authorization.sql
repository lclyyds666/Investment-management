-- 法务合同组织归属与动态候选规则（MySQL 8.0+）。
-- 先执行 20260813_unified_organization_permissions.sql、
-- 20260814_position_workflow_engine.sql 和 20260814_legal_risk_domain.sql。

SET @schema_name = DATABASE();

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'company_code'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `company_code` VARCHAR(64) NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'organization_code'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `organization_code` VARCHAR(64) NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'initiator_assignment_id'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `initiator_assignment_id` INT NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'workflow_route_version'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD COLUMN `workflow_route_version` INT NULL DEFAULT 0'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'legal_case' AND column_name = 'company_code'),
  'SELECT 1',
  'ALTER TABLE `legal_case` ADD COLUMN `company_code` VARCHAR(64) NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'legal_case' AND column_name = 'organization_code'),
  'SELECT 1',
  'ALTER TABLE `legal_case` ADD COLUMN `organization_code` VARCHAR(64) NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'legal_case' AND column_name = 'initiator_assignment_id'),
  'SELECT 1',
  'ALTER TABLE `legal_case` ADD COLUMN `initiator_assignment_id` INT NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

UPDATE `biz_contract`
SET `company_code` = 'supplymanagement',
    `organization_code` = 'supplymanagement'
WHERE `company_code` IS NULL OR `company_code` = ''
   OR `organization_code` IS NULL OR `organization_code` = '';

UPDATE `biz_contract`
SET `workflow_route_version` = 0
WHERE `workflow_route_version` IS NULL;

UPDATE `legal_case`
SET `company_code` = 'investment',
    `organization_code` = 'investment.legal_risk'
WHERE `company_code` IS NULL OR `company_code` = ''
   OR `organization_code` IS NULL OR `organization_code` = '';

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'company_code' AND is_nullable = 'YES'),
  'ALTER TABLE `biz_contract` MODIFY COLUMN `company_code` VARCHAR(64) NOT NULL',
  'SELECT 1'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'organization_code' AND is_nullable = 'YES'),
  'ALTER TABLE `biz_contract` MODIFY COLUMN `organization_code` VARCHAR(64) NOT NULL',
  'SELECT 1'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'workflow_route_version' AND (is_nullable = 'YES' OR column_default IS NULL OR column_default <> '0')),
  'ALTER TABLE `biz_contract` MODIFY COLUMN `workflow_route_version` INT NOT NULL DEFAULT 0',
  'SELECT 1'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'legal_case' AND column_name = 'company_code' AND is_nullable = 'YES'),
  'ALTER TABLE `legal_case` MODIFY COLUMN `company_code` VARCHAR(64) NOT NULL',
  'SELECT 1'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'legal_case' AND column_name = 'organization_code' AND is_nullable = 'YES'),
  'ALTER TABLE `legal_case` MODIFY COLUMN `organization_code` VARCHAR(64) NOT NULL',
  'SELECT 1'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'wf_node' AND column_name = 'candidate_rule'),
  'SELECT 1',
  'ALTER TABLE `wf_node` ADD COLUMN `candidate_rule` VARCHAR(32) NOT NULL DEFAULT ''position'''
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'wf_node' AND column_name = 'candidate_position_codes'),
  'SELECT 1',
  'ALTER TABLE `wf_node` ADD COLUMN `candidate_position_codes` JSON NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND index_name = 'ix_biz_contract_company_code'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD INDEX `ix_biz_contract_company_code` (`company_code`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND index_name = 'ix_biz_contract_organization_code'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD INDEX `ix_biz_contract_organization_code` (`organization_code`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND index_name = 'ix_biz_contract_initiator_assignment_id'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD INDEX `ix_biz_contract_initiator_assignment_id` (`initiator_assignment_id`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'legal_case' AND index_name = 'ix_legal_case_company_code'),
  'SELECT 1',
  'ALTER TABLE `legal_case` ADD INDEX `ix_legal_case_company_code` (`company_code`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'legal_case' AND index_name = 'ix_legal_case_organization_code'),
  'SELECT 1',
  'ALTER TABLE `legal_case` ADD INDEX `ix_legal_case_organization_code` (`organization_code`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.statistics WHERE table_schema = @schema_name AND table_name = 'legal_case' AND index_name = 'ix_legal_case_initiator_assignment_id'),
  'SELECT 1',
  'ALTER TABLE `legal_case` ADD INDEX `ix_legal_case_initiator_assignment_id` (`initiator_assignment_id`)'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = @schema_name AND table_name = 'biz_contract')
  AND EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'biz_contract' AND column_name = 'initiator_assignment_id')
  AND EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = @schema_name AND table_name = 'sys_user_assignment')
  AND EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_user_assignment' AND column_name = 'id'),
  'UPDATE `biz_contract` AS `record` LEFT JOIN `sys_user_assignment` AS `assignment` ON `assignment`.`id` = `record`.`initiator_assignment_id` SET `record`.`initiator_assignment_id` = NULL WHERE `record`.`initiator_assignment_id` IS NOT NULL AND `assignment`.`id` IS NULL',
  'SELECT 1'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = @schema_name AND table_name = 'legal_case')
  AND EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'legal_case' AND column_name = 'initiator_assignment_id')
  AND EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema = @schema_name AND table_name = 'sys_user_assignment')
  AND EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema = @schema_name AND table_name = 'sys_user_assignment' AND column_name = 'id'),
  'UPDATE `legal_case` AS `record` LEFT JOIN `sys_user_assignment` AS `assignment` ON `assignment`.`id` = `record`.`initiator_assignment_id` SET `record`.`initiator_assignment_id` = NULL WHERE `record`.`initiator_assignment_id` IS NOT NULL AND `assignment`.`id` IS NULL',
  'SELECT 1'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = @schema_name AND table_name = 'biz_contract' AND constraint_name = 'fk_biz_contract_initiator_assignment'),
  'SELECT 1',
  'ALTER TABLE `biz_contract` ADD CONSTRAINT `fk_biz_contract_initiator_assignment` FOREIGN KEY (`initiator_assignment_id`) REFERENCES `sys_user_assignment` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @statement = IF(
  EXISTS(SELECT 1 FROM information_schema.table_constraints WHERE constraint_schema = @schema_name AND table_name = 'legal_case' AND constraint_name = 'fk_legal_case_initiator_assignment'),
  'SELECT 1',
  'ALTER TABLE `legal_case` ADD CONSTRAINT `fk_legal_case_initiator_assignment` FOREIGN KEY (`initiator_assignment_id`) REFERENCES `sys_user_assignment` (`id`) ON DELETE SET NULL'
);
PREPARE stmt FROM @statement; EXECUTE stmt; DEALLOCATE PREPARE stmt;
