-- =============================================================
--  法规知识库 迁移脚本（2026-07-16）
--  新增 biz_knowledge_doc 表：存放公司合同法/集团企业制度/法律规范等参考文件全文，
--  供 AI 合同审查作为分析依据调用。
--  说明：新库由 init_db(create_all) 自动建表；运行库执行本脚本（IF NOT EXISTS 幂等）。
-- =============================================================
USE `sd_publish_scm`;

CREATE TABLE IF NOT EXISTS `biz_knowledge_doc` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `title` VARCHAR(200) NOT NULL COMMENT '文件标题',
  `category` VARCHAR(32) NOT NULL DEFAULT '法律规范' COMMENT '分类:公司合同法/集团企业制度/法律规范/其他',
  `filename` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '原始文件名',
  `stored_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '磁盘存储名',
  `file_type` VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'pdf/docx/xlsx',
  `char_count` INT NOT NULL DEFAULT 0 COMMENT '提取字符数',
  `content` MEDIUMTEXT COMMENT '提取的全文(供 AI 审查引用)',
  `uploaded_by` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '上传人',
  `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='法规知识库';

SELECT '法规知识库迁移完成（biz_knowledge_doc）。' AS message;
