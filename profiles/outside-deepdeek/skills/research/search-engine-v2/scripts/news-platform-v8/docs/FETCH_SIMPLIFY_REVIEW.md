# Fetch Pipeline 简化方案评估

## 环境事实

```
SearXNG:  ❌ 不可用 (服务未运行/端口不通)
Tavily:   ❌ 无 API Key
Tier A:   4/4 已抓取 (100%)
Tier B:   80/394 已抓取 (20%)
```

## 逐项评估

### 1. SearXNG 作为 URL 恢复 ✅ 逻辑正确，暂不可用

| 维度 | 评估 |
|------|------|
| 逻辑 | Fetch 失败 → SearXNG 搜索相同新闻的其他 URL → 重试 ← 正确 |
| 实际 | SearXNG 端口 8080 不通，searxng-core 容器虽在运行但 search API 无响应 |
| 结论 | **先修复 SearXNG，再实施** |

### 2. Tavily 作为最后补偿 ⚠️ 成本可控时合理

| 维度 | 评估 |
|------|------|
| 逻辑 | 仅 >=90 分文章使用，日调用 <5 次 |
| 实际 | 无 API Key，需注册 |
| 成本 | Tavily 免费计划 1000 次/月，够用 |
| 结论 | **注册 Key 后可实施** |

### 3. 评分路由 (>=80 SearXNG, >=90 Tavily) ✅ 合理

| 维度 | 评估 |
|------|------|
| 逻辑 | 重要文章多尝试，普通文章直接放弃 |
| 数据 | Tier A 已 100% 抓取，Tier B 20% |
| 收益 | 对 314 篇未抓取的 Tier B 文章恢复 |
| 结论 | **阈值可调整为 >=85 SearXNG, >=90 Tavily** |

### 4. 不抽象 SearchProvider ❌ 建议更灵活

| 维度 | 评估 |
|------|------|
| 原因 | 当前只有 2 个搜索后端，抽象收益低 |
| 我的看法 | 不同意 — 2 行 if/else 即可，不需要抽象 |

### 5. 简化架构 (L0-L7) ✅ 与当前一致

```
L0 RSS → L1 Score → L2 Router → L3 Fetch → L4 Extract → L5 Validate → L6 Enhance → L7 Storage
```
与我们现有的 pipeline.py 流程一致，只是 L3 增加 SearXNG/Tavily 补偿。

## 推荐实施

| 优先级 | 任务 | 工时 |
|:--:|------|:--:|
| 1 | 修复 SearXNG (确认容器运行) | 15min |
| 2 | 注册 Tavily API Key | 5min |
| 3 | batch.py 增加 fetch_with_recovery() | 30min |
| 4 | 仅在 Tier A (>=90) 触发 Tavily | 已包含在上步 |

## 最终判断

> 方案方向正确，6 个建议中 3 个可取，2 个不可用（环境未就绪），1 个不需抽象。先修复 SearXNG + 注册 Tavily，再实施代码（1h 内完成）。
