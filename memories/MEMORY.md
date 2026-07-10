Anthropic provider configured with proxy: Windows system proxy 127.0.0.1:10808 (Clash/V2Ray). API key updated and working through Hermes gateway after setting HTTPS_PROXY env var and restarting.
§
多智能体项目(开发运维/舆情自媒体/金融投资三飞轮): 环境权威文件=workspace\ENVIRONMENT.md。角色载体=每角色1个Hermes profile。调度=Kanban。决策合并: 副总+秘书长=总控C0; 记录员+巡检员=监审员A1(只读, 只能看/记/报/备)。
§
项目关键环境: 本机DESKTOP-IU8HLAO(100.126.188.44,win11,6c/16G/8GGPU,代理127.0.0.1:10808)。云主机100.107.117.23(ubuntu24,2c/3.8G,SSH=administrator/见.env,docker需sudo)。SearXNG活地址=100.107.117.23:8080(非.env里的旧100.97.252.20)。n8n=100.107.117.23:5678。本地LLM=LMStudio:1234 gemma-4-E4B。
§
项目模型路由: 开发/分析明确任务优先DeepSeek执行+Anthropic验收; 治理/创造性用Anthropic; 高频确定性用本地gemma或纯脚本不走LLM。Token熔断上限$10/天触顶锁死到次日零点。知识库四分区建在Documents\Obsidian Vault。公众号wx41aa598cc3faa87f是P1发布平台。P3只做模拟盘2%仓位5%止损。
§
Wiki pipeline location: C:\Users\ChangHui\wiki with scripts/llm-wiki-pipeline.py connecting to Hermes state.db at C:\Users\ChangHui\AppData\Local\hermes\state.db. SQLite CLI installed via winget at v3.53.3. Pipeline generates two-layer wiki (topics/ + entities/), semantic graph, and git commits.