-- =============================================================
--  客户 AI 尽职调查 迁移脚本（2026-07-14）
--  新增两张表：准入资料(逐页文本+关键信息) + 调研报告(四段+建议+来源)
--  说明：运行库执行本脚本升级；新库由 init_db(create_all) 自动建表。
--        CREATE TABLE IF NOT EXISTS，可安全重复执行（幂等）。
-- =============================================================
USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `biz_customer_material` (
  `id`          INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
  `customer_id` INT          NOT NULL                COMMENT '客户ID',
  `filename`    VARCHAR(255) NOT NULL                COMMENT '原始文件名',
  `stored_name` VARCHAR(255) NOT NULL DEFAULT ''     COMMENT '磁盘存储名(UPLOAD_DIR下)',
  `file_type`   VARCHAR(16)  NOT NULL DEFAULT ''     COMMENT 'pdf/docx',
  `page_count`  INT          NOT NULL DEFAULT 0      COMMENT '页数',
  `char_count`  INT          NOT NULL DEFAULT 0      COMMENT '提取字符数',
  `pages`       JSON                  DEFAULT NULL   COMMENT '逐页文本[{page,text}]',
  `key_info`    JSON                  DEFAULT NULL   COMMENT '正则抽取的关键信息',
  `uploaded_by` VARCHAR(64)  NOT NULL DEFAULT ''     COMMENT '上传人',
  `created_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_material_customer` (`customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户准入资料(解析后)';

CREATE TABLE IF NOT EXISTS `biz_customer_research` (
  `id`             INT         NOT NULL AUTO_INCREMENT COMMENT '主键',
  `customer_id`    INT         NOT NULL                COMMENT '客户ID',
  `recommendation` VARCHAR(16) NOT NULL DEFAULT ''     COMMENT '合作建议:优先合作/谨慎合作/严禁合作',
  `sections`       JSON                 DEFAULT NULL   COMMENT '四段报告',
  `report_md`      TEXT                                COMMENT '渲染后的Markdown报告全文',
  `sources`        JSON                 DEFAULT NULL   COMMENT '信息来源[{type,title,ref}]',
  `engine`         VARCHAR(16) NOT NULL DEFAULT ''     COMMENT 'deepseek/rule',
  `searched`       TINYINT(1)  NOT NULL DEFAULT 0      COMMENT '是否成功联网检索',
  `search_count`   INT         NOT NULL DEFAULT 0      COMMENT '外部资讯条数',
  `created_by`     VARCHAR(64) NOT NULL DEFAULT ''     COMMENT '生成人',
  `created_at`     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_research_customer` (`customer_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='客户尽职调查报告';

SELECT '客户 AI 尽调迁移完成（biz_customer_material + biz_customer_research）' AS message;
