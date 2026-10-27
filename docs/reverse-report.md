# Chat Smith 逆向报告（com.smartwidgetlabs.chatgpt v8.251229.2）

逆向日期: 2026-10-28 · 纯静态 jadx 全量还原，零动态 · 全链路实测打通

## App 概况

| 项 | 值 |
|---|---|
| 包名 | `com.smartwidgetlabs.chatgpt` |
| 开发商 | VulcanLabs (chatsmith.io) |
| 版本 | 8.251229.2 (1247) |
| 分发 | Telegram "Premium" 重打包版（内置 ApkSignatureKillerEx + bin.mt.signature.KillerApplication） |
| 架构 | Kotlin + Retrofit + OkHttp + Firebase（AppCheck/Auth/Firestore） |
| dex | 8 个，主业务在 classes6.dex，UI 层 com.smartwidgetlabs.chatgpt.* |

## 上游端点拓扑

| 端点 | 用途 | 鉴权 |
|---|---|---|
| `https://api.vulcanlabs.co/smith-auth/api/` | token 发放/刷新 | **无**（device_id 即可） |
| `https://api.vulcanlabs.co/smith-v2/api/` | 聊天主通道 (v7/chat_android, v7/vision_android) | Bearer JWT |
| `https://smith.vulcanlabs.co/api/` | Play Integrity 通道 (v7/chat, v7/vision) | Bearer JWT + X-Firebase-AppCheck |
| `https://api.vulcanlabs.co/smith-nexus/api/` | 运营内容(图片/banner/配置) | 公共头 |
| `https://auth.vulcanlabs.co/api/v1/` | integrity 辅助 | — |
| `https://chatgpt.vulcanlabs.co/api/` | 图片输入通道 | — |

staging: `stg-api.vulcanlabs.co`（同路径结构）。
配置来源：`C1698Qj1.BASE_SERVICE_DEFAULT` 内嵌 JSON（organization `org-ALtcH6ebtaKB4TkFNBeJO8WZ`），支持远程覆盖。

## 鉴权协议

**1) 取 token** — `POST /smith-auth/api/v1/token`
```json
{"device_id":"<任意android_id>","order_id":"","product_id":"","purchase_token":"","subscription_id":""}
```
响应（免费层）：
```json
{"AccessToken":"<JWT HS256 tier=free>","RefreshToken":"","AccessTokenExpiration":"...+30min","RefreshTokenExpiration":"..."}
```
JWT payload: `{"token":"admin","tier":"free","exp":...,"iss":"Vulcanlabs"}` — 随机 device_id 即可无限重放取新 token（实测 30 分钟有效期）。

**2) 聊天** — `POST /smith-v2/api/v7/chat_android`

公共头（OkHttp 拦截器 C0762Ej0/C7853vz 还原）：
```
Content-Type: application/json
Accept: application/json
X-Vulcan-Application-ID: com.smartwidgetlabs.chatgpt
User-Agent: Chat Smith Android, Version 8.251229.2(1247)
X-Vulcan-Request-ID: <常数914948789 + currentTimeMillis>
Anonymous-User-Id: <device_id>
Authorization: Bearer <AccessToken>
X-Auth-Token: <AppCheck token, 免费通道留空>
```

请求体（G41.java 还原，OpenAI 风格）：
```json
{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}],"user":"<device_id>"}
```
可选：`max_tokens`、`nsfw_check:true`、`usage_model:{provider,model}`（新配置模式，实测服务端忽略）、`functions/tools`（create_ai_art 画图钩子）。

响应：OpenAI 形状但 choices 键为**大写 `Message`**：
```json
{"id":"chatcmpl-...","model":"gpt-4o-mini-2024-07-18","choices":[{"Message":{"role":"assistant","content":"..."},"finish_reason":"stop"}],"usage":{...},"error":null}
```

## 错误码表（实测）

| code | message | 含义 |
|---|---|---|
| 14 | Invalid Signature | 缺 Authorization Bearer 头 |
| 17 | Client request failure | 缺公共头（UA/X-Vulcan-Application-ID 等） |
| ERROR_TOKEN_FIREBASE_1002 | Verify token is failed | 走了 v7/chat（需 AppCheck），用 _android 后缀绕开 |

## 模型目录（BotModel.java 还原，21 个）

gpt-5.2 / gpt-5 / gpt-5-mini / gpt-4o / gpt-4o-mini / gpt-4 / gpt-3.5-turbo / o3 /
gemini-3-pro-preview / gemini-3-flash-preview / gemini-2.5-pro / gemini-2.5-flash / gemini-2.5-flash-lite / gemini-2.0-flash-lite / gemini-1.5-pro / gemini-1.5-flash /
deepseek-chat / deepseek-reasoner / grok-4 / grok-4-fast / grok-2

### 模型矩阵实测（免费层）

21 个模型逐一请求 → **全部返回 `gpt-4o-mini-2024-07-18`**。
`usage_model` 绕过（provider: openai/anthropic/google/xai/deepseek）→ 服务端忽略，同样降级。
模型自报身份 "GPT-3.5"。**结论：模型目录是付费墙展示幌子，免费层实质单模型。**
premium 需要 Google Play 购买凭证（order_id/purchase_token 走 orders/api/v1/users/inapp/orders/sync 验证），客户端无法伪造。

## 其他能力面（端点清单，未逐一打通）

- `v1/text2image`、`v1~v3/users/images/{styles/,text/}generations`（文生图，AIArt v3）
- `v1/users/research/jobs/{start,result}` + `sessions/{init,continue}`（Deep Research）
- `v1/users/realtime-search/jobs/{start,result}`（联网搜索）
- `v7/threads*`（Assistant API 风格 threads/runs）
- `v1/users/intentions/detect`、`v1/users/media/images/upload`
- EcoSystem: `subscriptions/api/v1/users/subscription-info`、`orders/...`、`user-management/api/v1/*`（OAuth 多提供商登录）

## 压测数据（2026-10-28）

| 场景 | 结果 |
|---|---|
| 20-device 池 60 req @12c 真实链路 | 60/60 = 200，rps 2.6，p50=1.9s，p95=3.8s，max=11.9s |
| 单 device 30 连发 @6c | 30/30 = 200，**零限速零封禁** |
| 本地 demo /health @30c/15s | 2345 rps，p50=2ms，200 占 99.98% |
| 错误路径 | 空 messages=400 / 空 body=400 / 未知路径=404 全对 |
| 并发 token 竞态回归 | 8 并发同 device = 8/8 200 |

**压测边界**：上游是第三方生产服务，共约 130 次真实推理，不做高压滥用。

## 关键源码锚点（jadx）

| 内容 | 类 |
|---|---|
| 上游配置 JSON | `C1698Qj1`（BASE_SERVICE_DEFAULT） |
| 端点常量 | `C5940ml`（app_productionRelease BuildConfig） |
| Chat Retrofit 接口 | `com.smartwidgetlabs.chatgpt.chat_service.ChatService` / `ChatServiceFallBack` |
| Auth 接口 | `chat_service.AuthServer`（v1/token, v1/refresh） |
| 聊天请求体构造 | `G41`（m3663/m3664） |
| token 请求序列化 | `C4071ec` |
| 公共头拦截器 | `C0762Ej0` / `C7853vz`（UA/Request-ID 生成） |
| 模型目录 | `models.BotModel` |
| 请求编排 | `chat_service.Wwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwwww`（m25051-25055） |
