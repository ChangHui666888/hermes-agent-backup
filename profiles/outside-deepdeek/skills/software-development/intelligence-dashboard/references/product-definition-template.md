# News Intelligence — Web V1 产品定义 (已冻结)

> 不是新闻后台，不是 CMS，不是数据库管理工具。
> **新闻情报分析平台。** 每个页面都有明确的职责边界。

---

## 页面职责矩阵

| 页面 | 核心职责 | 不允许做的事 |
|------|---------|------------|
| **Dashboard** | 全局态势 + 重点事件 + 情报增量 | 不做数据管理、不做CRUD |
| **Event Detail** | 事件深度分析：事实→证据→演化→AI洞察 | 不做文章列表、不做原始数据展示 |
| **Event Explorer** | 事件检索、筛选、排序、批量对比 | 不做编辑、不做配置 |
| **World Map** | 地理空间态势入口 | 不做精细地理分析（Phase2） |
| **Sources** | 信息源能力分析（权威度、首发率、覆盖域） | 不做简单媒体列表 |
| **Search** | 全局搜索入口 | 不做高级查询（Phase2） |

---

## Event Detail — 情报分析阅读顺序 (冻结)

```
第一屏：发生了什么？
  ├─ 标题 + 一句话摘要
  ├─ Confidence 进度条
  └─ Impact level + Event type

第二屏：为什么重要？
  ├─ AI Summary / Significance
  └─ 影响范围 (市场/地缘/行业)

第三屏：事实
  ├─ Subject / Action / Object
  ├─ Location / Time
  └─ 关联实体

第四屏：证据
  ├─ 引用原文
  ├─ 来源
  └─ Verification level (Phase2预留)

第五屏：演化
  ├─ Stage Progress: Breaking → Official → Follow-up → Analysis
  └─ Timeline with stage context

第六屏：信息流动
  ├─ Information Origin (not "Source Chain")
  └─ BREAK → FOLLOW flow
```

**核心原则**: 告诉分析员 "发生了什么 → 为什么重要 → 事实依据 → 证据 → 演化过程"

---

## 颜色规范 (冻结)

| Token | Hex | 用途 |
|-------|-----|------|
| bg-primary | #080B12 | 页面背景 |
| bg-card | #141925 | 卡片（暖灰，非纯蓝灰） |
| bg-elevated | #1A2030 | 悬浮层 |
| border | #1E2A3A | 边框 |
| accent-amber | #F59E0B | **强调色**（重要标记、highlight） |
| accent-blue | #3B82F6 | 交互色（链接、按钮） |
| critical | #EF4444 | 风险 |
| high | #F97316 | 高影响 |
| success | #22C55E | 稳定/通过 |

**原则**: 背景深灰暖、卡片蓝灰、强调琥珀、交互蓝、状态红/橙/绿

---

## Dashboard 三核心组件 (冻结)

| 组件 | 职责 | 位置 |
|------|------|------|
| **Global Situation** | 按区域/主题的事件分布概览 (数字 + 热度条) | 左上 |
| **Event Heat** | 实体/事件热度排行 (横向条形图) | 左下 |
| **Intelligence Feed** | 实时情报增量流 (新事件/置信度变化/状态更新) | 右侧 |

地图是 Global Situation 的**一种表现形式**，不是独立页面。

---

## 不允许做的事 (V1)

- ❌ 用户系统 / 登录
- ❌ CRUD 管理界面
- ❌ 文章原始数据展示
- ❌ 图表库 (recharts 除外，仅用于 Event Heat)
- ❌ Agent Chat 集成
- ❌ 知识图谱可视化

---

## 允许引入的依赖 (V1)

- react-simple-maps (World Map)
- framer-motion (页面过渡)
- date-fns (时间格式化)
