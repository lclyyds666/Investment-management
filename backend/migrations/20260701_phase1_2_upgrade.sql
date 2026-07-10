-- =============================================================
--  阶段一 & 二 升级迁移脚本（在已存在数据的运行库上执行一次）
--  目标库: sd_publish_scm (MySQL 8.0+)
--  内容:
--    1) 用户表：角色列扩容为 7 级，新增 部门 / 电子签名
--    2) 合同表：新增 单据类型/申请部门/客户名称/业务类型/当前审批步序
--    3) 审批表：新增 步序/审批角色/电子签名快照
--    4) 旧角色数据迁移（staff/leader/normal → 7 级角色）
--  注意: 本脚本为一次性升级，重复执行会因列已存在而报错。
-- =============================================================
USE `sd_publish_scm`;

-- ---- 1. sys_user ----
ALTER TABLE `sys_user`
  MODIFY COLUMN `role` VARCHAR(32) NOT NULL DEFAULT 'business_handler' COMMENT '角色(7级)';
ALTER TABLE `sys_user`
  ADD COLUMN `department` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '所属部门' AFTER `role`;
ALTER TABLE `sys_user`
  ADD COLUMN `signature` TEXT NULL COMMENT '电子签名(图片data-uri或路径)' AFTER `department`;

-- 旧角色 → 新 7 级角色映射
UPDATE `sys_user` SET `role` = 'business_handler'  WHERE `role` = 'staff';
UPDATE `sys_user` SET `role` = 'business_reviewer' WHERE `role` = 'normal';
UPDATE `sys_user` SET `role` = 'invest_director'   WHERE `role` = 'leader' AND `is_superuser` = 1;
UPDATE `sys_user` SET `role` = 'scm_director'       WHERE `role` = 'leader' AND `is_superuser` = 0;

-- ---- 2. biz_contract ----
ALTER TABLE `biz_contract`
  ADD COLUMN `contract_type` VARCHAR(16)  NOT NULL DEFAULT 'payment' COMMENT '单据类型 payment/business' AFTER `remark`;
ALTER TABLE `biz_contract`
  ADD COLUMN `department`    VARCHAR(64)  NOT NULL DEFAULT ''        COMMENT '申请部门'   AFTER `contract_type`;
ALTER TABLE `biz_contract`
  ADD COLUMN `customer_name` VARCHAR(200) NOT NULL DEFAULT ''        COMMENT '客户名称'   AFTER `department`;
ALTER TABLE `biz_contract`
  ADD COLUMN `business_type` VARCHAR(64)  NOT NULL DEFAULT ''        COMMENT '业务类型'   AFTER `customer_name`;
ALTER TABLE `biz_contract`
  ADD COLUMN `current_step`  INT          NOT NULL DEFAULT 0         COMMENT '当前审批步序' AFTER `status`;

-- 历史 pending 合同规范化到业务复核环节
UPDATE `biz_contract` SET `current_step` = 1 WHERE `status` = 'pending';

-- ---- 3. biz_approval ----
ALTER TABLE `biz_approval`
  ADD COLUMN `step`               INT         NOT NULL DEFAULT 0  COMMENT '审批步序'       AFTER `approver_id`;
ALTER TABLE `biz_approval`
  ADD COLUMN `approver_role`      VARCHAR(32) NOT NULL DEFAULT '' COMMENT '审批人角色'     AFTER `step`;
ALTER TABLE `biz_approval`
  ADD COLUMN `signature_snapshot` TEXT       NULL               COMMENT '电子签名快照'   AFTER `comment`;

-- 回填历史审批记录的审批人角色（取其迁移后的角色）
UPDATE `biz_approval` a
  JOIN `sys_user` u ON a.`approver_id` = u.`id`
  SET a.`approver_role` = u.`role`
  WHERE a.`approver_role` = '';

SELECT '阶段一&二 迁移完成' AS message;
