#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chat Smith (com.smartwidgetlabs.chatgpt v8.251229.2) 2API demo server
上游: api.vulcanlabs.co (VulcanLabs smith-v2) — 逆向还原协议
  1. POST /smith-auth/api/v1/token  {device_id,...}  -> 免费 JWT (无签名/无AppCheck)
  2. POST /smith-v2/api/v7/chat_android  Bearer JWT + Vulcan 公共头 -> OpenAI 风格响应
OpenAI 兼容端点: POST /v1/chat/completions (stream 参数忽略, 上游为纯非流式协议)
GET  /v1/models  列出 BotModel.java 还原的模型目录
"""
import json, os, time, uuid, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request

AUTH_URL = "https://api.vulcanlabs.co/smith-auth/api/v1/token"
CHAT_URL = "https://api.vulcanlabs.co/smith-v2/api/v7/chat_android"
APP_ID = "com.smartwidgetlabs.chatgpt"
UA = "Chat Smith Android, Version 8.251229.2(1247)"
SSL_CTX = None
try:
    import ssl
    SSL_CTX = ssl.create_default_context()
    SSL_CTX.check_hostname = False
    SSL_CTX.verify_mode = ssl.CERT_NONE
except Exception:
    pass

MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-5", "gpt-5-mini", "gpt-5.2", "gpt-4", "gpt-3.5-turbo",
          "o3", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-3-pro-preview", "gemini-3-flash-preview",
          "deepseek-chat", "deepseek-reasoner", "grok-4", "grok-4-fast", "grok-2"]

_token_cache = {}  # device_id -> (token, exp_ts)
_lock = threading.Lock()

def get_token(device_id):
    with _lock:
        hit = _token_cache.get(device_id)
        if hit and hit[1] > time.time() + 60:
            return hit[0]
    body = json.dumps({"device_id": device_id, "order_id": "", "product_id": "",
                       "purchase_token": "", "subscription_id": ""}).encode()
    req = urllib.request.Request(AUTH_URL, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        tok = json.loads(r.read())["AccessToken"]
    _token_cache[device_id] = (tok, time.time() + 1500)
    return tok

def upstream_chat(device_id, payload):
    token = get_token(device_id)
    body = json.dumps(payload).encode()
    req = urllib.request.Request(CHAT_URL, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "X-Vulcan-Application-ID": APP_ID, "User-Agent": UA,
        "X-Vulcan-Request-ID": "914948789%d000" % int(time.time() * 1000),
        "Anonymous-User-Id": device_id, "Authorization": "Bearer " + token,
    })
    try:
        with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read())
        except Exception: return {"error": {"message": "upstream http %d" % e.code, "code": e.code}}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/demo.html"):
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo.html"), "rb") as f:
                b = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
            return
        if self.path == "/health":
            return self._json(200, {"status": "ok", "upstream": "api.vulcanlabs.co", "app": "Chat Smith 8.251229.2"})
        if self.path == "/v1/models":
            return self._json(200, {"object": "list", "data": [
                {"id": m, "object": "model", "owned_by": "vulcanlabs"} for m in MODELS]})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n))
        except Exception:
            return self._json(400, {"error": {"message": "bad json"}})
        device_id = (req.get("user") or "cs2api-" + uuid.uuid4().hex[:16])[:64]
        messages = req.get("messages") or []
        if not messages:
            return self._json(400, {"error": {"message": "messages required"}})
        model = req.get("model", "gpt-4o-mini")
        payload = {"model": model,
                   "messages": [{"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages],
                   "user": device_id}
        if req.get("max_tokens"): payload["max_tokens"] = req["max_tokens"]
        up = upstream_chat(device_id, payload)
        err = up.get("error")
        if err and (err.get("message") or err.get("code")):
            return self._json(502, {"error": {"message": str(err.get("message")), "type": "upstream_error", "code": err.get("code")}})
        choices = up.get("choices") or []
        if not choices:
            return self._json(502, {"error": {"message": "empty upstream choices", "raw": str(up)[:300]}})
        content = (choices[0].get("Message") or {}).get("content", "")
        out = {"id": "chatcmpl-" + uuid.uuid4().hex[:24], "object": "chat.completion",
               "created": int(time.time()), "model": up.get("model", model),
               "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
               "usage": up.get("usage", {})}
        self._json(200, out)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8903"))
    print("Chat Smith 2API demo on http://0.0.0.0:%d  (upstream api.vulcanlabs.co)" % port)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
