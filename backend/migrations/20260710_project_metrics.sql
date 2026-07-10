-- =============================================================
--  供管公司项目经营指标 迁移脚本（2026-07-10）
--  新增：项目投入/回款/毛利表 + 财务配置增加可用资金列
--  说明：运行库执行本脚本升级；新库由 init.sql / init_db 建表。
-- =============================================================
USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `biz_project_metrics` (
  `id`              INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  `seq`             INT           NOT NULL DEFAULT 0      COMMENT '序号',
  `project_name`    VARCHAR(200)  NOT NULL                COMMENT '项目名称',
  `platforms`       VARCHAR(200)  NOT NULL DEFAULT ''     COMMENT '平台(标签)',
  `invested_amount` DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '投入金额(元)=现存业务规模/已投入本金',
  `realized_scale`  DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '回款小计(元)=已实现业务规模',
  `gross_profit`    DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '实现毛利(元)=已实现业务毛收入',
  `profit_rate`     DECIMAL(9,4)           DEFAULT NULL   COMMENT '收益率(小数，如0.0473)',
  `pay_date`        DATE                   DEFAULT NULL   COMMENT '付款日期',
  `term_months`     VARCHAR(16)   NOT NULL DEFAULT ''     COMMENT '合同期限(月)',
  `created_at`      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_project_paydate` (`project_name`, `pay_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='供管公司项目经营指标';

-- 财务配置增加可用资金列
ALTER TABLE `biz_finance_config`
  ADD COLUMN `available_funds` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '可用资金(手工录入)' AFTER `total_invested_cost`;

SELECT '项目经营指标迁移完成（biz_project_metrics + available_funds）' AS message;
