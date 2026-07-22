-- 文旅业务·景区酒店平台核销业务台账（泉州欧乐堡，按 scenic_id 数据隔离）
-- 一份对账明细=一期,内含多平台(抖音/美团/携程)→每平台一行。
-- 幂等：可重复执行；新库亦可用 `python -m app.db.init_db`(create_all) 自动建表。

CREATE TABLE IF NOT EXISTS `biz_hotel_ledger` (
  `id`                  INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `scenic_id`           VARCHAR(64) NOT NULL COMMENT '景区ID(作用域键)',
  `row_no`              INT NOT NULL DEFAULT 0 COMMENT '行序',
  `platform`            VARCHAR(32) NOT NULL DEFAULT '' COMMENT '平台(抖音/美团/携程)',
  `hotel_name`          VARCHAR(255) NOT NULL DEFAULT '' COMMENT '酒店名称',
  `check_date_text`     VARCHAR(64) NOT NULL DEFAULT '' COMMENT '核对日期(周期跨度)',
  `period_text`         VARCHAR(64) NOT NULL DEFAULT '' COMMENT '对账周期文本',
  `period_start`        DATE NULL COMMENT '对账周期起(排序键)',
  `period_end`          DATE NULL COMMENT '对账周期止',
  `room_nights`         INT NOT NULL DEFAULT 0 COMMENT '间夜数',
  `base_received`       DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '平台结算原值(抖音=服务商到账;美团/携程=毛额)',
  `supplier_commission` DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '服务商佣金(仅抖音,默认订单实收×6%−达人−团长,可编辑)',
  `settle_base`         DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '结算基数=base_received−佣金',
  `rate_hexiao`         DECIMAL(6,4) NOT NULL DEFAULT 0.9000 COMMENT '景区核销率(默认0.90)',
  `hexiao_amount`       DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '景区核销金额=结算基数×核销率',
  `fee_per_night`       DECIMAL(10,2) NOT NULL DEFAULT 44.00 COMMENT '每间夜服务费(默认44)',
  `service_fee`         DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '服务费=间夜×每间夜服务费',
  `jinying_amount`      DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '结算金额=景区核销+服务费(原锦盈结算)',
  `payment_amount`      DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '付款金额(手工,隐藏,参与递推)',
  `pending_writeoff`    DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '景区待核销金额(按平台滚动余额)',
  `repay_date`          DATE NULL COMMENT '回款日期(手工)',
  `repay_amount`        DECIMAL(18,2) NULL COMMENT '回款金额(手工)',
  `order_count`         INT NOT NULL DEFAULT 0 COMMENT '订单数',
  `source_file`         VARCHAR(255) NOT NULL DEFAULT '' COMMENT '来源Excel文件名',
  `detail_stored`       VARCHAR(255) NOT NULL DEFAULT '' COMMENT '明细文件磁盘存储名(uuid)',
  `detail_name`         VARCHAR(255) NOT NULL DEFAULT '' COMMENT '明细文件原始名',
  `uploaded_by`         INT NULL COMMENT '上传/创建人',
  `created_at`          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_hotel_ledger_sid` (`scenic_id`),
  KEY `idx_hotel_ledger_period` (`scenic_id`, `period_start`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文旅业务景区酒店平台核销业务台账';

SELECT '酒店平台核销台账表 biz_hotel_ledger 就绪。' AS message;
