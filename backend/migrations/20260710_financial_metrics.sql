-- =============================================================
--  财务经营指标 迁移脚本（2026-07-10）
--  新增：平台对账单回款指标表 + 投入成本配置表
--  说明：运行库执行本脚本升级；新库由 init.sql / init_db 建表。
-- =============================================================
USE `sd_publish_scm`;

-- 平台对账单财务指标（抖音/美团/携程，按账期）
CREATE TABLE IF NOT EXISTS `biz_financial_metrics` (
  `id`             INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  `platform`       VARCHAR(16)   NOT NULL                COMMENT '平台 douyin/meituan/ctrip',
  `period`         VARCHAR(32)   NOT NULL                COMMENT '账期，如 2026-06-24~06-30',
  `realized_scale` DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '已实现业务规模(出版应得到账金额)',
  `gross_income`   DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '已实现业务毛收入(应扣出版预付/回款)',
  `gmv`            DECIMAL(18,2)          DEFAULT NULL    COMMENT '订单实收GMV(可选)',
  `order_count`    INT           NOT NULL DEFAULT 0      COMMENT '订单数',
  `room_nights`    INT           NOT NULL DEFAULT 0      COMMENT '间夜',
  `created_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_platform_period` (`platform`, `period`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台对账单财务指标';

-- 投入成本配置（单行）
CREATE TABLE IF NOT EXISTS `biz_finance_config` (
  `id`                  INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
  `total_invested_cost` DECIMAL(18,2) NOT NULL DEFAULT 0.00   COMMENT '投入成本(手工录入)',
  `created_at`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='财务投入成本配置';

SELECT '财务经营指标迁移完成（biz_financial_metrics + biz_finance_config）' AS message;
