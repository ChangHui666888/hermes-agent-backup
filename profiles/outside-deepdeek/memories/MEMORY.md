Wiki at C:/Users/ChangHui/wiki. SCHEMA.md, index.md, log.md, .obsidian/app.json, graph.html. scripts/wiki-graph.py → data.json. scripts/wiki-sync.sh auto-commits + rebuilds graph + pushes GitHub. Hermes cron job 'wiki-sync' (every 30m, no-agent). Cron fires if gateway running (hermes gateway install). Obsidian 1.12.7 at D:\Program Files\Obsidian. Launch: hermes-wiki.sh / hermes-wiki.cmd (one-click Hermes+Wiki). Bash aliases: wiki, wiki-obsidian, wiki-graph, wiki-start, hermes-wiki. Git proxy socks5h://127.0.0.1:10808 for github.com.
§
RSS系统: 94源, cron每5min, no_agent。隔离: 连续失败≥3→隔离30min(1800s)。重置: rm ~/.hermes/rss-scanner-state.json。Nitter 18源+中文央媒6源。开机自启+保活已配。SOCKS5代理境外源,国内直连。
§
search-engine-v2 v2.4: news_intel五维评分+Tier A≥90(DS Flash)/B60-89(Qwen3 1024tokens 60s超时合并1调用)/C<60(Python规则). aggregator v2: 导语Jaccard≥0.20+shared_ent≥2, HTML过滤. L9: Tier A→DeepSeek, 其余→Qwen3. L8/L9待集成pipeline(先手动验证). V1 Schema: PostgreSQL event-centric(11新表), 迁移完成: 24sources/35entities/210links. Cloud: 100.107.117.23(Docker:FastAPI:8001+Vue:80+PG内网). Cron: "every Xm"非"once", --repeat 99999, --no-agent. Backup: git(每日12:00 TaskScheduler)+full(F盘每日18:00,保留14天). restore.bat双YES确认+backup.ok验证.
§
执行铁律: 读过skill后同一轮必须发出第一个工具调用，不得停在计划阶段等用户批准下一步。plan→execute断裂是严重违例。写计划可以，但必须紧接着执行工具调用。"If you have tools available to accomplish the task, use them instead of telling the user what you would do."
§
Default model switched: claude-fable-5→deepseek-v4-pro @ DeepSeek. Entity weights: Kevin Warsh/凯文·沃什/沃什/沃舎=20, Warsh=20, Powell/鲍威尔=20 same tier.
§
news-intel-platform部署: GitHub repo ChangHui666888/news-intel-platform, 云主机100.107.117.23(administrator/root123root!@), Docker Compose(FastAPI:8001+Vue:80+PostgreSQL内网)。UFW+DOCKER-USER链白名单(100.126.188.44+100.120.73.47)。Hermes cron create在PowerShell需单行+末尾""空prompt; --repeat 99999否则只跑1次。push: tar.gz→sftp→docker compose up -d。
§
用户要求：所有操作命令、步骤、架构设计需要写入wiki，目录为 ~/wiki/BOSS_Doc/，按类别建子目录并维护索引。每次涉及部署、配置、命令的操作完成后同步更新wiki。
§
工程规范: Shell仅SCRIPT_DIR+python启动; Python用argparse+logging不硬编码路径; 业务返回report dict→~/.hermes/xxx-report.json; 退出码0=OK/1=Pipeline/2=Import.