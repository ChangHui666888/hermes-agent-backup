不要手动修改 Windows 注册表中的 HTTP_PROXY/HTTPS_PROXY 代理环境变量。代理由代理软件（如 Clash/V2Ray）自身管理，不要去配置或删除。如需处理代理相关问题，让用户自己操作代理软件。
§
自媒体/情报平台专家，精通13节点DAG。偏好Hermes原生集成。中文沟通。要求系统真实可运行。重视成本透明、角色边界清晰、状态可见。严格照做模式。代码审查做多轮结构化审计：逐行逐文件，不接受绕过的修复要求拆除根因。对指标真实性有强迫要求(分母陷阱、全零信号)。多次强调硬编码密钥进git是严重问题。
§
工程规范: cron脚本统一模板(Shell定位→Python argparse+logging→返回JSON report)。循环任务Hermes Cron(every 5m/30m), 固定时间Task Scheduler(12:00/18:00)。Shell+.py同目录。RSS隔离3次失败→30min。Qwen超时60s/max_tokens=1024。评分Tier A≥90 B=60-89 C<60。PYTHONUNBUFFERED=1。exhausted机制: retry_count≥3→fetch_strategy='exhausted'不再重试。true_coverage含exhausted分母。
§
中文交流。Windows 10 + Hermes Agent，云端 Ubuntu VPS (100.107.117.23, 3.9G RAM, Docker)。部署规则: Docker构建只在云端，不在本地。每次代码修改必须 git commit + push (hermes-agent-backup + news-platform-v8)。未经批准禁止操作。知识库: C:/Users/ChangHui/wiki。
§
架构偏好: 先验证再开发、零LLM确定性规则优先、自动化无人值守、Event-centric(非Article-centric)。评分: Tier A≥90, B=60-89, C<60。Scrapling>浏览器作为抓取工具优先级。
§
产品目标: 事件情报分析平台(非新闻后台/CMS/GIS)。V1架构已冻结: RSS→Score→Fetch→Aggregate→Sync→PG→API→Web (71 events)。V2方向: MapLibre、Event-Map联动、GDELT Tone、D3关系图。geo monitor已有region/type/limit过滤。
§
行为铁律(最优先): ①每次修改后git commit+push双仓库(hermes-agent-backup+news-platform-v8)。②未经批准禁止修改文件(擅自patch/回退会导致用户不满)。③部署后用浏览器验证。④先输出任务清单+验收标准再执行。⑤读完skill后同一轮必须发工具调用。