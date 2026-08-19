# 法务风控模块部署与运维

本文用于投资公司法务风控模块的首次上线、日常维护和故障排查。数据库为 MySQL 8.0+，后端服务目录默认为 `/opt/sd-scm/backend`。

## 1. 固定业务口径

- 案件主状态固定为：`审查立案`、`审理中`、`已判决`、`执行中`、`终本`、`已结案`。
- 裁判/结果类型固定为：`一审`、`二审`、`再审`、`调解`、`和解`、`执行`、`其他`。
- 案件不维护风险等级，不统计“重大案件”。
- 业务人员与法务风控人员拥有相同的法务业务权限。
- 董事长、总经理、副总经理使用管理层只读权限，可查看案件、统计和管理报表。
- 超级管理员拥有全部权限；外聘法律顾问仅能访问被分配且仍在有效期内的案件。

## 2. 上线步骤

先备份数据库和附件目录，再按顺序执行迁移：

```bash
mysqldump -u root -p sd_publish_scm > /opt/sd-scm/backups/legal-risk-before.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260814_legal_risk_foundation.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260814_legal_risk_domain.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260814_legal_risk_hardening.sql
mysql -u root -p sd_publish_scm < backend/migrations/20260818_legal_alert_generation.sql
```

四个迁移均可重复执行。`foundation` 为用户补充手机号和钉钉提醒开关；`domain` 创建法务独立数据表；`hardening` 为已有法务数据域补充预警投递并发领取字段和索引；`legal_alert_generation` 允许期限日期改回历史值时生成新的活动预警。新环境也应按上述顺序完整执行。

准备附件目录并限制访问权限：

```bash
install -d -m 750 -o www-data -g www-data /opt/sd-scm/backend/uploads/legal-risk
```

在 `backend/.env` 配置：

```dotenv
UPLOAD_DIR=/opt/sd-scm/backend/uploads
DINGTALK_LEGAL_ALERT_ENABLED=true
DINGTALK_LEGAL_ALERT_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=实际令牌
DINGTALK_LEGAL_ALERT_SECRET=SEC实际加签密钥
LEGAL_ALERT_TIMEZONE=Asia/Shanghai
```

合同 AI 审查和生产钉钉预警还需要在服务器本地 `.env` 中补充以下配置示例。以下值均为占位符，请由运维人员通过安全渠道填入实际值，严禁提交到 Git、构建产物或日志：

```dotenv
DEEPSEEK_API_KEY=实际密钥
DINGTALK_LEGAL_ALERT_ENABLED=true
DINGTALK_LEGAL_ALERT_WEBHOOK=实际Webhook
DINGTALK_LEGAL_ALERT_SECRET=实际Secret
```

部署前先备份数据库、上传文件和环境文件；至少覆盖以下路径（按实际部署目录替换 `/opt/sd-scm`）：

```bash
backup_dir="/opt/sd-scm/backups/legal-contract-$(date +%Y%m%d%H%M%S)"
mkdir -p "$backup_dir"
cp -a /opt/sd-scm/backend/uploads/contract_* "$backup_dir/" 2>/dev/null || true
cp -a /opt/sd-scm/backend/uploads/knowledge_base "$backup_dir/"
cp -a /opt/sd-scm/backend/uploads/legal-risk "$backup_dir/"
cp -a /opt/sd-scm/backend/.env "$backup_dir/.env"
```

备份目录需限制为仅服务账号和运维管理员可读。

复制并启用定时任务：

```bash
cp deploy/sd-scm-legal-alert-*.service deploy/sd-scm-legal-alert-*.timer /etc/systemd/system/
cp deploy/sd-scm-legal-import-cleanup.service deploy/sd-scm-legal-import-cleanup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sd-scm-legal-alert-scan.timer sd-scm-legal-alert-retry.timer sd-scm-legal-import-cleanup.timer
systemctl restart sd-scm-backend
systemctl list-timers 'sd-scm-legal-*'
```

`scan` 每天北京时间 09:00 扫描；`retry` 每五分钟检查待补偿投递；`import-cleanup` 每天北京时间 03:30 删除已过期的导入预检文件和记录。失败投递按 5、30、120 分钟的有界间隔重试，超过三次后保留失败记录，供页面手工重发。

