-- =============================================================
--  门票平台核销台账·期次递推与明细源文件 迁移脚本（2026-07-22）
--  新增 biz_ticket_ledger 列：
--    supplier_commission  服务商佣金(手工,默认0)——出版应得=服务商到账-服务商佣金
--    payment_amount       付款金额(手工,期次递推输入)
--    pending_writeoff     景区待核销金额(滚动余额,后端集中记录)
--    detail_stored/detail_name  对账明细源文件落盘名/原始名(供预览/下载)
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。
--        使用 information_schema 守卫，可安全重复执行（幂等）。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__tl_add_col_if_absent`;
DELIMITER $$
CREATE PROCEDURE `__tl_add_col_if_absent`(IN col VARCHAR(64), IN ddl VARCHAR(500))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'biz_ticket_ledger'
      AND COLUMN_NAME = col
  ) THEN
    SET @s = CONCAT('ALTER TABLE `biz_ticket_ledger` ADD COLUMN ', ddl);
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

CALL `__tl_add_col_if_absent`('supplier_commission', "`supplier_commission` DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '服务商佣金(手工,默认0)' AFTER `supplier_received`");
CALL `__tl_add_col_if_absent`('payment_amount',      "`payment_amount` DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '付款金额(手工,期次递推输入)' AFTER `hexiao_amount`");
CALL `__tl_add_col_if_absent`('pending_writeoff',    "`pending_writeoff` DECIMAL(18,2) NOT NULL DEFAULT 0 COMMENT '景区待核销金额(滚动余额)' AFTER `payment_amount`");
CALL `__tl_add_col_if_absent`('detail_stored',       "`detail_stored` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '明细文件磁盘存储名(uuid)' AFTER `source_file`");
CALL `__tl_add_col_if_absent`('detail_name',         "`detail_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '明细文件原始名' AFTER `detail_stored`");

DROP PROCEDURE IF EXISTS `__tl_add_col_if_absent`;

-- 历史行回填：出版应得沿用原 publisher_due（佣金默认0，无需变动）；
-- 景区待核销金额=首期/续期递推，历史数据以「本期核销金额」为负债起点保守回填，
-- 建议升级后由前端重新保存一次以触发后端集中重算滚动余额。
UPDATE `biz_ticket_ledger`
   SET `pending_writeoff` = COALESCE(`payment_amount`,0) - COALESCE(`hexiao_amount`,0)
 WHERE `pending_writeoff` = 0;

SELECT '门票台账期次递推迁移完成（supplier_commission/payment_amount/pending_writeoff/detail_*）。' AS message;
