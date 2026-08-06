Anthropic provider configured with proxy: Windows system proxy 127.0.0.1:10808 (Clash/V2Ray). API key updated and working through Hermes gateway after setting HTTPS_PROXY env var and restarting.
§
多智能体项目(开发运维/舆情自媒体/金融投资三飞轮): 环境权威文件=workspace\ENVIRONMENT.md。角色载体=每角色1个Hermes profile。调度=Kanban。决策合并: 副总+秘书长=总控C0; 记录员+巡检员=监审员A1(只读, 只能看/记/报/备)。
§
项目关键环境: 本机DESKTOP-IU8HLAO(100.126.188.44,win11,6c/16G/8GGPU,代理127.0.0.1:10808)。云主机100.107.117.23(ubuntu24,2c/3.8G,SSH=administrator/见.env,docker需sudo)。SearXNG活地址=100.107.117.23:8080(非.env里的旧100.97.252.20)。n8n=100.107.117.23:5678。本地LLM=LMStudio:1234 gemma-4-E4B。
§
项目模型路由: 开发/分析明确任务优先DeepSeek执行+Anthropic验收; 治理/创造性用Anthropic; 高频确定性用本地gemma或纯脚本不走LLM。Token熔断上限$10/天触顶锁死到次日零点。知识库四分区建在Documents\Obsidian Vault。公众号wx41aa598cc3faa87f是P1发布平台。P3只做模拟盘2%仓位5%止损。
§
Wiki pipeline location: C:\Users\ChangHui\wiki with scripts/llm-wiki-pipeline.py connecting to Hermes state.db at C:\Users\ChangHui\AppData\Local\hermes\state.db. SQLite CLI installed via winget at v3.53.3. Pipeline generates two-layer wiki (topics/ + entities/), semantic graph, and git commits.
§
Pipeline 架构：非并发（max-workers=1, LIMIT=5, rate-delay=0.3s）。6 步：1)Sync+Score 2)RSS FullText 3)batch.py级联抓取 4)事件聚类 5)云推送事件 6)增量推送文章。CONTENT_PUSH 已改为增量（fetch_at/t0 过滤）。
§
Cascade 策略链优先级：direct(1) → archive(1) → google_cache(1) → scrapling(2) → browser(3) → jina(2) → tavily(3) → searxng_alt(2) → search_snippet(1)。cascade_timeout=90s 软截止。已为 bloomberg、reuters、marketwatch、bbc.co.uk 配置域名画像。
§
Windows 兼容要点：os.kill(pid,0) 不支持（WinError 87），改用文件 mtime + BATCH_TIMEOUT 做进程锁。httpx 0.28 http2=True 有 SSL 间歇超时，设为 http2=False。SOCKS5 代理稳定，HTTP CONNECT 代理不稳定。Jina/Tavily 需通过 subprocess curl -4 调用绕过 httpx SSL 问题。
§
本机 IE 模型环境(2026-08): transformers 5.13.1 + gliner 0.2.28 + torch 2.13 CPU 装在系统 Python311(C:\Users\ChangHui\AppData\Local\Programs\Python\Python311), 不在 hermes venv。HF_ENDPOINT=https://hf-mirror.com 与 NO_PROXY=hf-mirror.com,huggingface.co 已持久化(setx+.env)。GLiNER small-v1 与 REBEL large 已本地化(~/.cache/huggingface/hub + ~/models/)。坑: hf-mirror 走代理卡死(663B/s), 必须 unset 代理直连(9.7MB/s); gliner from_pretrained 只认 HF 缓存结构不认本地路径。