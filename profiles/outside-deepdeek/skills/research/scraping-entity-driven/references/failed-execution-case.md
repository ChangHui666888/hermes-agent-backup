# 失败案例分析：scraping-entity-driven 执行错误

> 记录时间: 2026-07-01
> 场景: 用户说"追踪川普" → 代理执行 scraping-entity-driven 时犯了5个连续错误

## 背景

用户要求追踪川普（Trump），代理加载 `scraping-entity-driven` skill 后执行失败。

## 5个连续错误

### 错误1: 实体被篡改（任务偏差）

```
用户说: 追踪川普
代理响应: "Since you are interested in Elon Musk..."
```

**原因:** 没有继承对话上下文中的实体 `川普/Trump`，自己凭空捏造了 `Elon Musk`。

**修复:** 用户指定的实体必须忠于原实体，不可替代。实体=任务锚点。

### 错误2: 只做了1/6的流程就停住

skill 定义6步，实际只执行了Step 2（搜索）就停了。Step 3-6全部跳过。

**原因:** plan→execute断裂。描述了"我将做什么"，但没有紧接着做。

**修复:** 同一轮响应中必须执行到交付物产出。

### 错误3: 搜索策略错误（OR合并）

```
❌ web_search(query="site:reuters.com Elon Musk OR site:wsj.com Elon Musk")
✅ web_search(query="Donald Trump site:reuters.com")
✅ web_search(query="Donald Trump site:apnews.com")
```

**原因:** 很多搜索引擎不支持跨站OR查询，导致结果不完整。

**修复:** 每个来源独立搜索。

### 错误4: 中途让用户决策

```
代理输出: "based on the results, which area would you like me to prioritize?"
```

**原因:** 把未完成的 pipeline 回退给用户选方向。

**修复:** pipeline 是全自动的，方向选择是 skill 内部工作。

### 错误5: 读skill后只写了计划没执行

读了skill → "我知道怎么做了" → 写计划 → 停住。

**原因:** 违反 Hermes 核心规则：读过skill的同一轮必须发出第一个工具调用。

**修复:** 加载skill后，同一响应中立即调用 web_search 开始批量搜索。
