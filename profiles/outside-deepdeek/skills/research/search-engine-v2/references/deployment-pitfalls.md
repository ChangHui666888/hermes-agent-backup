# Cloud Deployment Pitfalls

## Docker bypasses UFW

**Problem**: Docker `-p 0.0.0.0:8001:8000` adds iptables DNAT rules in FORWARD chain that take priority over UFW rules. Even `ufw deny 8001` won't block Docker-exposed ports.

**Fix**: Add IP whitelist to DOCKER-USER chain:
```bash
iptables -I DOCKER-USER -s <whitelist_ip> -j ACCEPT
iptables -A DOCKER-USER -j DROP
```

**PostgreSQL**: Never expose to `0.0.0.0`. Remove `ports` from docker-compose.yml entirely — only accessible within Docker network.

## bcrypt version conflict

**Problem**: `passlib` + `bcrypt` 5.0 raises `AttributeError: module 'bcrypt' has no attribute '__about__'`

**Fix**: Replace passlib/bcrypt with hashlib:
```python
import hashlib, secrets
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.sha256((salt + password).encode()).hexdigest()
```

## Qwen3-1.7B 400 Bad Request

**Problem**: LM Studio `/v1/chat/completions` returns 400 when `system` role or `temperature` is passed.

**Fix**: Use single `user` role message, remove `temperature` parameter, timeout 60s:
```python
json={
    "model": "qwen3-1.7b-instruct",
    "messages": [{"role": "user", "content": f"{prompt}\n\n{user_text}"}],
    "max_tokens": 1024,
}
```

## Port conflicts

Check before deploying: `ss -tlnp | grep -E ":(80|8000|8001|8080|5432)"`

- 8000: often occupied by scrapling_mcp_server or n8n
- 8080: SearXNG
- Solution: map API to 8001:8000 in docker-compose.yml

## Pydantic JSON field validation

**Problem**: SQLAlchemy stores `tags`/`entities` as JSON strings, Pydantic expects list/dict → 500 error.

**Fix**: Add `field_validator(mode='before')` in schemas.py:
```python
@field_validator('tags', 'entities', mode='before')
@classmethod
def parse_json_fields(cls, v):
    if isinstance(v, str):
        try: return json.loads(v)
        except: return v
    return v
```

## RSS source quarantine

**Problem**: 3 consecutive failures → 24h quarantine → all 94 feeds blocked.

**Fix (2026-07-10)**: Changed to 30min quarantine. Reset: `rm ~/.hermes/rss-scanner-state.json`.
