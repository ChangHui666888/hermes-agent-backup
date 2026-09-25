Anthropic provider 走 Windows 系统代理 127.0.0.1:10808(Clash)，需设 HTTPS_PROXY 后重启 Hermes 才生效。
§
多智能体项目(开发运维/舆情自媒体/金融投资三飞轮): 环境权威文件=workspace\ENVIRONMENT.md。角色载体=每角色1个Hermes profile。调度=Kanban。决策合并: 副总+秘书长=总控C0; 记录员+巡检员=监审员A1(只读, 只能看/记/报/备)。
§
项目关键环境: 本机DESKTOP-IU8HLAO(100.126.188.44,win11,6c/16G/8GGPU,代理127.0.0.1:10808)。云主机100.107.117.23(ubuntu24,2c/3.8G,SSH=administrator/见.env,docker需sudo)。SearXNG活地址=100.107.117.23:8080(非.env里的旧100.97.252.20)。n8n=100.107.117.23:5678。本地LLM=LMStudio:1234 gemma-4-E4B。
§
项目模型路由: 开发/分析明确任务优先DeepSeek执行+Anthropic验收; 治理/创造性用Anthropic; 高频确定性用本地gemma或纯脚本不走LLM。Token熔断上限$10/天触顶锁死到次日零点。知识库四分区建在Documents\Obsidian Vault。公众号wx41aa598cc3faa87f是P1发布平台。P3只做模拟盘2%仓位5%止损。
§
Wiki pipeline: C:\Users\ChangHui\wiki (scripts/llm-wiki-pipeline.py → hermes state.db)；生成 topics/+entities/ 双层 wiki + 语义图谱 + git 提交。
§
Pipeline 架构：非并发（max-workers=1, LIMIT=5, rate-delay=0.3s）。6 步：1)Sync+Score 2)RSS FullText 3)batch.py级联抓取 4)事件聚类 5)云推送事件 6)增量推送文章。CONTENT_PUSH 已改为增量（fetch_at/t0 过滤）。
§
Cascade 策略链优先级：direct(1) → archive(1) → google_cache(1) → scrapling(2) → browser(3) → jina(2) → tavily(3) → searxng_alt(2) → search_snippet(1)。cascade_timeout=90s 软截止。已为 bloomberg、reuters、marketwatch、bbc.co.uk 配置域名画像。
§
Windows 兼容要点：os.kill(pid,0) 不支持（WinError 87），改用文件 mtime + BATCH_TIMEOUT 做进程锁。httpx 0.28 http2=True 有 SSL 间歇超时，设为 http2=False。SOCKS5 代理稳定，HTTP CONNECT 代理不稳定。Jina/Tavily 需通过 subprocess curl -4 调用绕过 httpx SSL 问题。
§
本机 IE 模型环境: transformers+gliner+torch(CPU) 装在系统 Python311(不在 hermes venv); HF_ENDPOINT=hf-mirror.com + NO_PROXY 已持久化; GLiNER small-v1 与 REBEL large 已本地化。坑: hf-mirror 走代理卡死(必须 unset 代理直连); gliner from_pretrained 只认 HF 缓存结构不认本地路径。
§
workspace 工具链(共用 8777 前端): bundle(网关8777, 抖音CDP9335, 成品 state\downloads\douyin_<作者>) + scene-splitter(8765→/splitter/, 产物 <视频名>_clips) + watermark-cleaner(8778→/watermark/)。坑1: Hermes 环境导出 PORT=8648, 从 Hermes 会话重启 bundle 网关必须显式 set PORT=8777, 否则绑 127.0.0.1:8648 劫持 Hermes Studio → "Error: Connection error"。坑2: bundle\bin\ffmpeg 只有 ffmpeg.exe(9.0.1 essentials, 无 ffprobe), ffprobe 须独立解析。抖音作者名取 aweme/detail 接口(权威), 扫页面文字会拿推荐位作者; cdp.evaluate 注入 JS 禁写正则(模板转义会静默失效)。默认剪辑素材 D:\Douyin\MV\待分段\douyin_阿木（山野）。