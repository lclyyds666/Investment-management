-- =============================================================
--  商用级数据打通 迁移脚本（2026-07-10）
--  1) 渠道回传数据表新增列映射字段 mapping，用于汇入经营数据表
--  2) 电子签名列由 TEXT 加宽为 MEDIUMTEXT，兼容真实扫描签名图
--  说明：已存在的运行库执行本脚本即可平滑升级；新库由 init.sql / init_db 建表。
-- =============================================================
USE `sd_publish_scm`;

-- 1. 渠道回传数据：列 → 经营指标映射
ALTER TABLE `biz_channel_data`
  ADD COLUMN `mapping` JSON NULL COMMENT '列映射{date_col,revenue_col,cost_col,order_col,business_line}' AFTER `rows`;

-- 2. 签名列加宽（MEDIUMTEXT 约 16MB）
ALTER TABLE `sys_user`
  MODIFY COLUMN `signature` MEDIUMTEXT COMMENT '电子签名(图片data-uri或路径)';
ALTER TABLE `biz_approval`
  MODIFY COLUMN `signature_snapshot` MEDIUMTEXT COMMENT '电子签名快照';

SELECT '商用级数据打通迁移完成（渠道映射 + 签名列加宽）' AS message;
