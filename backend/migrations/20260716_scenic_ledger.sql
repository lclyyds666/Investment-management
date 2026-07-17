-- 文旅业务·景区核销数据台账（严格按 scenic_id 数据隔离）
-- 幂等：可重复执行。新库亦可用 `python -m app.db.init_db`（create_all）自动建表。

CREATE TABLE IF NOT EXISTS `biz_scenic_ledger` (
  `id`          INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `scenic_id`   VARCHAR(64) NOT NULL COMMENT '景区ID(作用域键)',
  `row_no`      INT NOT NULL DEFAULT 0 COMMENT '行序',
  `data`        JSON NOT NULL COMMENT '单行核销数据(列名→值)',
  `source_file` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '来源Excel文件名',
  `uploaded_by` INT NULL COMMENT '上传人',
  `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_scenic_ledger_sid` (`scenic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文旅业务景区核销台账';
