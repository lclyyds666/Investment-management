# AI 助手客户端 UUID 兼容修复设计

## 背景

AI 助手提交消息时使用 `crypto.randomUUID()` 生成 `client_message_id`。生产站点当前通过 HTTP 访问，浏览器不会在该上下文提供 `randomUUID()`，导致消息发送在发起网络请求前直接失败。后端要求 `client_message_id` 为合法 UUID，并依赖该字段实现同一会话内的重复提交保护。

## 目标

- 在支持 `crypto.randomUUID()` 的浏览器中保持现有行为。
- 在 HTTP 或缺少 `randomUUID()` 的浏览器中生成合法的 RFC 4122 UUID v4。
- 保持现有重试语义：同一失败问题复用原 `client_message_id`，新问题生成新 ID。
- 不修改后端接口、数据库约束或 SSE 流程。

## 方案

新增独立 UUID 工具函数，按以下顺序生成 ID：

1. `globalThis.crypto.randomUUID()` 可用时直接调用。
2. 否则使用 `globalThis.crypto.getRandomValues()` 生成 16 字节随机数，设置 UUID v4 的版本位和变体位后格式化。
3. 若浏览器连 `getRandomValues()` 也不支持，使用时间、性能计时值和 `Math.random()` 生成符合 UUID v4 格式的兼容值。该值只用于提交幂等标识，不作为安全密钥。

AI 助手 Store 只调用该工具，不再直接访问浏览器的 `crypto.randomUUID()`。

## 数据流

```text
用户提交问题
  → 检查是否为同内容重试
  → 重试：复用原 client_message_id
  → 新提交：调用 UUID 兼容工具
  → 构造乐观用户消息
  → 发送 SSE 请求
```

## 异常与安全边界

- 工具函数始终返回后端可接受的 UUID 字符串，避免把浏览器能力错误暴露到页面。
- UUID 是幂等键，不承担身份认证、授权、加密或签名职责。
- HTTPS 仍需独立推进；本修复只恢复当前 HTTP 环境下的助手发送能力，不解决 HTTP 明文传输风险。

## 测试

- 原生 `randomUUID()` 路径返回原生值。
- 缺少 `randomUUID()` 时，`getRandomValues()` 路径生成符合 UUID v4 版本位、变体位和格式的值。
- 缺少全部 Web Crypto 能力时，最终回退仍生成合法 UUID v4。
- AI 助手 Store 的失败重试继续复用同一个 ID，新问题继续生成不同 ID。
- 运行 AI 助手 Store 单元测试和前端生产构建。

## 非目标

- 本次不部署 HTTPS。
- 本次不引入第三方 UUID 依赖。
- 本次不调整后端重复提交规则或数据库结构。
