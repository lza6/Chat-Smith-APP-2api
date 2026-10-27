# Chat Smith → new-api 渠道对接文档

> 目标读者：执行对接的 new-api 会话。上游协议已 100% 还原并实测，照本文操作即可。
> 参考 demo 实现：仓库根 `demo_server.py`（Python 版参考实现，行为已验证）。

## 一、上游事实速览

| 项 | 值 |
|---|---|
| 上游 | `https://api.vulcanlabs.co`（Chat Smith App / VulcanLabs） |
| 取 token | `POST /smith-auth/api/v1/token`，body 只需 `device_id`，**无鉴权** |
| 聊天 | `POST /smith-v2/api/v7/chat_android`，Bearer JWT + 公共头 |
| 有效模型 | **只有 gpt-4o-mini**（任何 model 参数上游一律路由到 gpt-4o-mini-2024-07-18） |
| 限速 | 无（单 device 30 连发零封禁；device_id 随机即新用户） |
| 响应差异 | `choices[].Message` **大写 M**（非标准 `message`） |
| 流式 | 上游纯非流式（App 内无 stream 字段），对接侧需伪流式或整段返回 |
| token 有效期 | 30 分钟（AccessTokenExpiration 字段，建议 25min 提前刷新） |
| 延迟基线 | p50≈1.9s，p95≈3.8s（OpenAI 推理延迟） |

## 二、协议细节（实现必需）

### 1. 取 token

```
POST https://api.vulcanlabs.co/smith-auth/api/v1/token
Content-Type: application/json

{"device_id":"<随机串>","order_id":"","product_id":"","purchase_token":"","subscription_id":""}
```

响应：
```json
{"AccessToken":"eyJ...","RefreshToken":"","AccessTokenExpiration":"2026-10-27T19:54:42Z","RefreshTokenExpiration":"..."}
```

- `device_id` 任意随机字符串（App 用 android_id；对接建议每渠道实例固定一个或小池轮换，见第五节池策略）
- 失败重试：token 端点极稳，一般失败=网络问题

### 2. 聊天请求

```
POST https://api.vulcanlabs.co/smith-v2/api/v7/chat_android
Content-Type: application/json
Accept: application/json
X-Vulcan-Application-ID: com.smartwidgetlabs.chatgpt
User-Agent: Chat Smith Android, Version 8.251229.2(1247)
X-Vulcan-Request-ID: 914948789<毫秒时间戳>     ← 前缀常数 914948789 + 当前毫秒，纯格式无校验
Anonymous-User-Id: <device_id>
Authorization: Bearer <AccessToken>
X-Auth-Token:                                   ← 留空但建议不发（发空串实测也通过）

{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}],"user":"<device_id>"}
```

可选 body 字段：`max_tokens`（int）。**不要发 `stream`**（上游无此字段，发了返回空壳响应）。

### 3. 响应解析（关键差异）

```json
{"id":"chatcmpl-...","model":"gpt-4o-mini-2024-07-18",
 "choices":[{"Message":{"role":"assistant","content":"..."},"index":0,"finish_reason":"stop"}],
 "usage":{"prompt_tokens":9,"completion_tokens":2,"total_tokens":11},"error":null}
```

- 取 content：`resp.choices[0].Message.content`（**大写 M**）
- 错误判定：`resp.error != null` 时 body 为 `{"data":null,"error":{"message":"...","code":<int>}}`

### 4. 上游错误码

| HTTP/body code | 含义 | 处理 |
|---|---|---|
| code 14 "Invalid Signature" | 缺/坏 Authorization | 检查 Bearer 拼接 |
| code 17 "Client request failure" | 缺公共头 | 检查 5 个公共头 |
| HTTP 401/403 | token 过期 | 刷 token 重试一次 |
| code 17 + 空壳响应 (choices:null) | 请求体含 stream 等不支持字段 | 去 stream |

## 三、new-api 对接方案（二选一）

### 方案 A：独立中转服务 + OpenAI 兼容渠道（推荐，最快）

直接部署仓库的 `demo_server.py`（已实现 token 缓存/续期/键名归一化），new-api 加一个标准 OpenAI 渠道：

| 渠道配置 | 值 |
|---|---|
| 类型 | OpenAI |
| Base URL | `http://<中转机IP>:8903`（不要带 /v1，new-api 会自动拼） |
| 密钥 | 任意非空串（demo server 不校验） |
| 模型 | `gpt-4o-mini`（映射名可自定，如 `chatsmith-free`） |
| 分组 | 按需（建议独立分组做免费兜底） |

demo_server 已把 `Message` 归一化为标准 `message`，new-api 侧零改动。

### 方案 B：new-api 原生 adaptor（Go，免中转一跳）

参考本仓库协议细节在 new-api 写 type=xx 的 adaptor（参考现有 `relay/channel/` 下任一简单 adaptor，如 notrack/aivg 的写法）：

1. **adaptor 请求构造**（`relay/channel/chatsmith/`）：
   - `GetRequestURL`: 固定 `https://api.vulcanlabs.co/smith-v2/api/v7/chat_android`
   - `SetupRequestHeader`: 上表 5 公共头 + `Authorization: Bearer <token>`；渠道 key 字段存 device_id 或直接存 JWT 由 ` channelLevelTokenRefresh ` 维护
   - token 获取：实现一个 helper 调 `/smith-auth/api/v1/token`，按渠道缓存 25 分钟（带单飞锁防并发刷新竞态——demo_server 首版踩过：并发同 device 刷新会 502）
2. **响应处理**：
   - 非流式：把 `choices[].Message` 改写为 `message` 后走标准 OpenAI 响应处理
   - 流式请求：上游不支持 → adaptor 收到 `stream:true` 时仍整段请求上游，包装成单个 SSE chunk（`data: {...}\n\ndata: [DONE]`）返回
3. **渠道注册**：`relay/constant/api_type.go` 加 ApiTypeChatsmith + `relay/channel/chatsmith/adaptor.go` + 前端渠道类型常量
4. 模型只注册 `gpt-4o-mini`；`model_mapping` 可把任意请求模型重写为 gpt-4o-mini（反正上游都降级）

## 四、稳定性注意（压测结论）

1. **无配额墙**：device_id 是唯一身份，随机即新用户。但建议固定小池（10-20 个）而非每请求随机——降低被风控画像为爬虫的概率
2. **并发扩展**：瓶颈是上游推理延迟（p50 1.9s），不是配额；多 device 并行即可线性扩
3. **超时**：new-api 渠道超时建议 ≥120s（实测 max 11.9s，留余量）
4. **重试**：偶发网络失败重试 1 次即可；不要对业务错误码重试
5. **X-Vulcan-Request-ID**：无校验（纯时间戳格式），但仍建议照格式生成，防后续加校验
6. **上游监控**：若上游批量 5xx/换协议，先跑仓库 `tools/protocol_probe.py` 定位是协议变了还是服务挂了

## 五、验证清单（对接完成后逐项过）

```bash
# 1. 渠道连通性（new-api 后台"测试"按钮 或 curl 经 new-api)
curl http://<new-api>/v1/chat/completions -H "Authorization: Bearer <sk-xxx>" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"reply pong"}]}'
# 期望: 200, content 含 pong, model 显示 gpt-4o-mini-2024-07-18（或映射名）

# 2. 流式请求
curl -N ... -d '{...,"stream":true}'
# 期望: 正常 SSE 流（伪流式整段吐出也算通过）

# 3. token 过期路径: 中转/token 缓存过期后首请求自动续期不报错

# 4. 上游错误透传: 把 Authorization 改坏 → new-api 应报渠道错误而非 200 空内容
```
