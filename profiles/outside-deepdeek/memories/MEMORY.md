Wiki at C:/Users/ChangHui/wiki. SCHEMA.md, index.md, log.md, .obsidian/app.json, graph.html. scripts/wiki-graph.py → data.json. scripts/wiki-sync.sh auto-commits + rebuilds graph + pushes GitHub. Hermes cron job 'wiki-sync' (every 30m, no-agent). Cron fires if gateway running (hermes gateway install). Obsidian 1.12.7 at D:\Program Files\Obsidian. Launch: hermes-wiki.sh / hermes-wiki.cmd (one-click Hermes+Wiki). Bash aliases: wiki, wiki-obsidian, wiki-graph, wiki-start, hermes-wiki. Git proxy socks5h://127.0.0.1:10808 for github.com.
§
RSS系统: 94源, cron每5min, no_agent。隔离: 连续失败≥3→隔离30min(1800s)。重置: rm ~/.hermes/rss-scanner-state.json。Nitter 18源+中文央媒6源。开机自启+保活已配。SOCKS5代理境外源,国内直连。
§
search-engine-v2 v2.3: +news_intel引擎(五维评分+三路增强), +cloud推送(pusher.py→FastAPI), +Hermes cron(30min, --repeat 99999必须加否则只跑1次). 坑: Qwen3 system角色→400 Bad Request,用user角色替代. bcrypt→hashlib避免版本冲突. Docker绕过UFW→DOCKER-USER链白名单. RSS全隔离→删rss-scanner-state.json. RSS扫描16.89s(94源), Pipeline 30s(200篇评分+增强). [ref: deployment-pitfalls.md]
§
执行铁律: 读过skill后同一轮必须发出第一个工具调用，不得停在计划阶段等用户批准下一步。plan→execute断裂是严重违例。写计划可以，但必须紧接着执行工具调用。"If you have tools available to accomplish the task, use them instead of telling the user what you would do."
§
Default model switched: claude-fable-5→deepseek-v4-pro @ DeepSeek. Entity weights: Kevin Warsh/凯文·沃什/沃什/沃舎=20, Warsh=20, Powell/鲍威尔=20 same tier.
§
news-intel-platform部署: GitHub repo ChangHui666888/news-intel-platform, 云主机100.107.117.23(administrator/root123root!@), Docker Compose(FastAPI:8001+Vue:80+PostgreSQL内网)。UFW+DOCKER-USER链白名单(100.126.188.44+100.120.73.47)。Hermes cron create在PowerShell需单行+末尾""空prompt; --repeat 99999否则只跑1次。push: tar.gz→sftp→docker compose up -d。
§
用户要求：所有操作命令、步骤、架构设计需要写入wiki，目录为 ~/wiki/BOSS_Doc/，按类别建子目录并维护索引。每次涉及部署、配置、命令的操作完成后同步更新wiki。
§
工程规范(对齐rss-scanner): Shell仅SCRIPT_DIR+python启动; Python用argparse+logging; 业务返回report dict→写~/.hermes/xxx-report.json; 摘要动态循环tiers不硬编码; 退出码0=OK/1=Pipeline/2=Import/3=Config; 不硬编码路径不用cd。评分:Tier A≥90(DeepSeek), B60-89(Qwen3), C<60(Python)。Qwen超时60s/max_tokens 1024/合并3调用为1。RSS隔离3次失败→30min。云推送5s超时/3次失败跳过。Hermes cron create在PowerShell需单行+末尾""。