-- 操作审计日志（登录日志 + 通用操作日志）
-- 幂等：可重复执行；新库亦可用 `python -m app.db.init_db`(create_all) 自动建表。

CREATE TABLE IF NOT EXISTS `sys_audit_log` (
  `id`          INT NOT NULL AUTO_INCREMENT COMMENT '主键',
  `user_id`     INT NULL COMMENT '操作者ID(登录失败/匿名可空)',
  `username`    VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '操作者账号(快照)',
  `full_name`   VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '操作者姓名(快照)',
  `role`        VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '操作者角色(快照)',
  `action`      VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '动作(login/create/update/delete/approve/export...)',
  `module`      VARCHAR(32)  NOT NULL DEFAULT '' COMMENT '资源模块(auth/contract/approval/user...)',
  `target_desc` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '目标对象描述',
  `method`      VARCHAR(8)   NOT NULL DEFAULT '' COMMENT 'HTTP 方法',
  `path`        VARCHAR(255) NOT NULL DEFAULT '' COMMENT '请求路径',
  `ip`          VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '客户端IP',
  `status`      VARCHAR(16)  NOT NULL DEFAULT 'success' COMMENT '结果(success/fail)',
  `http_status` INT NOT NULL DEFAULT 0 COMMENT 'HTTP 响应码',
  `detail`      TEXT NULL COMMENT '摘要/错误信息(不含敏感字段)',
  `created_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at`  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  KEY `idx_audit_user` (`user_id`),
  KEY `idx_audit_action` (`action`),
  KEY `idx_audit_module` (`module`),
  KEY `idx_audit_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='操作审计日志';

SELECT '操作审计日志表 sys_audit_log 就绪。' AS message;
