不要手动修改 Windows 注册表中的 HTTP_PROXY/HTTPS_PROXY 代理环境变量。代理由代理软件（如 Clash/V2Ray）自身管理，不要去配置或删除。如需处理代理相关问题，让用户自己操作代理软件。
§
自媒体内容生产专家/管理者，精通从选题发现到策略学习的完整内容工业流程（13节点DAG）。偏好基于Hermes Agent原生集成的架构方案。中文沟通、要求工作系统必须真实可运行（不仅是规划），重视成本/Token消耗透明度、角色职责边界清晰度和系统状态可见性。严格对照规范落地（"照做"模式）。
§
工程规范: 所有cron脚本遵循统一模板—Shell仅定位+启动Python, Python仅argparse+logging+调用业务函数, 业务返回report dict写入JSON。循环任务用Hermes Cron(every 5m/30m), 固定时间用Task Scheduler(12:00/18:00)。Shell和.py必须同目录(rss-scan模式)。create "30m"=once, add "every 30m"=循环。所有cron脚本放~/.hermes/scripts/。RSS隔离: 3次失败→隔离30分钟。Qwen超时60s, max_tokens=1024。评分阈值: Tier A≥90, B=60-89, C<60。备份: Git每日+全量F盘每3天, 保留15天, restore.bat双YES确认。PYTHONUNBUFFERED=1保证cron日志。
§
中文交流。Windows 10 + Hermes Agent，云端 Ubuntu VPS (100.107.117.23, 3.9G RAM, Docker)。部署规则: Docker构建只在云端，不在本地。每次代码修改必须 git commit + push (hermes-agent-backup + news-platform-v8)。未经批准禁止操作。知识库: C:/Users/ChangHui/wiki。
§
架构偏好: 先验证再开发、零LLM确定性规则优先、自动化无人值守、Event-centric(非Article-centric)。评分: Tier A≥90, B=60-89, C<60。Scrapling>浏览器作为抓取工具优先级。
§
产品目标: 事件情报分析平台(非新闻后台/CMS/GIS)。V1架构已冻结: RSS→Score→Fetch→Aggregate→Sync→PG→API→Web (71 events)。V2方向: MapLibre、Event-Map联动、GDELT Tone、D3关系图。geo monitor已有region/type/limit过滤。
§
行为铁律(最优先): ①每次修改后git commit+push双仓库(hermes-agent-backup+news-platform-v8)。②未经批准禁止修改文件(擅自patch/回退会导致用户不满)。③部署后用浏览器验证。④先输出任务清单+验收标准再执行。⑤读完skill后同一轮必须发工具调用。