-- =============================================================
--  台账结算费率 + 酒店服务费算法 迁移脚本（2026-07-26）
--  1) biz_ticket_ledger：新增 rate_settle（结算费率），回填 = 核销率 + 旧服务费率
--       结算金额 = 出版应得 × 结算费率；服务费 = 结算金额 − 景区核销（数值与旧口径一致）。
--  2) biz_hotel_ledger：新增 fee_algo（服务费算法1/2）、rate_settle（结算费率，算法2）。
--       算法1(默认)=间夜×每间夜服务费；算法2=结算基数×结算费率，服务费=结算−核销。
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建列。幂等，可重复执行。
--  ⚠️ 酒店待核销口径由「平台各自滚动」改为「整期滚动」，升级后建议对存量台账重新保存一次回填。
-- =============================================================
USE `sd_publish_scm`;

DROP PROCEDURE IF EXISTS `__ledger_add_col_if_absent`;
DELIMITER $$
CREATE PROCEDURE `__ledger_add_col_if_absent`(IN tbl VARCHAR(64), IN col VARCHAR(64), IN ddl VARCHAR(500))
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = tbl
      AND COLUMN_NAME = col
  ) THEN
    SET @s = CONCAT('ALTER TABLE `', tbl, '` ADD COLUMN ', ddl);
    PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
  END IF;
END$$
DELIMITER ;

-- 门票台账：结算费率
CALL `__ledger_add_col_if_absent`('biz_ticket_ledger', 'rate_settle',
  "`rate_settle` DECIMAL(6,4) NOT NULL DEFAULT 0.9400 COMMENT '结算费率(结算金额=出版应得×结算费率)' AFTER `rate_hexiao`");

-- 酒店台账：服务费算法 + 结算费率
CALL `__ledger_add_col_if_absent`('biz_hotel_ledger', 'fee_algo',
  "`fee_algo` TINYINT NOT NULL DEFAULT 1 COMMENT '服务费算法(1=间夜×每间夜服务费;2=结算−核销)' AFTER `hexiao_amount`");
CALL `__ledger_add_col_if_absent`('biz_hotel_ledger', 'rate_settle',
  "`rate_settle` DECIMAL(6,4) NOT NULL DEFAULT 0.9400 COMMENT '结算费率(算法2:结算=结算基数×结算费率)' AFTER `fee_per_night`");

DROP PROCEDURE IF EXISTS `__ledger_add_col_if_absent`;

-- 说明：ADD COLUMN NOT NULL DEFAULT 0.9400 已把存量行 rate_settle 填为 0.94，
--       恰等于「默认核销率0.90 + 默认服务费率0.04」，历史台账数值不变，无需再回填。
--       已存的 hexiao/jinying/service_fee 为落库值不受影响；rate_settle 仅在下次编辑重算时生效。

SELECT '台账结算费率/酒店服务费算法 迁移完成（rate_settle / fee_algo）。' AS message;
