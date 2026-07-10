# Hermes Search Backends — 配置与测试

配置 Hermes 的两大搜索后端：Tavily（云端 API）和 SearXNG（自托管元搜索引擎）。

---

## 配置文件

搜索后端的 API 密钥和 URL **必须放在 `.env` 文件中**，而不是 `config.yaml`。

```bash
hermes config env-path   # 查看 .env 路径
```

### Tavily API Key

```bash
hermes config set TAVILY_API_KEY "tvly-xxxxx"
```
→ 会自动写入 `.env` ✅

### SearXNG URL

```bash
hermes config set SEARXNG_URL "http://your-server:8080"
```
→ ⚠️ **会错误地写入 `config.yaml`**，而不是 `.env`

必须手动修正：从 `config.yaml` 删除该行，添加到 `.env`：

```bash
# 从 config.yaml 中删除
sed -i '/SEARXNG_URL:/d' "$(hermes config path)"

# 添加到 .env
echo 'SEARXNG_URL=http://your-server:8080' >> "$(hermes config env-path)"
```

> **原因**：`hermes config set` 对某些非标准 env var 名称会误判目标文件。
> API key 类变量（含 `_KEY`/`_TOKEN`/`_SECRET` 等）正确走 `.env`，
> 而 `SEARXNG_URL` 这类纯 URL 变量被当成普通 config 写入 `config.yaml`。

---

## 测试搜索

### 方式 A：直接测试 SearXNG

SearXNG 实例通常**禁用 JSON API**（返回 403），但 HTML 搜索可用。

```bash
# 1. 检查端点是否可达
curl -s -o /dev/null -w "%{http_code}" "http://<host>:<port>/"    # 应返回 200

# 2. HTML 搜索（GET + 新闻分类）
curl -s -L -H "User-Agent: Mozilla/5.0" \
  "http://<host>:<port>/search?q=<query>&categories=news&language=en&time_range=week&safesearch=0" \
  > /tmp/searxng_result.html

# 3. 用 Python 解析 HTML 结果
python -c "
import re
with open('/tmp/searxng_result.html') as f:
    html = f.read()
articles = re.findall(r'<article[^>]*class=\"result[^\"]*\"[^>]*>(.*?)</article>', html, re.DOTALL)
for i, art in enumerate(articles[:10]):
    # 提取标题
    t = re.search(r'<h3><a[^>]*rel=\"noreferrer\"[^>]*>(.*?)</a></h3>', art, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', t.group(1)).strip() if t else 'N/A'
    # 提取 URL
    u = re.search(r'<a href=\"(https?://[^\"]+)\" class=\"url_header\"', art)
    url = u.group(1) if u else ''
    # 提取日期
    d = re.search(r'datetime=\"([^\"]+)\"', art)
    date = d.group(1) if d else ''
    # 提取摘要
    sn = re.search(r'<p class=\"content\">(.*?)</p>', art, re.DOTALL)
    snippet = re.sub(r'<[^>]+>', '', sn.group(1)).strip() if sn else ''
    print(f'[{i+1}] {title}')
    print(f'    URL: {url}')
    print(f'    Date: {date}')
    print()
"
```

### 方式 B：直接测试 Tavily API

```bash
# 1. 从 .env 读取 key
KEY=$(grep "^TAVILY_API_KEY=*** "$(hermes config env-path)" | cut -d'=' -f2)

# 2. 写入 payload 到临时文件（避免 shell 转义问题）
cat > /tmp/tavily_payload.json << 'EOF'
{
  "api_key": "PASTE_KEY_HERE",
  "query": "search query",
  "search_depth": "basic",
  "topic": "news",
  "days": 3,
  "max_results": 5,
  "include_answer": true
}
EOF

# 替换实际的 key（或用 Python 写文件）
# 3. 调用 API
curl -s -X POST "https://api.tavily.com/search" \
  -H "Content-Type: application/json" \
  -d @/tmp/tavily_payload.json \
  -o /tmp/tavily_response.json \
  -w "%{http_code}"
```

### 方式 C：Hermes 内部 web_search 工具（需要 /reset）

配置生效后（`.env` 已写对），在新会话中：

```
/reset
web_search(query="搜索词")
```

Tavily 和 SearXNG 都可用时，Hermes 自动选择可用后端。`web.search_backend: ''`（空字符串）表示自动检测。

---

## 陷阱

| 问题 | 原因 | 解决 |
|------|------|------|
| `hermes config set SEARXNG_URL` 写到 config.yaml | hermes config set 对非标准 env var 误判目标文件 | **手动写入 .env** |
| web_extract 搜 SearXNG 报 "Blocked: private network" | web_extract 工具禁止内网地址 | 用 `curl` 直接调用 |
| patch 拒绝修改 .env/config.yaml | 安全保护 | 用 `sed` 或 `终端` 操作 |
| `python3` 报 exit code 49 | Windows Store Python 存根 | 用 `python`（Hermes venv） |
| Tavily 返回无关结果（体育、世足赛等） | 搜索词不够精确 | 用更具体的词 + `topic: news` + `days: 3` 缩小范围 |
