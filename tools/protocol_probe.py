#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chat Smith 上游协议直连探针 — 不依赖 demo server，逐项验证协议要素。
用法: python tools/protocol_probe.py [probe|models|stress]
"""
import json, ssl, sys, time, urllib.request, urllib.error, statistics, random, threading

AUTH = "https://api.vulcanlabs.co/smith-auth/api/v1/token"
CHAT = "https://api.vulcanlabs.co/smith-v2/api/v7/chat_android"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

def headers(dev, tok):
    return {"Content-Type": "application/json", "Accept": "application/json",
            "X-Vulcan-Application-ID": "com.smartwidgetlabs.chatgpt",
            "User-Agent": "Chat Smith Android, Version 8.251229.2(1247)",
            "X-Vulcan-Request-ID": "914948789%d000" % (int(time.time() * 1000)),
            "Anonymous-User-Id": dev, "Authorization": "Bearer " + tok}

def token(dev):
    b = json.dumps({"device_id": dev, "order_id": "", "product_id": "",
                    "purchase_token": "", "subscription_id": ""}).encode()
    r = urllib.request.urlopen(urllib.request.Request(AUTH, data=b,
        headers={"Content-Type": "application/json"}), timeout=30, context=CTX)
    return json.loads(r.read())["AccessToken"]

def chat(dev, body, tok=None, hdr_extra=None, hdr_remove=()):
    tok = tok or token(dev)
    h = headers(dev, tok)
    for k in hdr_remove: h.pop(k, None)
    h.update(hdr_extra or {})
    req = urllib.request.Request(CHAT, data=json.dumps(body).encode(), headers=h)
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=90, context=CTX).read())
        ch = r.get("choices") or [{}]
        return "200", r.get("model", "?"), (ch[0].get("Message") or {}).get("content", "")[:40], r.get("error")
    except urllib.error.HTTPError as e:
        return str(e.code), "?", "", e.read().decode()[:120]

def probe():
    dev = "probe-%d" % int(time.time())
    print("== 1. token 端点 =="); t = token(dev); print("   JWT:", t[:50], "...")
    print("== 2. 完整公共头链路 =="); print("  ", chat(dev, {"model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "reply pong"}], "user": dev}))
    print("== 3. 去 Authorization (期望 code 14 Invalid Signature) ==")
    print("  ", chat(dev, {"model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi"}], "user": dev}, hdr_remove=("Authorization",)))
    print("== 4. 去 UA/AppID (期望 code 17) ==")
    print("  ", chat(dev, {"model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hi"}], "user": dev},
        hdr_extra={"User-Agent": "curl/8", "X-Vulcan-Application-ID": "x"}))
    print("== 5. v7/chat 非 android (期望 AppCheck 1002) ==")
    tok = token(dev)
    req = urllib.request.Request("https://api.vulcanlabs.co/smith-v2/api/v7/chat",
        data=json.dumps({"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}).encode(),
        headers=headers(dev, tok))
    try: print("  ", urllib.request.urlopen(req, timeout=30, context=CTX).read()[:150])
    except urllib.error.HTTPError as e: print("  ", e.code, e.read().decode()[:200])

def models():
    print("== 模型矩阵 (期望全部降级为 gpt-4o-mini-2024-07-18) ==")
    for m in ["gpt-5.2", "gpt-5", "o3", "gemini-2.5-pro", "deepseek-reasoner", "grok-4"]:
        dev = "mprobe-%s-%d" % (m[:6], int(time.time()))
        print(f"  {m:22s} ->", chat(dev, {"model": m,
            "messages": [{"role": "user", "content": "reply pong"}], "user": dev}))
        time.sleep(0.4)

def stress(n=20, c=5):
    print(f"== 真实链路压测 {n} req / {c}c / 10-device 池 ==")
    pool = ["sdev%02d" % i for i in range(10)]
    toks = {d: token(d) for d in pool}
    res, codes, lock = [], {}, threading.Lock()
    def worker(k):
        for _ in range(n // c):
            d = random.choice(pool); t0 = time.time()
            s, m, _, _ = chat(d, {"model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}], "user": d}, tok=toks[d])
            with lock: res.append(time.time() - t0); codes[s] = codes.get(s, 0) + 1
    ths = [threading.Thread(target=worker, args=(i,)) for i in range(c)]
    t0 = time.time(); [t.start() for t in ths]; [t.join() for t in ths]
    res.sort()
    print(f"  wall={time.time()-t0:.0f}s rps={len(res)/(time.time()-t0):.2f}")
    if res: print(f"  p50={statistics.median(res)*1000:.0f}ms p95={res[int(len(res)*.95)-1]*1000:.0f}ms")
    print("  codes:", codes)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    {"probe": probe, "models": models, "stress": stress}.get(mode, probe)()
