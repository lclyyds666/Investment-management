-- 投资公司法务风控模块：用户钉钉提醒配置。
-- 执行前请备份数据库；本项目迁移按日期顺序手工执行。
-- 每列独立检测，支持全新、部分执行和重复执行三种场景。

SET @has_legal_mobile = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'sys_user'
      AND COLUMN_NAME = 'mobile'
);
SET @add_legal_mobile = IF(
    @has_legal_mobile = 0,
    'ALTER TABLE `sys_user` ADD COLUMN `mobile` VARCHAR(11) NULL COMMENT ''法务钉钉提醒手机号'' AFTER `department`',
    'SELECT 1'
);
PREPARE legal_foundation_stmt FROM @add_legal_mobile;
EXECUTE legal_foundation_stmt;
DEALLOCATE PREPARE legal_foundation_stmt;

SET @has_legal_alert_enabled = (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'sys_user'
      AND COLUMN_NAME = 'legal_alert_enabled'
);
SET @add_legal_alert_enabled = IF(
    @has_legal_alert_enabled = 0,
    'ALTER TABLE `sys_user` ADD COLUMN `legal_alert_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''是否接收法务钉钉@提醒'' AFTER `mobile`',
    'SELECT 1'
);
PREPARE legal_foundation_stmt FROM @add_legal_alert_enabled;
EXECUTE legal_foundation_stmt;
DEALLOCATE PREPARE legal_foundation_stmt;

-- 将法务页面接入统一组织权限目录。INSERT IGNORE 保证可重复执行。
INSERT IGNORE INTO `sys_permission` (`code`, `name`, `resource`, `action`, `is_active`)
VALUES
  ('investment.legal.dashboard.view', '法务工作台查看', 'investment.legal.dashboard', 'view', 1),
  ('investment.legal.cases.view', '法务案件查看', 'investment.legal.cases', 'view', 1),
  ('investment.legal.alerts.view', '法务预警查看', 'investment.legal.alerts', 'view', 1),
  ('investment.legal.statistics.view', '法务统计查看', 'investment.legal.statistics', 'view', 1),
  ('investment.legal.admin.view', '法务通知人员维护', 'investment.legal.admin', 'view', 1);

-- 普通业务、法务岗位及管理层均可进入投资公司应用。
INSERT IGNORE INTO `sys_position_permission`
  (`position_id`, `permission_id`, `data_scope`, `scope_ref`)
SELECT position_row.`id`, permission_row.`id`, 'platform', 'investment'
FROM `sys_position` AS position_row
JOIN `sys_permission` AS permission_row
  ON permission_row.`code` = 'investment.portal.enter'
WHERE position_row.`code` IN (
  'investment.executive.chairman',
  'investment.executive.general_manager',
  'investment.executive.deputy_general_manager',
  'investment.department.director',
  'investment.department.deputy_director',
  'investment.department.senior_manager',
  'investment.department.middle_manager',
  'investment.department.junior_manager',
  'supply.business_handler',
  'supply.business_reviewer',
  'supply.finance_handler',
  'supply.company_leader',
  'governance.supply_leader',
  'investment.duty.supply_risk_review',
  'investment.duty.supply_finance_review',
  'external.legal_counsel'
);

-- 普通业务人员与法务风控人员拥有相同的四个业务页面权限；管理层只读同样页面。
INSERT IGNORE INTO `sys_position_permission`
  (`position_id`, `permission_id`, `data_scope`, `scope_ref`)
SELECT position_row.`id`, permission_row.`id`, 'company', 'investment'
FROM `sys_position` AS position_row
JOIN `sys_permission` AS permission_row
  ON permission_row.`code` IN (
    'investment.legal.dashboard.view',
    'investment.legal.cases.view',
    'investment.legal.alerts.view',
    'investment.legal.statistics.view'
  )
WHERE position_row.`code` IN (
  'investment.executive.chairman',
  'investment.executive.general_manager',
  'investment.executive.deputy_general_manager',
  'investment.department.director',
  'investment.department.deputy_director',
  'investment.department.senior_manager',
  'investment.department.middle_manager',
  'investment.department.junior_manager',
  'supply.business_handler',
  'supply.business_reviewer',
  'supply.finance_handler',
  'supply.company_leader',
  'governance.supply_leader',
  'investment.duty.supply_risk_review',
  'investment.duty.supply_finance_review'
);

-- 外聘法律顾问只显示被指派案件及其预警页面，数据范围由接口继续收紧。
INSERT IGNORE INTO `sys_position_permission`
  (`position_id`, `permission_id`, `data_scope`, `scope_ref`)
SELECT position_row.`id`, permission_row.`id`, 'company', 'investment'
FROM `sys_position` AS position_row
JOIN `sys_permission` AS permission_row
  ON permission_row.`code` IN (
    'investment.legal.cases.view',
    'investment.legal.alerts.view'
  )
WHERE position_row.`code` = 'external.legal_counsel';

SELECT '法务风控用户提醒字段迁移完成。' AS message;
