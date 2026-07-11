不要手动修改 Windows 注册表中的 HTTP_PROXY/HTTPS_PROXY 代理环境变量。代理由代理软件（如 Clash/V2Ray）自身管理，不要去配置或删除。如需处理代理相关问题，让用户自己操作代理软件。
§
自媒体内容生产专家/管理者，精通从选题发现到策略学习的完整内容工业流程（13节点DAG）。偏好基于Hermes Agent原生集成的架构方案。中文沟通、要求工作系统必须真实可运行（不仅是规划），重视成本/Token消耗透明度、角色职责边界清晰度和系统状态可见性。严格对照规范落地（"照做"模式）。
§
用户：自媒体内容生产专家/架构导向型工程师。偏好：施工模式（直接构建可运行系统）、结构化决策（选项清单）、成本透明度、Agent角色边界清晰、中文交流。工程规范：Shell只负责启动、Python只负责入口、业务全在模块内。所有Cron Job遵循同一模板（对齐rss-scanner）。循环任务→Hermes Cron，固定时间→Windows Task Scheduler。Windows环境用绝对路径避免git-bash路径问题。脚本必须PYTHONUNBUFFERED=1保证cron日志可见。备份策略：Git每日+全量F盘每3天，保留15天。
§
用户是严谨的流程/架构导向型工程师。要求数据抓取优先选优雅工具（Scrapling > 浏览器），出错后必须做根因分析并建立永久防护机制（规则+技能+记忆三步）。偏好伪代码形式的硬规则（V1修复版风格），而非软建议。对时间线/数据一致性有强迫级要求，不接受"看起来对"的模糊结果。重视知识沉淀——成功和失败的策略都要写入 skill + memory，关键词必须精准确保下次匹配。
§
Hermes cron关键陷阱：create "30m" = once（只执行一次），add "every 30m" = 循环。news-pipeline cron: hermes cron add "every 30m" --name news-pipeline --script news-pipeline.py --workdir "C:\Users\ChangHui\AppData\Local\hermes\scripts" --no-agent。所有cron脚本放~/.hermes/scripts/，不加--workdir时默认从此目录解析。