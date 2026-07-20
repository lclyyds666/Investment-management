-- 文旅业务·门票平台核销业务台账（泉州欧乐堡门票平台，按 scenic_id 数据隔离）
-- 幂等：可重复执行。新库亦可用 `python -m app.db.init_db`（create_all）自动建表。

CREATE TABLE IF NOT EXISTS `biz_ticket_ledger` (
  `id`                INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `scenic_id`         VARCHAR(64) NOT NULL COMMENT '景区ID(作用域键)',
  `row_no`            INT NOT NULL DEFAULT 0 COMMENT '行序(稳定排序)',
  `pay_date`          DATE NULL COMMENT '付款日期(手工)',
  `platform`          VARCHAR(32) NOT NULL DEFAULT '' COMMENT '平台(抖音/美团/携程/同程)',
  `ticket_product`    VARCHAR(200) NOT NULL DEFAULT '水上世界/童话世界/海洋王国' COMMENT '景区门票产品名(默认固定)',
  `check_date_text`   VARCHAR(64) NOT NULL DEFAULT '' COMMENT '核对日期(自动,周期跨度)',
  `period_text`       VARCHAR(64) NOT NULL DEFAULT '' COMMENT '对账周期文本(自动)',
  `period_start`      DATE NULL COMMENT '对账周期起(自动)',
  `period_end`        DATE NULL COMMENT '对账周期止(自动)',
  `supplier_received` DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '服务商到账金额(明细算)',
  `publisher_due`     DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '出版应得到账金额B(计算基数)',
  `hexiao_amount`     DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '景区核销金额 = B×核销率',
  `jinying_amount`    DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '锦盈结算金额 = 景区核销+实收服务费',
  `service_fee`       DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '实收服务费 = B×服务费率',
  `rate_hexiao`       DECIMAL(6,4) NOT NULL DEFAULT 0.9000 COMMENT '景区核销率(默认0.90)',
  `rate_fee`          DECIMAL(6,4) NOT NULL DEFAULT 0.0400 COMMENT '实收服务费率(默认0.04)',
  `order_count`       INT NOT NULL DEFAULT 0 COMMENT '核销订单数',
  `repay_date`        DATE NULL COMMENT '回款日期(手工)',
  `repay_amount`      DECIMAL(18,2) NULL COMMENT '回款金额(手工)',
  `source_file`       VARCHAR(255) NOT NULL DEFAULT '' COMMENT '来源Excel文件名',
  `uploaded_by`       INT NULL COMMENT '上传/创建人',
  `created_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_ticket_ledger_sid` (`scenic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文旅业务门票平台核销业务台账';
