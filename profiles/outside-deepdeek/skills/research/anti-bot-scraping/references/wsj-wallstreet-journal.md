# WSJ (The Wall Street Journal) — 华尔街日报

**域名**: wsj.com  
**反爬系统**: DataDome CAPTCHA（最激进级别）  
**付费墙**: 硬付费墙，无免费额度  
**成功策略**: web_extract 直连（主页面）→ Wayback Machine（文章/卡片）→ 搜索摘要（备用）

---

## 已验证的抓取组合

| 目标类型 | URL 模式 | 成功工具 | 状态 |
|---------|----------|---------|------|
| Live blog 主页 | `/livecoverage/stock-market-today-...-06-30-2026` | `web_extract` 直连 | ✅ 可提取 |
| Live blog 子卡片 | `/livecoverage/.../card/卡片标题-ID` | Wayback Machine 存档 | ✅ 可提取 |
| 独立文章 | `/finance/stocks/...-f99afef2` | Wayback Machine 存档 | ✅ 可提取 |
| 独立文章 (新) | `/business/deals/...-62e08b5e` | Wayback Machine 存档 | ✅ 可提取 |
| 独立文章 (新) | `/world/americas/...-0e7e3b61` | Wayback Machine 存档 | ✅ 可提取 |
| 印刷版 | `/print-edition/20260630/...` | 全部被阻断 | ❌ 无解 |
| 观点版 | `/opinion/...` | 全部被阻断 | ❌ 无解 |
| News API | `/api/feed/news/` | 全部被阻断 | ❌ 无解 |

## 已验证的工作案例

### 案例1: 2026-06-30 Live Blog（当日）

- **主页 URL**: `https://www.wsj.com/livecoverage/stock-market-today-dow-sp-500-nasdaq-06-30-2026`
- **提取方式**: `web_extract` 直连 ✅
- **提取内容**: 标题、摘要（"S&P 500 is up 14%, Nasdaq has jumped 20% — biggest quarterly rallies since Q2 2020"）、中东局势更新、日元四十年低点
- **限制说明**: 子卡片全部被 DataDome 阻断，无法提取；当日最新，Wayback Machine 尚未收录

### 案例2: 2026-06-29 Live Blog 卡片（隔日文章）

- **卡片 URL**: 多个 live blog 子卡片
- **提取方式**: Wayback Machine 存档 ✅
- **提取的卡片**:
  1. `Heard on the Street Recap: Wild Quarter` — S&P 500 +10% Q2, 纳斯达克五年最佳, 高盛领涨金融板块
  2. `Canada Rescinds Digital-Services Tax` — 加拿大废除3%数字税以挽救对美贸易谈判
  3. `White House: Canada 'Caved' to Trump on Digital Taxes` — 白宫宣布胜利
  4. `Hassett: U.S.-Canada Trade Talks Back On` — 美加重启贸易谈判
  5. `Dollar Heads for Worst First Half in Decades` — 美元指数跌超10%，40年最差
  6. `Tech Industry Cheers Canada's Withdrawal` — 科技行业欢呼
  7. `EU Trade Chief Plans Trip to U.S. as Tariff Deadline Looms` — 欧盟贸易主管访美
  8. `White House: Higher Tariffs Expected` — 对未诚意谈判国家征收更高关税
  9. `Blockbuster Deals Stir Hopes for M&A Boom` — 美国并购交易额同比增长10%，三年最高
  10. `Reasons for Optimism as a Wild Quarter Wraps Up` — 季度收官的乐观理由
- **存档路径**: `https://web.archive.org/web/20260630000000/https://www.wsj.com/livecoverage/.../card/卡片-ID`

## Wayback Machine URL 构造规则

```
https://web.archive.org/web/YYYYMMDDHHMMSS/https://www.wsj.com/原始路径
```

- `YYYYMMDD` = 文章日期（如 20260630）
- `HHMMSS` = 时间戳（000000 即可，自动取当天的第一个快照）
- **当天文章可能无存档**：用前一天或当日后半夜的时间戳测试

## 潜在改进方向

- 测试 Scrapling `configure()` API（新版本弃用旧逻辑，`.configure()` 可能有所改进）
- 测试通过 `textise.iitty.com` / `12ft.io` / `r.jina.ai` 等文本代理（本次测试 jina.ai 同样被 DataDome 阻断）
- 测试浏览器代理池方案（需 residential proxy，当前 Hermes 环境不支持）
