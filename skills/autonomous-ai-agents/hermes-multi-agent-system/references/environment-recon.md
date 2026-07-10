# Environment recon for a Hermes multi-agent build

Run these BEFORE planning. Write findings to a single `ENVIRONMENT.md`.
Verify every IP/port/credential the user gave you — expect drift.

## Hermes state
```bash
hermes --version
hermes config show                    # NOTE: 'config list' is NOT valid; subcommands: show|edit|set|path|env-path|check|migrate
hermes mcp list
hermes cron list --all
hermes profile list
hermes tools list
hermes skills list
```

## Config + secrets (read structure, redact values)
```bash
# config.yaml has model/providers/auxiliary routing, approvals, curator, kanban, etc.
read config.yaml   # or: hermes config path
# .env holds provider keys + custom infra URLs. Grep, don't dump:
grep -iE "^SEARXNG_URL|^N8N|^DEEPSEEK|^ANTHROPIC|^LM_API_KEY|_BASE_URL|_API_KEY" "$HERMES_HOME/.env" | sed -E 's/(=.{6}).*/\1****/'
```

## Cost data lives in state.db (no separate usage table)
```bash
# sessions table already carries per-session cost:
#   estimated_cost_usd, actual_cost_usd, cost_status, input_tokens, output_tokens,
#   cache_read_tokens, cache_write_tokens, billing_provider, model, started_at (unix ts)
# 'hermes insights --days N' aggregates from this. Providers Hermes can't price
# (deepseek, local gemma) show cost 0 / status 'unknown' — token-estimate them.
```

## LAN / cloud infra (Tailscale-style setups)
```bash
tailscale status                       # map hostnames↔IPs; the user's "my IP" is often a DIFFERENT peer
curl -s -m4 -x http://127.0.0.1:<proxyport> https://www.google.com -o /dev/null -w "%{http_code}\n"   # proxy check
ping -n 2 <cloud-ip>
curl -s -m4 http://<host>:<port>/ -o /dev/null -w "%{http_code}\n"   # service liveness; test EACH candidate host
```

### SSH to cloud host (use system Python + paramiko; sshpass usually absent on Windows)
```python
# system python: C:\Users\<u>\AppData\Local\Programs\Python\Python311\python.exe -m pip install paramiko
import paramiko
c = paramiko.SSHClient(); c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(host, username=user, password=pw, timeout=8)
i,o,e = c.exec_command("whoami; docker --version; nproc; free -h | grep Mem; df -h / | tail -1; groups")
print(o.read().decode(), e.read().decode())
```
- `root` password login is often disabled → use the sudo user.
- `docker ps` may need the user in the `docker` group; `sudo -S` piping is BLOCKED — make it an approval-card / manual step.

## Windows / OneDrive gotcha
`C:\Users\<u>\Documents` and subfolders can be OneDrive "known folders". `listdir`
works but `mkdir`/file-create throws `WinError 2 (file not found)` until the folder
is "hydrated". Fix: call `os.listdir(path)` first (wakes it), retry mkdir 2-3× with
a 1s sleep. Registry `User Shell Folders\Personal` may still say the path is local
even when OneDrive intercepts writes.
