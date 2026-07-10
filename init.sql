-- =============================================================
--  山东出版供应链管理公司业务平台 - 数据库初始化脚本
--  适用数据库: MySQL 8.0+ (InnoDB / utf8mb4)
--
--  使用方式:
--    1) 用 Navicat / DBeaver / MySQL Workbench 打开本文件后执行；
--       或命令行: mysql -u root -p < init.sql
--    2) 脚本会自动创建数据库 sd_publish_scm 并建表、写入种子数据。
--
--  说明: 表结构与后端 SQLAlchemy 模型保持一致（7 级组织角色 + 审批流）。
--        所有种子账号密码均为 123456 (bcrypt 加密存储)。
--        员工电子签名默认留空，可在“个人设置”上传，或运行
--        python -m app.db.init_db 自动生成 Mock 签名。
-- =============================================================

CREATE DATABASE IF NOT EXISTS `sd_publish_scm`
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `sd_publish_scm`;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `biz_approval`;
DROP TABLE IF EXISTS `biz_contract`;
DROP TABLE IF EXISTS `biz_operation_data`;
DROP TABLE IF EXISTS `sys_user`;
SET FOREIGN_KEY_CHECKS = 1;


-- -------------------------------------------------------------
-- 1. 用户表（含组织架构与电子签名资产）
-- -------------------------------------------------------------
CREATE TABLE `sys_user` (
  `id`              INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  `username`        VARCHAR(64)  NOT NULL                COMMENT '登录账号',
  `full_name`       VARCHAR(64)  NOT NULL DEFAULT ''     COMMENT '姓名',
  `hashed_password` VARCHAR(128) NOT NULL                COMMENT '密码哈希(bcrypt)',
  `role`            VARCHAR(32)  NOT NULL DEFAULT 'business_handler'
      COMMENT '7级角色: business_handler/business_reviewer/risk_auditor/finance_handler/finance_reviewer/scm_director/invest_director',
  `department`      VARCHAR(64)  NOT NULL DEFAULT ''     COMMENT '所属部门',
  `signature`       TEXT                                 COMMENT '电子签名(图片data-uri或路径)',
  `is_active`       TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '是否启用',
  `is_superuser`    TINYINT(1)   NOT NULL DEFAULT 0      COMMENT '是否超级管理员',
  `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_user_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='系统用户表';


-- -------------------------------------------------------------
-- 2. 合同表（合同全生命周期 + 审批流状态）
-- -------------------------------------------------------------
CREATE TABLE `biz_contract` (
  `id`            INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  `contract_no`   VARCHAR(64)   NOT NULL                COMMENT '合同编号',
  `title`         VARCHAR(200)  NOT NULL                COMMENT '合同名称',
  `party_a`       VARCHAR(200)  NOT NULL DEFAULT ''     COMMENT '甲方',
  `party_b`       VARCHAR(200)  NOT NULL DEFAULT ''     COMMENT '乙方',
  `amount`        DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '合同金额(元)',
  `sign_date`     DATE          DEFAULT NULL            COMMENT '签订日期',
  `remark`        TEXT                                  COMMENT '备注',
  `contract_type` VARCHAR(16)   NOT NULL DEFAULT 'payment' COMMENT '单据类型 payment=付款审批单 / business=业务审批单',
  `department`    VARCHAR(64)   NOT NULL DEFAULT ''     COMMENT '申请部门',
  `customer_name` VARCHAR(200)  NOT NULL DEFAULT ''     COMMENT '客户名称',
  `business_type` VARCHAR(64)   NOT NULL DEFAULT ''     COMMENT '业务类型',
  `status`        VARCHAR(16)   NOT NULL DEFAULT 'draft' COMMENT '状态: draft/pending/approved/rejected',
  `current_step`  INT           NOT NULL DEFAULT 0      COMMENT '当前审批步序(0-6)',
  `created_by`    INT           NOT NULL                COMMENT '创建人(业务经办), 关联 sys_user.id',
  `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_contract_no` (`contract_no`),
  KEY `idx_contract_created_by` (`created_by`),
  CONSTRAINT `fk_contract_user` FOREIGN KEY (`created_by`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='合同表';


-- -------------------------------------------------------------
-- 3. 审批记录表（合规审计日志 + 电子签章快照）
-- -------------------------------------------------------------
CREATE TABLE `biz_approval` (
  `id`                 INT         NOT NULL AUTO_INCREMENT COMMENT '主键',
  `contract_id`        INT         NOT NULL                COMMENT '关联合同 biz_contract.id',
  `approver_id`        INT         NOT NULL                COMMENT '审批人, 关联 sys_user.id',
  `step`               INT         NOT NULL DEFAULT 0      COMMENT '审批步序(0-6)',
  `approver_role`      VARCHAR(32) NOT NULL DEFAULT ''     COMMENT '审批人当时角色',
  `action`             VARCHAR(16) NOT NULL                COMMENT '动作: approve=通过 / reject=驳回',
  `comment`            TEXT                                COMMENT '审批意见/驳回原因',
  `signature_snapshot` TEXT                                COMMENT '电子签名快照',
  `created_at`         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`         DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_approval_contract` (`contract_id`),
  KEY `idx_approval_approver` (`approver_id`),
  CONSTRAINT `fk_approval_contract` FOREIGN KEY (`contract_id`) REFERENCES `biz_contract` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_approval_user`     FOREIGN KEY (`approver_id`) REFERENCES `sys_user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='合同审批记录表';


-- -------------------------------------------------------------
-- 4. 经营数据表 (用于可视化看板)
-- -------------------------------------------------------------
CREATE TABLE `biz_operation_data` (
  `id`            INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  `year`          INT           NOT NULL                COMMENT '年份',
  `month`         INT           NOT NULL                COMMENT '月份 1-12',
  `business_line` VARCHAR(64)   NOT NULL                COMMENT '业务条线',
  `revenue`       DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '营收(元)',
  `cost`          DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '成本(元)',
  `profit`        DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '利润(元)',
  `order_count`   INT           NOT NULL DEFAULT 0      COMMENT '订单数',
  `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_period_line` (`year`, `month`, `business_line`),
  KEY `idx_operation_year` (`year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='经营数据表';


-- =============================================================
--  种子数据
-- =============================================================

-- 8 个默认账号（admin 超管 + 7 级角色各一），密码均为 123456 (bcrypt 哈希)。
-- 电子签名默认为空，可在“个人设置”上传或运行 init_db 生成 Mock 签名。
INSERT INTO `sys_user` (`id`, `username`, `full_name`, `hashed_password`, `role`, `department`, `is_active`, `is_superuser`) VALUES
  (1, 'admin',  '系统管理员', '$2b$12$eb./yT6rZ1TxTSj6JYdyfe8OCvHTB3NY4Op2kwDYHqqKLls/N43nS', 'invest_director',   '信息中心',   1, 1),
  (2, 'op',     '张经办',     '$2b$12$eb./yT6rZ1TxTSj6JYdyfe8OCvHTB3NY4Op2kwDYHqqKLls/N43nS', 'business_handler',  '业务部',     1, 0),
  (3, 'review', '李复核',     '$2b$12$eb./yT6rZ1TxTSj6JYdyfe8OCvHTB3NY4Op2kwDYHqqKLls/N43nS', 'business_reviewer', '业务部',     1, 0),
  (4, 'risk',   '王风控',     '$2b$12$eb./yT6rZ1TxTSj6JYdyfe8OCvHTB3NY4Op2kwDYHqqKLls/N43nS', 'risk_auditor',      '风控合规部', 1, 0),
  (5, 'fin',    '赵财办',     '$2b$12$eb./yT6rZ1TxTSj6JYdyfe8OCvHTB3NY4Op2kwDYHqqKLls/N43nS', 'finance_handler',   '财务部',     1, 0),
  (6, 'finr',   '孙财复',     '$2b$12$eb./yT6rZ1TxTSj6JYdyfe8OCvHTB3NY4Op2kwDYHqqKLls/N43nS', 'finance_reviewer',  '财务部',     1, 0),
  (7, 'scm',    '周供管',     '$2b$12$eb./yT6rZ1TxTSj6JYdyfe8OCvHTB3NY4Op2kwDYHqqKLls/N43nS', 'scm_director',      '供管公司',   1, 0),
  (8, 'inv',    '吴投资',     '$2b$12$eb./yT6rZ1TxTSj6JYdyfe8OCvHTB3NY4Op2kwDYHqqKLls/N43nS', 'invest_director',   '投资公司',   1, 0);

-- 示例合同（创建人均为业务经办 op, id=2），初始为草稿，可在平台内驱动 7 级审批流。
INSERT INTO `biz_contract`
  (`id`, `contract_no`, `title`, `party_a`, `party_b`, `amount`, `sign_date`, `remark`, `contract_type`, `department`, `customer_name`, `business_type`, `status`, `current_step`, `created_by`) VALUES
  (1, 'HT-2026-001', '2026年度教材印制采购合同', '山东出版供应链管理公司', '齐鲁印刷有限公司',   1800000.00, '2026-01-15', '年度框架合同', 'payment',  '业务部', '齐鲁印刷有限公司',   '印刷采购', 'draft', 0, 2),
  (2, 'HT-2026-002', '数字出版平台技术服务合同', '山东出版供应链管理公司', '泉城软件科技有限公司', 600000.00, '2026-02-20', '含一年运维',   'payment',  '业务部', '泉城软件科技有限公司', '技术服务', 'draft', 0, 2),
  (3, 'HT-2026-003', '仓储物流外包服务合同',     '山东出版供应链管理公司', '鲁运物流股份有限公司',  450000.00, NULL,         '草拟中',       'business', '业务部', '鲁运物流股份有限公司', '物流仓储', 'draft', 0, 2);

-- 经营数据: 3 条业务线 × 6 个月 (2026 年)
INSERT INTO `biz_operation_data` (`year`, `month`, `business_line`, `revenue`, `cost`, `profit`, `order_count`) VALUES
  (2026, 1, '图书发行', 1260000.00,  882000.00, 378000.00, 110),
  (2026, 2, '图书发行', 1320000.00,  924000.00, 396000.00, 120),
  (2026, 3, '图书发行', 1380000.00,  966000.00, 414000.00, 130),
  (2026, 4, '图书发行', 1440000.00, 1008000.00, 432000.00, 140),
  (2026, 5, '图书发行', 1500000.00, 1050000.00, 450000.00, 150),
  (2026, 6, '图书发行', 1560000.00, 1092000.00, 468000.00, 160),
  (2026, 1, '数字出版',  840000.00,  588000.00, 252000.00, 110),
  (2026, 2, '数字出版',  880000.00,  616000.00, 264000.00, 120),
  (2026, 3, '数字出版',  920000.00,  644000.00, 276000.00, 130),
  (2026, 4, '数字出版',  960000.00,  672000.00, 288000.00, 140),
  (2026, 5, '数字出版', 1000000.00,  700000.00, 300000.00, 150),
  (2026, 6, '数字出版', 1040000.00,  728000.00, 312000.00, 160),
  (2026, 1, '物流仓储',  525000.00,  367500.00, 157500.00, 110),
  (2026, 2, '物流仓储',  550000.00,  385000.00, 165000.00, 120),
  (2026, 3, '物流仓储',  575000.00,  402500.00, 172500.00, 130),
  (2026, 4, '物流仓储',  600000.00,  420000.00, 180000.00, 140),
  (2026, 5, '物流仓储',  625000.00,  437500.00, 187500.00, 150),
  (2026, 6, '物流仓储',  650000.00,  455000.00, 195000.00, 160);

-- -------------------------------------------------------------
-- 阶段三：主数据与渠道集成表（演示数据由 python -m app.db.init_db 写入）
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `biz_customer` (
  `id`              INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  `customer_code`   VARCHAR(64)  NOT NULL                COMMENT '客户ID/编码',
  `name`            VARCHAR(200) NOT NULL                COMMENT '客户名称',
  `address`         VARCHAR(255) NOT NULL DEFAULT ''     COMMENT '地址',
  `contact`         VARCHAR(64)  NOT NULL DEFAULT ''     COMMENT '联系人',
  `phone`           VARCHAR(32)  NOT NULL DEFAULT ''     COMMENT '电话',
  `admission_files` JSON                                  COMMENT '准入资料附件[{name,url}]',
  `remark`          TEXT                                  COMMENT '备注',
  `created_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_customer_code` (`customer_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户档案';

CREATE TABLE IF NOT EXISTS `biz_channel` (
  `id`          INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  `name`        VARCHAR(100) NOT NULL                COMMENT '平台名称',
  `category`    VARCHAR(16)  NOT NULL DEFAULT 'other' COMMENT '类别 ticket/hotel/ota/other',
  `url`         VARCHAR(255) NOT NULL DEFAULT ''     COMMENT '平台地址',
  `account`     VARCHAR(128) NOT NULL DEFAULT ''     COMMENT '登录账号(Mock)',
  `password`    VARCHAR(128) NOT NULL DEFAULT ''     COMMENT '登录密码(Mock)',
  `logo`        VARCHAR(16)  NOT NULL DEFAULT '🔗'   COMMENT '图标',
  `description` TEXT                                  COMMENT '说明',
  `sort_order`  INT          NOT NULL DEFAULT 0      COMMENT '排序',
  `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道平台';

CREATE TABLE IF NOT EXISTS `biz_channel_data` (
  `id`         INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `channel_id` INT NOT NULL                COMMENT '关联渠道',
  `columns`    JSON                         COMMENT '表头列',
  `rows`       JSON                         COMMENT '数据行(二维数组)',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_channel_data` (`channel_id`),
  CONSTRAINT `fk_channel_data` FOREIGN KEY (`channel_id`) REFERENCES `biz_channel` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道回传数据';

CREATE TABLE IF NOT EXISTS `biz_invoice` (
  `id`            INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  `invoice_title` VARCHAR(200)  NOT NULL                COMMENT '发票抬头',
  `tax_no`        VARCHAR(64)   NOT NULL DEFAULT ''     COMMENT '税号',
  `invoice_type`  VARCHAR(32)   NOT NULL DEFAULT '增值税专用发票' COMMENT '发票类型',
  `amount`        DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '开票金额',
  `status`        VARCHAR(16)   NOT NULL DEFAULT 'pending' COMMENT '状态 pending/issued/void',
  `customer_name` VARCHAR(200)  NOT NULL DEFAULT ''     COMMENT '客户名称',
  `contract_no`   VARCHAR(64)   NOT NULL DEFAULT ''     COMMENT '关联合同编号',
  `issued_date`   DATE          DEFAULT NULL            COMMENT '开票日期',
  `remark`        TEXT                                  COMMENT '备注',
  `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='发票';

-- 完成
SELECT '数据库初始化完成！账号: admin/op/review/risk/fin/finr/scm/inv，密码均为 123456' AS message;
