# Cloud Deployment Architecture

## 架构

```
本地 Windows (Hermes)                  云 Ubuntu (Docker)
─────────────────────                 ─────────────────────
rss-scan (每5min)                     ┌───────────────┐
    │                                 │   Vue :80      │
news-pipeline (每30min)               └───────▲───────┘
  评分 → 分流 → 增强                          │
    │ POST /internal/news             ┌───────┴───────┐
    └────────────────────────────────►│  FastAPI :8001 │
                                      └───────▲───────┘
                                              │
                                      ┌───────┴───────┐
                                      │ PostgreSQL     │
                                      │ (内网, 无公网)  │
                                      └───────────────┘
```

## 云主机信息

- IP: 100.107.117.23
- 用户: administrator
- Docker Compose: `~/news-intel-platform/docker-compose.yml`

## 服务端口

| 服务 | 容器内 | 宿主机 | 访问控制 |
|------|:--:|:--:|------|
| Vue/Nginx | 80 | 80 | 公开 |
| FastAPI | 8000 | 8001 | 仅白名单 IP |
| PostgreSQL | 5432 | — | 仅 Docker 内网 |
| SearXNG | 8080 | 8080 | 公开 |
| n8n | 5678 | 5678 | 公开 |

## 部署命令

```bash
ssh administrator@100.107.117.23
cd ~/news-intel-platform
git pull
docker compose build --no-cache
docker compose up -d
docker compose ps
```

## API 端点 (15个)

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|:--:|------|
| POST | /register | - | 注册 |
| POST | /login | - | 登录 |
| GET | /me | JWT | 用户信息 |
| POST | /subscribe | JWT | 标签订阅 |
| POST | /upgrade-vip | JWT | VIP升级 |
| GET | /news | - | 新闻列表(分页) |
| GET | /news/{id} | - | 详情(VIP全文) |
| GET | /news/hot | - | 热门 |
| GET | /news/latest | - | 最新 |
| GET | /news/search | - | 搜索 |
| GET | /categories | - | 分类 |
| GET | /tags | - | 标签 |
| POST | /internal/news | Token | Hermes推送 |
| GET | /admin/* | JWT+Admin | 后台管理 |
| GET | /ads/random | - | 随机广告 |

## 管理员

admin@newsintel.com / admin123

## 安全加固

1. UFW 已启用，默认 deny incoming
2. DOCKER-USER 链: 白名单 IP + 默认 DROP
3. PostgreSQL 不暴露公网端口
4. FastAPI 仅白名单 IP 可访问
5. Hermes 推送用 X-Internal-Token 认证

## 数据库

PostgreSQL: `postgresql://news_admin:news_pass@postgres:5432/news_intel`

6 tables: articles, users, subscriptions, ads, settings, logs

## 常见问题

### 端口冲突
8000 已被 scrapling_mcp_server 占用 → API 用 8001

### JSON 字段 500 错误
`tags`/`entities` 在 DB 存储为 JSON 字符串，Pydantic 需要 `field_validator(mode='before')` 解析。

### 部署失败
```bash
docker compose logs api   # 看 API 日志
docker compose down -v    # 完全重置（会删数据！）
```
