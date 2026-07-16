# 结构调试模式 — 隐蔽 Bug 模式目录

本轮代码审查发现的通用隐蔽 bug 模式。不仅适用于本项目。

## 1. Python `else:` 绑定陷阱

```python
try:                     # outer try
    if urls:
        ...
    # Step 3.5  # 与 if urls: 同级缩进
    try:         # inner try — 注意这里
        ...
    except:
        ...
    else:        # ← 绑定到 inner try, NOT outer try!
        step_result("FETCH", 0, 0, ...)
except:          # outer except
```

**结果**: inner try 没抛异常 → `else` 执行 → 生成一条假 `FETCH 0/0` 记录，污染 stats 数组。

**修复**: 用 `if not urls: step_result(...)` 替代 `else:` 结构。

## 2. 双重计数（已包含的子集又被加了一次）

```python
content_total = COUNT(*)           # 包含 exhausted，共497
content_exhausted = COUNT(*WHERE)  # 214
total_accounted = content_total + content_exhausted  # 497+214=711 ❌
# 正确: total_accounted = content_total  # 497 ✅
```

**红线**: 每当看到 `X = A + B` 其中 B 是 A 的子集，立即怀疑。

## 3. RateLimiter: sleep 在锁外 = 无效

```python
# ❌ 线程 A 和 B 同时在锁外 sleep → 并行通过
with lock:
    remaining = delay - (now - last)
if remaining > 0:        # ← 锁外!
    time.sleep(remaining)  # ← 两个线程同时 sleep
with lock:
    timestamp = now
```

**测试证明**: 8线程×50ms delay，锁外版 0.05s（并行绕过），锁内版 0.35s（序列化）。

```python
# ✅ 全部在锁内
with lock:
    remaining = delay - (now - last)
    if remaining > 0:
        time.sleep(remaining)  # ← 锁内 OK
    timestamp = time.monotonic()
```

## 4. 测试断言中的类型不匹配

```python
serial[url] = extract_text(url)  # extract_text 返回 (url, text) tuple
concur[url] = text               # 只存了字符串
# 比较: tuple vs string → 永远 False
```

**红线**: 当测试全部失败且说"0/4 match"但个别日志显示全部工作正常时，检查存储类型。

## 5. 硬编码密钥 fallback 默认值

```python
# ❌ 提交到 git
TOKEN = os.environ.get("KEY", "sk-abc123")
# ✅
TOKEN = os.environ.get("KEY") or ""
```

如果密钥已经进了 git 历史，必须轮换——不可仅通过修改代码修复。

## 6. sqlite3.Row 没有 `.get()` 方法

```python
# db.execute().fetchall() 返回 sqlite3.Row 对象
row = db.execute("SELECT ...").fetchone()
row.get("col")  # ❌ AttributeError: 'sqlite3.Row' object has no attribute 'get'
row["col"]      # ✅
row["col"] or default  # ✅ 有 fallback
```

**检测**: 全局 grep `row.get(` — 任何命中都是 bug，除非 `row_factory = dict_factory`。

## 7. LLM 增强串行瓶颈

Qwen3-1.7B CPU 推理 ~20s/篇。17篇 Tier B = 340s 纯阻塞。

**修复**: `ThreadPoolExecutor(max_workers=4)` — 4路并发 HTTP 到 LM Studio。
需配合 `threading.Lock` 保护全局错误标记，且 DB 写入保持串行（sqlite3 非线程安全）。
