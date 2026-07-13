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
Cloud: 100.107.117.23 (Ubuntu 24.04 Docker 29.5.3). SSH: administrator / root123root!@. Deploy at /home/administrator/news-intel-web/. SQLite at data/news_intel.db (ro+immutable mount). 3 containers: frontend(node:22-alpine), backend(python:3.12-slim), nginx(nginx:alpine). No Node.js on host. V1 uses SQLite only, no PG. Old platform (Vue+PG) permanently frozen.
§
Git push超时: 大文件>100MB(.rar/.tar.gz)被拒→reset--soft+rm--cached+.gitignore排除规则。每次改完必须add+commit+push。代理socks5h://127.0.0.1:10808用于github.com。