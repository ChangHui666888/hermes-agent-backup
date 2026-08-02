# Windows 兼容性模式 — 新闻抓取 Cascade 引擎

> 本系统运行于 Windows 10，Python 3.11，httpx 0.28。
> 以下差异点影响所有 HTTP/网络相关操作。

## httpx 0.28 + 代理：SSL 间歇超时

### 症状
```log
ConnectTimeout: _ssl.c:989: The handshake operation timed out
```
同一 URL 有时正常有时挂死，无固定规律。

### 根因
httpx 0.28 默认启用 HTTP/2 (`http2=True`)。在 Windows + HTTP CONNECT 代理 (`http://127.0.0.1:10808`) 环境下，`httpcore` 的 HTTP/2 实现和代理的 SSL 隧道存在兼容性问题。Clash/V2Ray 的 HTTP CONNECT 代理对 HTTP/2 ALPN 协商处理不当。

### 修复
```python
# core/fetchers.py — _make_client()
kwargs = {
    "http2": False,  # ← 关键：禁用 HTTP/2
    "timeout": httpx.Timeout(connect=5, read=15, write=10, pool=5),
}
```
这是本次优化中**最有效的一行代码**——eliminated 100% of SSL timeouts。

### 本地验证
```bash
# Before: 可能挂死
python -c "import httpx; httpx.Client(http2=True).get('https://www.bbc.com')"
# After: 稳定 200
python -c "import httpx; httpx.Client(http2=False).get('https://www.bbc.com')"
```

## SOCKS5 优于 HTTP CONNECT

### 现状
环境变量 `HTTPS_PROXY=http://127.0.0.1:10808`（HTTP CONNECT 模式）。
实测 httpx 通过 HTTP CONNECT 代理 + HTTPS 目标时，稳定性不如 SOCKS5。

### 修复
```python
# core/fetchers.py — 替代方案
proxy = os.environ.get("SOCKS5_PROXY") or "socks5://127.0.0.1:10808"
```
优先使用 SOCKS5，因为 httpx 的 SOCKS5 实现（`socksio` 库）不涉及 ALPN 协商，更稳定。
**不要 fallback 到 `HTTPS_PROXY` 环境变量**——其值为 `http://127.0.0.1:10808`，就是用 HTTP CONNECT 代理转发 HTTPS 请求，正是引发 SSL 超时的路径。
SOCKS5 也可以从环境变量读取，变量名是 `SOCKS5_PROXY`（避免与 `HTTPS_PROXY` 冲突）。

## 进程锁：Windows 上不能用 `os.kill(pid,0)`

### 问题
在 Unix 上，`os.kill(pid, 0)` 用于检测进程是否存活（signal 0 不发送信号，只做权限检查）。
**Windows 不支持 signal 0**——即使目标进程存活也会抛 `OSError: [WinError 87] 参数错误。`
更糟的是，Windows 上 `os.kill(pid, 0)` 有时抛 `SystemError`（不是 `OSError` 的子类），导致 `except OSError` 无法捕获。

### 修复：时间戳锁
```python
def acquire_lock():
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        mtime = os.path.getmtime(LOCK_FILE)
        age = time.time() - mtime
        if age < BATCH_TIMEOUT:  # 锁文件修改时间 < 超时阈值 → 认为活跃
            log(f"[SKIP] 已有 pipeline 在跑，跳过")
            return False
        # 过期锁，清理后重试
        os.remove(LOCK_FILE)
        return acquire_lock()
```

### 锁文件清理
注册 `atexit.register(release_lock)`——进程正常退出时释放锁。
但 Windows 上 `atexit` 在 SIGTERM / `timeout` 命令杀进程时不保证执行。
时间戳锁自带过期检测，即使 `atexit` 没跑，锁也会在下次启动时自动清理。

## IPv6 不可达

### 问题
`r.jina.ai` 和 `api.tavily.com` 都解析到 IPv6 地址，而本机的 Clash/V2Ray 代理
不支持或未正确路由 IPv6 流量，导致 SSL 连接超时。

### 验证
```bash
curl -4 -s -o /dev/null -w "%{http_code}" --max-time 5 https://r.jina.ai    # ✅ 200
curl -6 -s -o /dev/null -w "%{http_code}" --max-time 5 https://r.jina.ai    # ❌ 000
```

### 修复：`curl -4`
对 Jina Reader 和 Tavily 两个第三方 API，通过 `subprocess.run(["curl", "-4", ...])`
强制 IPv4。httpx 没有原生"prefer IPv4"选项，直接使用 IP 地址 + Host header 时
又会产生 SNI 问题（TLS 握手时 SNI 字段为 IP 而非域名，服务器拒绝）。
`curl -4` 同时解决了 IPv6 和 SNI 两个问题。

## subprocess 调用 `curl`：Python vs PowerShell 的路径差异

### 问题
在 Python 中 `subprocess.run(["curl", ...])` 和 PowerShell 中直接打 `curl` 的行为不同：
- **PowerShell**：`curl` 是 `Invoke-WebRequest` 的别名，不是真正的 curl。必须用 `curl.exe`。
- **Python subprocess**：`subprocess.run(["curl", ...])` 解析 PATH 找到 `C:\Program Files\Git\mingw64\bin\curl.exe`（Git 自带的 curl），是真正的 curl。**不需要加 `.exe`**。

### 验证
```python
import subprocess
r = subprocess.run(["curl", "--version"], capture_output=True, text=True)
print(r.stdout)  # → curl 8.21.0 (Windows) libcurl/8.21.0 Schannel ...
```

### 建议
Python 代码中直接写 `["curl", "-4", ...]` 即可。如果在 PowerShell 中手动测试，用 `curl.exe` 而非 `curl`。

## batch.py 退出码 143 = SIGTERM

### 含义
```log
batch.py exited 143
```
退出码 143 = 128 + 15 = SIGTERM。表示 `subprocess.run(timeout=...)` 超时后杀死了 batch.py 子进程。

这是正常行为——`BATCH_TIMEOUT` 到期后 subprocess 被强制终止。pipeline 会继续执行 Step 3.5 Recovery（独立 try 块，不受影响）。

### 排查
如果 `batch.py exited 143` 频繁出现（连续多次都超时），说明：
1. 当前批次的 URL 太难（含多个反爬站点），单个 cascade 耗时过长
2. 或者 `BATCH_TIMEOUT` 设得太紧（当前 600s，5 URL 的合理预算 ~500s）
3. 解决方向：在 `domain_profiles.py` 的 `known_failing` 中移除已确认不可用的策略，缩短单 URL 耗时

## URL 解析：`\t` 分隔格式

`auto-pipeline.py` Step 3.5 调用 `batch.py --force-strategy` 时，
URL 列表文件支持 `url\ttitle` 格式（tab 分隔），使 tavily/searxng_alt 策略
能获得文章标题做更精准的搜索查询。

```python
def _parse_url_line(line: str) -> tuple[str, str | None]:
    parts = line.split("\t", 1)
    if len(parts) == 2:
        u, t = parts[0].strip(), parts[1].strip()
        return u, (t or None)
    return line.strip(), None
```

纯 URL 行完全向后兼容。
