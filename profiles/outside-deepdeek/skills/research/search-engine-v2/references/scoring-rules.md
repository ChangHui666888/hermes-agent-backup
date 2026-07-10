# News Intelligence Engine — 评分规则详解

## 五维评分（满分 100，各维度有硬上限）

### 1. Source Authority（0-20，上限 20）
来源名在 `source_scores.json` 查表。未命中取 `_default: 5`。

| 分 | 来源示例 |
|:--:|------|
| 20 | Reuters, Bloomberg, Federal Reserve, Fed Press |
| 18 | WSJ, AP, The Economist |
| 16 | BBC, CNBC, WaPo |
| 15 | CNN, Guardian, OpenAI |
| 14 | Al Jazeera, France 24, NPR |
| 10 | Seeking Alpha, TechCrunch, The Verge |
| 5 | Hacker News, Reddit, 未配置来源 |

### 2. Event Impact（0-30，上限 30）
5 领域关键词匹配。**同类取最高分（不累加），不同类也取最高（跨类取 max）。**

| 领域 | 30分 | 28分 | 25分 | 20分 |
|------|------|------|------|------|
| 金融 | 降息/加息/破产 | 违约/崩盘 | 央行/通胀/制裁/暴跌 | 财报/IPO |
| 地缘 | 战争/政变/暗杀 | 停火/空袭/弹劾 | 冲突/打击 | 选举 |
| AI | — | AGI/GPT-5 | OpenAI/出口管制 | 模型发布 |
| 市场 | — | — | 央行 | 标普/纳斯达克 |
| 中国 | — | 台海 | 两会/政治局/中美 | 房地产 |

**硬上限规则**：即使命中 10 个 30 分关键词，impact 仍 ≤ 30。

### 3. Entity Importance（0-20，上限 20）
`title + description` 中匹配实体权重库（`entity_weights.json`），取最高分。

| 分 | 实体 |
|:--:|------|
| 20 | Trump, Powell, Xi, NVIDIA, OpenAI, TSMC, 美联储, Kevin Warsh/凯文沃舎 |
| 18 | Musk, Putin, SpaceX, Tesla, ASML, 华为 |
| 16 | Buffett, Yellen, Anthropic, DeepSeek, 伯克希尔 |
| 15 | Apple, Microsoft, Google, AMD, 阿里巴巴, 拜登 |
| 14 | Amazon, Meta, Intel, Boeing |

### 4. Market Relevance（0-20，上限 20）
两步匹配（取 max）：
1. 实体 → 资产映射（`asset_graph.json`）
2. 关键词 → 资产映射

| 关键词 | 关联标的 | 分 |
|------|------|:--:|
| GPU/AI芯片 | NVIDIA, AMD, TSMC, ASML | 20 |
| 降息/加息 | JPMorgan, Goldman Sachs, S&P500 | 20 |
| 出口管制 | NVIDIA, AMD, TSMC, ASML, SMIC | 20 |
| 石油/oil | Exxon, Chevron, Shell, CL1:COM | 18 |
| 战争/war | Lockheed Martin, RTX, Exxon, Chevron | 18 |

### 5. Velocity（0-10，上限 10）
Jaccard 相似度 ≥ 0.5 + 时间差 ≤ 30min = 同事件。

| 报道数 | 分 |
|:--:|:--:|
| 1（仅自身）| 0 |
| 2-4 | 2 |
| 5-9 | 5 |
| ≥10 | 10 |

### Tier 划分
- **A** (≥85): DeepSeek V4 Flash 深度分析
- **B** (60-84): Qwen3-1.7B 本地增强
- **C** (<60): Python 规则（零成本）

## 实测分布（60 篇真实 RSS, 2026-07-08）

| Tier | 篇数 | 占比 | 处理方式 |
|:----:|:--:|:--:|------|
| A | 1 | 1.7% | DeepSeek 云 (~$0.002/篇) |
| B | 6 | 10.0% | Qwen3 本地 ($0) |
| C | 53 | 88.3% | Python 规则 ($0) |

## 配置扩展

### 添加实体
编辑 `news_intel/config/entity_weights.json`：
```json
"persons": { "Kevin Warsh": 20, "凯文沃舎": 20, "沃什": 18 }
```

### 添加关键词
编辑 `news_intel/config/event_keywords.json`：
```json
"finance": { "量化宽松": 25, "QE": 25 }
```

### 添加资产映射
编辑 `news_intel/config/asset_graph.json`：
```json
"新能源": { "stocks": ["宁德时代","隆基绿能"], "weight": 18 }
```
