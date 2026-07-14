# Pipeline Gap Analysis — 2026-07-14

## 当前状态

```
Phase 0 RSS:      ✅ 3,949 articles, last 09:28 (today)
Phase 1 Scorer:   ✅ 3,949 scored, 100% coverage
Phase 2 Fetcher:  ❌ 290 rows, only 5 have content (1.7%)
Phase 3 Aggregator: ⚠️ 41 events, last 07-12 (2 days stale)
Phase 4 Enhancer:  ❌ 0 enhanced (no LLM running)
Phase 5 Pusher:    ❌ not running
Phase 6 Cloud Sync: ⚠️ cron disabled
```

## Gap Detail

| # | Gap | 影响 | 严重度 |
|:--:|------|------|:--:|
| 1 | **Fetcher 覆盖率 1.7%** — 290 rows, 5 with content | Aggregator 缺乏正文输入 | 🔴 Critical |
| 2 | **Aggregator 2天未更新** — 41 events since 07-12 | Web 数据停滞 | 🔴 Critical |
| 3 | **Tier B 368篇未抓取** — 仅 5/62 Bloomberg 有内容 | 高价值文章缺失 | 🟡 High |
| 4 | **Enhancer 零运行** — 无 LLM 增强 | Tier A/B 无标签/摘要 | 🟡 High |
| 5 | **Pusher 未运行** — 无数据推送到云端 | 云端 PG 数据滞后 | 🟡 Medium |
| 6 | **Cloud Sync cron 停用** — job 92b78fee7369 disabled | 无自动同步 | 🟡 Medium |
| 7 | **RSS Scanner 独立进程** — 不在 pipeline 管理内 | 故障不可见 | 🟢 Low |

## Tier A/B 抓取覆盖

```
Bloomberg:  5/62  (8%)    ← 仅部分付费墙绕过
France 24:  0/30  (0%)    ← 历史 403, 修复后应可达
Al Jazeera: 0/28  (0%)    ← 开放站点, 应100%
UK Gov:     0/28  (0%)    ← 开放站点, 应100%
Newsweek:   0/22  (0%)    ← 中等反爬
CBS News:   0/16  (0%)    ← 部分406
```

## 修复优先级

```
1. python -m news_intel.pipeline --hours 48 --fetch  ← 抓取全部 Tier A/B
2. python -m news_intel.pipeline --hours 48            ← 重新聚合
3. 启用 cron 92b78fee7369                              ← 恢复自动同步
```
