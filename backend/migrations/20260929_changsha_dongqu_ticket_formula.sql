-- Update only Changsha Dongqu ticket rates. Re-running is idempotent.
UPDATE `biz_scenic_config`
SET
  `rate_hexiao` = 0.93,
  `rate_settle` = 0.96,
  `commission_rate` = 0.18
WHERE `scenic_id` = 'changsha-dongqu';
