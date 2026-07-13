Wiki at C:/Users/ChangHui/wiki. Git proxy socks5h://127.0.0.1:10808 for github.com. Obsidian 1.12.7 at D:\Program Files\Obsidian.
§
Sentinel Intelligence (news-intel-web/): Event Dossier pipeline v4.4 -> SQLite -> FastAPI -> Next.js 16 -> nginx:80. 6 pages (Situation/Detail/Explorer/Geo/Sources/Search). All products renamed from News to Sentinel. Cloud: 100.107.117.23, Docker 3-container, SQLite immutable read-only. Old news-intel-platform (Vue+PG) frozen.
§
执行铁律: 读过skill后同一轮必须发出第一个工具调用，不得停在计划阶段等用户批准下一步。plan→execute断裂是严重违例。写计划可以，但必须紧接着执行工具调用。"If you have tools available to accomplish the task, use them instead of telling the user what you would do."
§
工程规范: 云部署优先于本地。每次修改后git add -A && git commit && git push。大文件(>100MB)需.gitignore排除，否则GitHub拒绝推送→git reset --soft + git rm --cached修复。
§
用户是新闻情报平台构建者：偏好结构化决策(选项清单)、施工模式(直接执行不规划)、中文沟通。要求所有操作命令/步骤/架构写入wiki(~\wiki\BOSS_Doc\按类别建子目录+索引)。严格流程导向型工程师。
§
RSS: 94源(46RSS+18Nitter+6央媒),cron 5min, SOCKS5. Pipeline→~/.hermes/xxx-report.json. TaskScheduler备份git 12:00+full 18:00.
§
User is a product-oriented engineer building intelligence platforms. Values: efficiency, real verification, structured decision-making, delivering running systems. Prefers Chinese. Insists on cloud-only deployment (no local builds), frozen architecture before execution, and product polish (renamed to Sentinel Intelligence).
§
Sentinel V8 (news-platform-v8/): PG唯一数据源, SFTP退休→HTTP POST。FastAPI 11路由+Next.js 16。Docker nginx+frontend+backend+postgres :80。密钥.env, Alembic。VIP+广告保留。
§
V8决策: PG唯一源/SFTP废除/HTTP统一/密钥.env/VIP保留/广告保留/鉴权Dashboard公开admin需登录/article.category暂字符串/Alembic版本化迁移。
§
每完成一个任务/子任务，代码修改后必须立即 git add -A && git commit && git push 到 GitHub。不得批量累积后统一提交。commit message 需标注对应 Phase（如 P0-1, P1 等）。