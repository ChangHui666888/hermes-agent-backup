# Event Aggregation V4.2.1 — 审计与调试指南

## 版本演进

```
V4.0: 标题Jaccard + Entity重叠 + Union-Find (链式污染严重)
V4.1: Entity Canonicalizer + Type Weight + IDF + Anchor
V4.2: Topic IDF + Action Hierarchy + Score重平衡 + Participants (Location被错误替换)
V4.2.1: Location硬约束恢复 + MERGE_THRESHOLD 70→75 + L6数据闭环
```

## V4.2.1 审计命令

```bash
# 正常聚合
python test_aggregator.py --hours 24 --window 6 --limit 50

# 完整指纹+评分矩阵
python test_aggregator.py --hours 24 --window 6 --limit 20 -v

# 单事件深度分析 (定位误聚合根因)
python test_aggregator.py --hours 24 --window 6 --limit 20 --single 1

# +Insight
python test_aggregator.py --hours 24 --window 6 --limit 20 --single 1 --insight
```

## 典型误聚合排查流程

1. `--single N` 定位事件成员指纹
2. 检查成员实体的原始值（是否被 RSS 过标）
3. 检查动作检测是否正确（regex 命中）
4. 检查评分矩阵中的具体分值

## 已知根因模式

### 模式A: RSS实体过标
```
症状: 无关文章因共享{Trump}被拉入Iran事件
指纹: subj=Trump 出现在多个不相关事件的指纹中
根因: L1评分层给所有提及Trump的文章标记 {persons: ["Trump"]}
```

### 模式B: 动作误检测
```
症状: 描述含"attack"词→action=ATTACKS→Military
指纹: 法律/体育文章被错误归类为Military
根因: ACTION_MAP regex 命中描述中的无关词汇
```

### 模式C: 截断日期
```
症状: "Fri, 10 Ju" 截断→None→跳过时间窗口→跨时间误合
根因: RSS scanner 的 date 字段被截断为25字符
```
