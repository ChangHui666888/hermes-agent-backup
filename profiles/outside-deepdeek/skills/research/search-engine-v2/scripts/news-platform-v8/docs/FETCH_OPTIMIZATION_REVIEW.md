# Fetch Pipeline 优化建议评估

## 数据事实

```
4245 articles:
  content_encoded (RSS全文): 0     ← RSS 源不发全文
  description > 200 chars:   998   ← 23% 有长摘要
```

## 逐项评估

### 1. RSS FullText ✅ 可取，立即生效

| 维度 | 评估 |
|------|------|
| 价值 | 998 articles (23%) 可直接用 RSS description 替代 HTTP 抓取 |
| 成本 | 0 HTTP 请求，0 延迟 |
| 实现 | 在 strategy_order 第一位加 `rss_fulltext` |
| 风险 | 无 |

**建议**: 立即实现。RSS description 已有 200-500 chars，足够事件聚合使用。

### 2. PreCheck / Strategy Planner ✅ 可取，V2 核心

| 维度 | 评估 |
|------|------|
| 价值 | Blumbrg 每次都尝试 direct(403)→archive(404)→scrapling(timeout)，30s 浪费 |
| 成本 | domain_profiles 已有 `known_failing` 列表，只需读配置 |
| 实现 | 在 `extract_url()` 中增加 `domain_stats` 查询 |

**建议**: 基于现有 `domain_profiles.known_failing` 增强即可。但 `known_failing` 目前已手动维护，建议增加自动学习（建议 #5）。

### 3. Extractor Router ⚠️ 部分可取

| 维度 | 评估 |
|------|------|
| 价值 | 不同网站正文格式不同，trafilatura 非万能 |
| 当前 | `_extract_main_text()` 已有 3 级 fallback: trafilatura → readability → regex |
| 改进 | 不需要新增 Extractor Router 模块，现有 fallback 已足够 |

**建议**: 不新增模块。现有 `_extract_main_text()` 的 3 级 fallback 已满足 V1 需求。

### 4. Quality Validator ✅ 可取，解决误判

| 维度 | 评估 |
|------|------|
| 价值 | 避免登录页/广告页/JS 占位页被误判为正文 |
| 当前 | 仅检查 `len > min_len` |
| 问题 | 3000 字 HTML 可能是 cookie 弹窗 |

**建议**: 增加 2 个快速检查：
- `html_ratio`: `<` 标签密度 > 30% → 拒绝
- `line_density`: 连续 5 行无标点 → 可能是 JS/JSON

### 5. Domain Statistics ✅ 可取，长期优化

| 维度 | 评估 |
|------|------|
| 价值 | 自动学习每个 domain 的最佳策略 |
| 当前 | `known_failing` 手动维护 |
| 实现 | 增加 `fetch_stats` 表记录每次成功/失败 |

**建议**: V2 实现。简单 SQLite 表即可，不需要复杂统计引擎。

### 6. Search Snippet 提前 ❌ 不建议

| 维度 | 评估 |
|------|------|
| 逻辑 | "搜索摘要足够聚合" — 对事件聚合不够 |
| 当前 | SAO 提取需要 200+ chars 正文，搜索摘要可能不够 |

**建议**: 保持当前顺序。search_snippet 作为最后兜底是合理的。

## 实施优先级

| 优先级 | 建议 | 工时 | 效果 |
|:--:|------|:--:|------|
| 1 | RSS FullText | 15min | 减少 23% HTTP 请求 |
| 2 | Quality Validator | 30min | 避免误判 |
| 3 | known_failing 增强 | 15min | 减少失败尝试 |
| 4 | Domain Statistics | 1h | 自动策略优化 |
| ❌ | Extractor Router | — | 已有 fallback |
| ❌ | Search Snippet 提前 | — | 不适合聚合 |

## 结论

6 个建议中 **4 个可取，2 个不需要**。优先实现 RSS FullText + Quality Validator（45min），立即见效。
