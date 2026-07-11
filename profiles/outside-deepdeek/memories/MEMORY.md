Wiki at C:/Users/ChangHui/wiki. SCHEMA.md, index.md, log.md, .obsidian/app.json, graph.html. scripts/wiki-graph.py → data.json. scripts/wiki-sync.sh auto-commits + rebuilds graph + pushes GitHub. Hermes cron job 'wiki-sync' (every 30m, no-agent). Cron fires if gateway running (hermes gateway install). Obsidian 1.12.7 at D:\Program Files\Obsidian. Launch: hermes-wiki.sh / hermes-wiki.cmd (one-click Hermes+Wiki). Bash aliases: wiki, wiki-obsidian, wiki-graph, wiki-start, hermes-wiki. Git proxy socks5h://127.0.0.1:10808 for github.com.
§
RSS系统: 94源, cron每5min, no_agent。隔离: 连续失败≥3→隔离30min(1800s)。重置: rm ~/.hermes/rss-scanner-state.json。Nitter 18源+中文央媒6源。开机自启+保活已配。SOCKS5代理境外源,国内直连。
§
search-engine-v2 v2.4: 10层流水线(L0-L9)。评分≥90A(DS Flash)/60-89B(Qwen3 1024tokens 60s合并1调用)/<60C(Python)。V4聚合器: Event-Centric 3-phase(SAEO+Location硬约束+date fix), 零LLM。去重: sync.py:47+ pipeline.py:66。V1 Schema: PG event-centric 11新表, 24sources/35entities/210links已迁移。Cron: "every Xm"+末尾""空prompt。Backup: TaskScheduler Git 12:00+全量F盘18:00(15d)。restore.bat双YES+/MIR/backup.ok。
§
执行铁律: 读过skill后同一轮必须发出第一个工具调用，不得停在计划阶段等用户批准下一步。plan→execute断裂是严重违例。写计划可以，但必须紧接着执行工具调用。"If you have tools available to accomplish the task, use them instead of telling the user what you would do."
§
Default model switched: claude-fable-5→deepseek-v4-pro @ DeepSeek. Entity weights: Kevin Warsh/凯文·沃什/沃什/沃舎=20, Warsh=20, Powell/鲍威尔=20 same tier.
§
用户要求：所有操作命令、步骤、架构设计需要写入wiki，目录为 ~/wiki/BOSS_Doc/，按类别建子目录并维护索引。每次涉及部署、配置、命令的操作完成后同步更新wiki。
§
工程规范: Shell仅SCRIPT_DIR+python启动; Python用argparse+logging不硬编码路径; 业务返回report dict→~/.hermes/xxx-report.json; 退出码0=OK/1=Pipeline/2=Import.
§
用户是新闻情报平台构建者：偏好结构化决策(选项清单)、施工模式(直接执行不规划)、中文沟通。要求所有操作命令/步骤/架构写入wiki(~\wiki\BOSS_Doc\按类别建子目录+索引)。严格流程导向型工程师。
§
Cron：rss-scan(5min)+news-pipeline(30min)用Hermes Cron。备份git(12:00)+full(18:00)用TaskScheduler。脚本放~/.hermes/scripts/。日志: scripts/logs/*.log。工程规范: Shell仅启动, Python argparse+logging, 业务返回report→~/.hermes/xxx-report.json。