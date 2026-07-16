Wiki at C:/Users/ChangHui/wiki. Git proxy socks5h://127.0.0.1:10808 for github.com. Obsidian 1.12.7 at D:\Program Files\Obsidian.
§
Sentinel Intelligence (news-intel-web/): Event Dossier pipeline v4.4 -> SQLite -> FastAPI -> Next.js 16 -> nginx:80. 6 pages (Situation/Detail/Explorer/Geo/Sources/Search). All products renamed from News to Sentinel. Cloud: 100.107.117.23, Docker 3-container, SQLite immutable read-only. Old news-intel-platform (Vue+PG) frozen.
§
用户是新闻情报平台构建者：偏好结构化决策(选项清单)、施工模式(直接执行不规划)、中文沟通。要求所有操作命令/步骤/架构写入wiki(~\wiki\BOSS_Doc\按类别建子目录+索引)。严格流程导向型工程师。
§
RSS: 94源(46RSS+18Nitter+6央媒),cron 5min, SOCKS5. Pipeline→~/.hermes/xxx-report.json. TaskScheduler备份git 12:00+full 18:00.
§
Sentinel V8 (news-platform-v8/): PG唯一数据源, SFTP退休→HTTP POST。FastAPI 11路由+Next.js 16。Docker nginx+frontend+backend+postgres :80。密钥.env, Alembic。VIP+广告保留。
§
V8决策: PG唯一源/SFTP废除/HTTP统一/密钥.env/VIP保留/广告保留/鉴权Dashboard公开admin需登录/article.category暂字符串/Alembic版本化迁移。
§
V8部署规则：Docker Compose卷external:true引用已有pgdata。前端fetch路径无/api/前缀（/news/ /auth/ /admin/）。SQLite→PG需DROP CASCADE。passlib+bcrypt在Py3.12不兼容，用hashlib.sha256作fallback。
§
fetch优化方向已冻结：①DEFAULT_HEADERS含Sec-Fetch-*头(france24/investing.com反爬关键)；②DirectClientPool domain隔离+LRU+线程安全；③Retry on 408/429/5xx不含403；④Scrapling timeout=秒×1000(曾bug:45ms)。禁止：Referer/TLS指纹/JS挑战/tldextract。
§
铁律(最高优先级): ①修改代码前必须获明确批准(禁止擅自patch/回退/改配置)。②每次代码修改后立即git add+commit+push(不累积)。③读完skill后同一轮必须发工具调用，不空等。④云部署优先于本地。⑤大文件>100MB→.gitignore。⑥commit标注Phase(P0-1,P1)。⑦中文沟通。⑧冻结架构后才执行。用户角色:新闻情报平台构建者·产品导向·结构化决策(选项清单)·施工模式(直接执行)。
§
代码审查教训(V1+V2): (1)Python else/except绑定问题—else跟随最近同级try,不继承外层if。控制流重构用if-not-early-return避免歧义。(2)subprocess.TimeoutExpired会跳出整个try块→超时恢复通道失效。关键路径必须独立try/except。(3)死代码参数(timeout)误导调用方,要么真接线要么删除。(4)指标分母陷阱: exhausted行被SQL排除导致填充率100%,需上报true_coverage。