## 3. 钉钉机器人

1. 在法务风控工作群添加“自定义机器人”。
2. 安全设置选择“加签”，把 Webhook 和 `SEC...` 密钥写入 `.env`。
3. 重启后端并重新启动法务定时器，使新环境变量生效。
4. 超级管理员进入法务风控的预警任务页发送测试消息。
5. 在用户管理中为责任人填写其钉钉绑定手机号，并开启“法务钉钉提醒”。

群成员都会收到机器人消息；开启提醒且手机号匹配的案件责任人会被手机号 `@`。消息只包含案件编号、预警类型和截止日期，不发送案情、金额或当事人敏感信息。

## 4. 预警与处置

系统扫描查冻扣到期、申请执行、开庭、缴费/材料期限、其他期限和终本持续监控六类预警。期限任务新增后立即进入预警任务列表，提醒窗口前不发送通知；修改来源日期或类型时，旧预警会自动关闭并按新周期生成；删除来源期限后关联预警自动关闭，重复扫描不会重复创建相同周期预警。

手工检查命令：

```bash
cd /opt/sd-scm/backend
sudo -u www-data .venv/bin/python -m app.jobs.legal_alert_scan
sudo -u www-data .venv/bin/python -m app.jobs.legal_alert_retry
sudo -u www-data .venv/bin/python -m app.jobs.legal_import_cleanup
journalctl -u sd-scm-legal-alert-scan.service -u sd-scm-legal-alert-retry.service -u sd-scm-legal-import-cleanup.service -n 100 --no-pager
```

常见状态：

- `channel_unconfigured`：检查启用开关和 Webhook，然后重启服务并在页面手工重发。
- 钉钉返回签名错误：核对 `SEC` 密钥、服务器时间和时区同步。
- 群消息成功但未 `@`：核对用户手机号、提醒开关，以及该手机号对应的钉钉账号是否在群内。
- 无预警生成：确认案件已正式立案、日期字段已填写且预警来源未标记完成。

## 5. Excel 与附件

- 只使用系统下载的当前标准模板；先“预检”，处理错误并确认警告后再事务导入。
- 正式案件必须至少有一名原告和一名被告；外部案件编号不可重复。
- 允许附件：PDF、Word、Excel、PNG、JPG/JPEG，单文件最大 50MB。
- 附件只通过鉴权接口预览或下载，磁盘文件名为随机值；归档案件不能再删除附件。
- 数据库备份不包含附件，必须同时备份 `UPLOAD_DIR/legal-risk`。

## 6. 验收与回退

上线后至少验证：六个固定状态、草稿转正式案件、八个明细页签、附件上传下载、六类预警、钉钉测试、统计导出、模板预检和权限矩阵。

出现严重故障时先停止定时器，避免继续生成投递：

```bash
systemctl disable --now sd-scm-legal-alert-scan.timer sd-scm-legal-alert-retry.timer sd-scm-legal-import-cleanup.timer
```

然后回退应用版本并恢复数据库/附件备份。不要直接删除法务表；需要保留审计、导入批次和投递历史用于追溯。

## 7. 合同 AI 与生产验收

完成部署后按以下顺序验收，并保存脱敏后的命令输出：

1. 登录具有 `invest.legal.cases` 资源和 `supply.contract.view` 权限的账号，访问法务合同路由 `/investment/legal-risk/contracts`；确认合同列表、详情和权限控制均可用。
2. 使用现有合同发起一次 AI 审查，检查接口响应中的 `engine=deepseek`（或等价 JSON 字段 `engine: "deepseek"`），不得在输出中打印 API Key。
3. 在后端环境中调用 `DingTalkClient.send_test`，确认返回 `status=sent`；若返回 `channel_unconfigured` 或签名错误，检查开关、Webhook、Secret 和服务器时钟后重试。
4. 检查服务健康和定时器状态：

   ```bash
   curl -fsS http://127.0.0.1/api/v1/health
   systemctl is-active sd-scm-backend nginx sd-scm-legal-alert-scan.timer sd-scm-legal-alert-retry.timer
   ```

5. 验收通过后核对当前 `REVISION` 与发布的 `main` 版本一致；任一步失败时先按本页回退步骤停用定时器，再恢复应用、数据库和上述上传目录备份。
