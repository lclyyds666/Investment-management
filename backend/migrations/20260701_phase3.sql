-- =============================================================
--  阶段三 迁移脚本：主数据管理与多渠道数据集成
--  新增表：客户档案 / 渠道平台 / 渠道回传数据 / 发票
--  说明：运行库亦可用 `python -m app.db.init_db` 自动建表并写入演示数据。
-- =============================================================
USE `sd_publish_scm`;

-- 客户档案
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

-- 渠道平台
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

-- 渠道回传数据
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

-- 发票
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

SELECT '阶段三 迁移完成（演示数据可由 python -m app.db.init_db 写入）' AS message;
