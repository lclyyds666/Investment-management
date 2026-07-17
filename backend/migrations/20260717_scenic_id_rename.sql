-- 文旅业务·景区标识符(scenic_id)重构：旧 slug → 与新景区名对齐的拼音标识。
-- 幂等：以旧值为 WHERE 条件、可重复执行；若已改则命中 0 行。
-- 说明：执行时 biz_scenic_ledger 为空表，此脚本为 no-op；保留以同步任何历史/未来数据，
--       保证 DB 里的作用域键与前端 constants/scenic.js 的 id 一致。
--
-- 映射：
--   qihe      -> quancheng-ouleb  (泉城欧乐堡)
--   quanzhou  -> quanzhou-ouleb   (泉州欧乐堡)
--   penglai   -> fuzhou-ouleb     (福州欧乐堡)
--   taishan   -> zunyi-zoo        (遵义动物园)
--   mengshan  -> nanyang-wildlife (南阳森林野生动物世界)

UPDATE `biz_scenic_ledger` SET `scenic_id` = 'quancheng-ouleb' WHERE `scenic_id` = 'qihe';
UPDATE `biz_scenic_ledger` SET `scenic_id` = 'quanzhou-ouleb'  WHERE `scenic_id` = 'quanzhou';
UPDATE `biz_scenic_ledger` SET `scenic_id` = 'fuzhou-ouleb'    WHERE `scenic_id` = 'penglai';
UPDATE `biz_scenic_ledger` SET `scenic_id` = 'zunyi-zoo'       WHERE `scenic_id` = 'taishan';
UPDATE `biz_scenic_ledger` SET `scenic_id` = 'nanyang-wildlife' WHERE `scenic_id` = 'mengshan';
