用户风格: 实用保守型。成本敏感($10/天熔断优先于一切)、要看过真实样品再推进(三条线各出样品)、合规优先(审宪法仔细才定稿)。偏好零成本方案先用再升级(edge-tts先跑、跳过AI生图用HTML渲染)。所有高风险操作要求先隔离测试再碰真实环境。
§
系统审计扫描时，必须同时检查 LLM Wiki (~/wiki/) 和 Obsidian Vault (Documents/Obsidian Vault/) 两个知识库位置。前者是自动生成的技术知识库，后者是宪法/角色定义/原始素材的治理分区。遗漏任一都会产生不完整的分析报告。
§
实用保守型技术用户，运行多智能体系统（三飞轮：开发运维/舆情自媒体/金融投资）。要求所有修改先测试验证（"先进行5轮测试"），不喜欢直接推到生产。偏好零成本方案先用再升级。
§
分析风格偏好：要求结构化报告（问题诊断→根因→修复→验证），有明确的发现/结论/修复优先级。深度技术根因分析（如 httpx SSL 握手、IPv6 解析、Playwright Target crashed）而非表面症状。
§
项目架构：双知识库（~/wiki/ 技术知识库 + Obsidian Vault/ 治理宪法+素材），宪法驱动多 Agent 治理。三个 cron 任务（rss-scan 每5分钟稳定运行、auto-pipeline 每15分钟含 cascade 抓取、news-pipeline 暂停）。outside-deepdeek 是执行 profile。
§
cascade 抓取策略链：direct → archive.org → google_cache → jina_reader(IPv4 via curl) → tavily(AI摘要) → search_snippet。强反爬站点(Reuters/MarketWatch) browser 被检测杀死，靠 RSS FullText + jina/tavily 兜底。
§
User is a conservative optimizer: prefers small/safe batch sizes (5 URLs) to validate before scaling, emphasizes RSS zero-cost fallback over expensive strategies, and proactively suggests preventive measures (risk analysis, QC checks, fallback paths) rather than just fixing surface issues.
§
网络调试偏好: 先测小批次再扩（5 URL起步），每次改完要跑 3 轮以上验证。所有优化必须有 pipeline log 或测试输出做证据支撑，不依赖"应该能行"的推断。级联策略配置优先考虑零成本方案(RSS FullText)，极限兜底才用付费 API(Tavily)。