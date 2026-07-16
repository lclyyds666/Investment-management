-- 审批中心：两套独立审批单工作流（业务付款审批单 / 业务审批单）
-- 幂等：可重复执行。新库亦可用 `python -m app.db.init_db`（create_all）自动建表。
-- 生产上线后须执行本脚本 + `pip install -r requirements.txt`（新增 Pillow，用于签章图片嵌入）。

-- 审批单主表
CREATE TABLE IF NOT EXISTS `biz_approval_form` (
  `id`                INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `form_type`         VARCHAR(16) NOT NULL COMMENT '单据类型 payment/business',
  `department`        VARCHAR(64) NOT NULL DEFAULT '' COMMENT '申请部门',
  `apply_date`        DATE NULL COMMENT '申请日期',
  `customer_id`       INT NULL COMMENT '客户(外键 biz_customer)',
  `customer_name`     VARCHAR(200) NOT NULL DEFAULT '' COMMENT '客户名称(快照)',
  `business_type`     VARCHAR(64) NOT NULL DEFAULT '' COMMENT '业务类型',
  `business_desc`     VARCHAR(500) NOT NULL DEFAULT '详见合同' COMMENT '业务情况',
  `contract_no`       VARCHAR(64) NOT NULL DEFAULT '' COMMENT '合同编号',
  `remark`            TEXT COMMENT '备注',
  `amount`            DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '付款金额(元)',
  `amount_words`      VARCHAR(128) NOT NULL DEFAULT '' COMMENT '付款金额大写',
  `bank_name`         VARCHAR(128) NOT NULL DEFAULT '' COMMENT '开户行',
  `bank_account`      VARCHAR(64) NOT NULL DEFAULT '' COMMENT '银行账号',
  `attachment_name`   VARCHAR(255) NOT NULL DEFAULT '' COMMENT '合同附件原始文件名',
  `attachment_stored` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '合同附件磁盘存储名',
  `status`            VARCHAR(16) NOT NULL DEFAULT 'draft' COMMENT '状态 draft/pending/approved/rejected',
  `current_step`      INT NOT NULL DEFAULT 0 COMMENT '当前待审批步序',
  `created_by`        INT NOT NULL COMMENT '创建人(业务经办)',
  `created_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_form_contract_no` (`contract_no`),
  KEY `idx_form_customer` (`customer_id`),
  KEY `idx_form_created_by` (`created_by`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审批单主表(审批中心)';

-- 审批流转/电子签章审计日志
CREATE TABLE IF NOT EXISTS `biz_approval_form_action` (
  `id`                 INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `form_id`            INT NOT NULL COMMENT '关联审批单',
  `approver_id`        INT NOT NULL COMMENT '审批人',
  `step`               INT NOT NULL DEFAULT 0 COMMENT '审批步序',
  `approver_role`      VARCHAR(32) NOT NULL DEFAULT '' COMMENT '审批人当时角色值',
  `action`             VARCHAR(16) NOT NULL COMMENT '动作 approve/reject',
  `comment`            TEXT COMMENT '审批意见/驳回原因',
  `signature_snapshot` MEDIUMTEXT NULL COMMENT '电子签名快照',
  `created_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_action_form` (`form_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审批单流转/签章日志';
