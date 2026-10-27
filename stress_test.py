#!/usr/bin/env python3
# Chat Smith 2API 本地压测 — /health 纯本地 + /v1/chat/completions 低频真实链路
import json, sys, time, threading, urllib.request, ssl, statistics

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8903"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE

def call(path, body=None, timeout=60):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if body else "GET",
        headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, time.time() - t0
    except urllib.error.HTTPError as e:
        return e.code, time.time() - t0
    except Exception:
        return 0, time.time() - t0

def bench(path, body, n, c, label, timeout=60):
    lat, codes = [], {}
    lock = threading.Lock()
    def worker():
        while True:
            with lock:
                if len(lat) >= n: return
            code, dt = call(path, body, timeout)
            with lock:
                lat.append(dt); codes[code] = codes.get(code, 0) + 1
    ths = [threading.Thread(target=worker, daemon=True) for _ in range(c)]
    t0 = time.time()
    [t.start() for t in ths]; [t.join() for t in ths]
    wall = time.time() - t0
    lat.sort()
    rps = len(lat) / wall
    print(f"[{label}] {len(lat)} req {c}c -> {rps:.1f} rps | p50={statistics.median(lat)*1000:.0f}ms "
          f"p95={lat[int(len(lat)*0.95)-1]*1000:.0f}ms p99={lat[int(len(lat)*0.99)-1]*1000:.0f}ms | codes={codes}")

if __name__ == "__main__":
    print("== Chat Smith 2API stress ==")
    bench("/health", None, 300, 10, "health/10c")
    # 真实链路: 低频小并发 (第三方生产服务, 只做行为验证不高压)
    bench("/v1/chat/completions", {"model": "gpt-4o-mini",
          "messages": [{"role": "user", "content": "reply with the word: pong"}]},
          10, 2, "chat-real/2c", timeout=90)
    # 错误路径
    r1, _ = call("/v1/chat/completions", {"model": "gpt-4o-mini", "messages": []})
    r2, _ = call("/v1/chat/completions", None if False else {})
    r3, _ = call("/nonexistent", {})
    print(f"error-paths: empty-messages={r1} no-body={r2} 404={r3} (expect 400/400/404)")
