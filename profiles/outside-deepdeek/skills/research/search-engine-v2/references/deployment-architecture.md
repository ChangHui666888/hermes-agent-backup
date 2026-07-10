# News Intelligence Platform — 部署架构参考

## 生产环境拓扑

```
本地 Windows (Hermes)              云 Ubuntu (Docker)
─────────────────────              ─────────────────
L0-L7 Pipeline                     Docker Compose
  │                                      │
  │  POST /internal/news                 │
  ├─────────────────────────────────────►│
  │  {url,content,tags,analysis,...}     ▼
  │                                FastAPI :8001 ──► PostgreSQL (内网)
  │                                      │
  │                                      ▼
  │                                Vue/Nginx :80
```

## Docker Compose 三个服务

```yaml
services:
  postgres:    # 内网隔离，无 ports 暴露
  api:         # 8001:8000，UFW+DOCKER-USER 白名单
  web:         # 80:80，公开
```

## 安全加固要点

1. **Docker 端口映射绕过 UFW**: Docker 的 `-p 0.0.0.0:PORT` 操作 iptables NAT 表，优先级高于 UFW。
   修复: 在 DOCKER-USER 链中添加规则（Docker 尊重此链），默认 DROP + 白名单 ACCEPT。

2. **PostgreSQL 不对外**: 移除 docker-compose 的 `ports` 映射，仅 Docker 内网可达。

3. **部署方式**: 用 Python paramiko SSH + tar 上传 + `docker compose build --no-cache && up -d`。

## 常见坑

- **bcrypt 版本冲突**: `passlib[bcrypt]` 在 Docker Alpine Python 3.11 中 `bcrypt.__about__` 缺失。
  修复: 改用 `hashlib.sha256 + secrets.token_hex(16)` 替代。

- **端口冲突**: 云主机可能已有服务占用 8000/80/443。用 `ss -tlnp` 先查再定端口。

- **Docker socket 权限**: 用户需在 `docker` 组，`usermod -aG docker <user>` 后需重连 SSH。

## Hermes 推送格式

```
POST /internal/news
X-Internal-Token: hermes-pipeline-secret-2026

{
  "url": "...", "title": "...", "content_md": "...",
  "tags": ["..."], "entities": {...}, "analysis": {...},
  "score_total": 85, "tier": "A", ...
}
```

## 数据库六表

articles / users / subscriptions / ads / settings / logs
