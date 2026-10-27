#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chat Smith 上游协议探针 — 不依赖 demo server，直连上游逐项验证。
用法:
  python protocol_probe.py auth          # token 端点
  python protocol_probe.py headers       # 公共头逐项缺失测试 (错误码 14/17 复现)
  python protocol_probe.py models        # 模型矩阵 (21 模型是否降级)
  python protocol_probe.py chat "你好"   # 单次真实聊天
"""
import json, sys, time, ssl, urllib.request, urllib.error

AUTH = "https://api.vulcanlabs.co/smith-auth/api/v1/token"
CHAT = "https://api.vulcanlabs.co/smith-v2/api/v7/chat_android"
APP_ID = "com.smartwidgetlabs.chatgpt"
UA = "Chat Smith Android, Version 8.251229.2(1247)"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

def get_token(device_id):
    body = json.dumps({"device_id": device_id, "order_id": "", "product_id": "",
                       "purchase_token": "", "subscription_id": ""}).encode()
    req = urllib.request.Request(AUTH, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        return json.loads(r.read())

def chat(device_id, model, content, headers_override=None, body_extra=None):
    tok = get_token(device_id)["AccessToken"]
    body = {"model": model, "messages": [{"role": "user", "content": content}], "user": device_id}
    if body_extra: body.update(body_extra)
    headers = {"Content-Type": "application/json", "Accept": "application/json",
               "X-Vulcan-Application-ID": APP_ID, "User-Agent": UA,
               "X-Vulcan-Request-ID": "914948789%d000" % int(time.time() * 1000),
               "Anonymous-User-Id": device_id, "Authorization": "Bearer " + tok}
    if headers_override: headers.update(headers_override)
    req = urllib.request.Request(CHAT, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "auth"
    if cmd == "auth":
        t = get_token("probe-auth-%d" % time.time())
        print("AccessToken:", t["AccessToken"][:50] + "...")
        print("tier exp:", t["AccessTokenExpiration"], "(30min)")
    elif cmd == "headers":
        dev = "probe-hdr-%d" % time.time()
        cases = [("full headers", {}), ("no Authorization", {"Authorization": ""}),
                 ("no X-Vulcan-Application-ID", {"X-Vulcan-Application-ID": ""}),
                 ("no User-Agent", {"User-Agent": ""})]
        for label, ov in cases:
            code, resp = chat(dev, "gpt-4o-mini", "hi", headers_override=ov)
            err = resp.get("error")
            print(f"{label:32s} -> http={code} err={err}")
    elif cmd == "models":
        for m in ["gpt-4o", "gpt-5", "gpt-5.2", "o3", "gemini-2.5-pro", "gemini-3-pro-preview",
                  "deepseek-reasoner", "grok-4", "gpt-3.5-turbo"]:
            dev = "probe-m-%d" % time.time()
            code, resp = chat(dev, m, "reply pong")
            served = resp.get("model", "?")
            content = ((resp.get("choices") or [{}])[0].get("Message") or {}).get("content", "")[:30]
            print(f"{m:24s} -> served={served:34s} {content!r} (downgraded)" if served != m
                  else f"{m:24s} -> OK served={served}")
            time.sleep(0.3)
    elif cmd == "chat":
        msg = sys.argv[2] if len(sys.argv) > 2 else "hello"
        code, resp = chat("probe-chat-%d" % time.time(), "gpt-4o-mini", msg)
        print(json.dumps(resp, ensure_ascii=False, indent=2)[:800])
    else:
        print(__doc__)

if __name__ == "__main__":
    main()
