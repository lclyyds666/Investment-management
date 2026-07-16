-- =============================================================
--  管理员角色更名（2026-07-18）
--  admin 账号角色：invest_director（投资公司分管领导）→ info_maintainer（信息维护）
--  说明：
--    · 「信息维护」是超管账号的身份标签，不计入 7 级审批链；
--      全部功能/权限来自 is_superuser=1（本迁移一并确保为超管）。
--    · 真实「投资公司分管领导」用户(如 inv)保持 invest_director 不变。
--    · role 列为 varchar(32)，无需 ALTER；幂等，可重复执行。
-- =============================================================
USE `sd_publish_scm`;

UPDATE `sys_user`
   SET `role` = 'info_maintainer',
       `full_name` = '信息维护',
       `is_superuser` = 1
 WHERE `username` = 'admin';

SELECT id, username, full_name, role, is_superuser
  FROM `sys_user` WHERE `username` = 'admin';
