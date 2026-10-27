# Chat Smith APP 2api

> **Chat Smith** (com.smartwidgetlabs.chatgpt, VulcanLabs) v8.251229.2 逆向 → OpenAI 兼容 2API 交付。
> 纯静态还原（jadx 8 dex / 20617 类，零模拟器动态），全链路实测打通。

| 状态 | 说明 |
|---|---|
| 协议还原 | ✅ 100%（鉴权/聊天/模型目录/错误码） |
| 2API demo | ✅ `demo_server.py` 端口 8903，OpenAI 兼容 `/v1/chat/completions` |
| 真实链路 | ✅ 直连 curl + demo 层 8 并发回归全 200 |
| 压测 | ✅ 上游无限速（单 device 30 连发零封禁）；本地 2345 rps |
| 模型 | ⚠️ 免费 JWT 一律路由 gpt-4o-mini-2024-07-18（21 模型目录是付费墙幌子） |
| new-api 对接文档 | ✅ [docs/new-api-integration.md](docs/new-api-integration.md) |

## 上游架构（还原结论）

```
App ──POST /smith-auth/api/v1/token {device_id}──▶ api.vulcanlabs.co  (无鉴权, 直接发 30min JWT)
   ──POST /smith-v2/api/v7/chat_android  Bearer JWT + 5 公共头──▶ OpenAI 风格响应 (choices[].Message 大写 M)
```

- **鉴权**：`device_id`（任意随机字符串）即身份，无签名、无 AppCheck（`_android` 后缀端点绕开 Firebase 校验）、token 可无限重放
- **免费层模型墙**：任何 model 参数静默降级为 gpt-4o-mini（`usage_model` 字段服务端不认）
- **无限速/无 IP 绑定**：横向加 device_id 即可扩展并发

## 快速开始

```bash
pip 无额外依赖 (纯标准库)
python demo_server.py          # 默认 8903 端口
# 浏览器打开 http://127.0.0.1:8903/demo.html  或
curl http://127.0.0.1:8903/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hi"}]}'
```

## 文件

| 文件 | 说明 |
|---|---|
| `demo_server.py` | 2API 服务：OpenAI 兼容端点 + demo 页 + JWT 自动获取/缓存/续期 |
| `demo.html` | 网页聊天 demo（模型下拉/token 统计/延迟显示） |
| `stress_test.py` | 压测脚本（本地基准 + 低频真实链路 + 错误路径） |
| `tools/protocol_probe.py` | 上游协议直连探针（不依赖 demo server，逐项验证头/签名/模型矩阵） |
| `docs/new-api-integration.md` | new-api 渠道对接文档（对接会话直接照做） |
| `docs/reverse-report.md` | 完整逆向报告（端点/头/错误码/模型目录/绕过尝试记录） |

## 压测数据（2026-10-28）

| 场景 | 结果 |
|---|---|
| 20-device 池 60 req @12c | 60/60 = 200，rps 2.6，p50 1.9s（瓶颈=上游推理延迟） |
| 单 device 30 连发 @6c | 30/30 = 200，零限速零封禁 |
| 本地 /health @30c | 2345 rps，p50 2ms |
| 错误路径 | 400/400/404 全对 |

> 免责声明：仅用于安全研究与协议学习。上游为第三方生产服务，请勿高压滥用。
