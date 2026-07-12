# News Intelligence Platform — Deploy Commands

## Initial deploy

```bash
# From local (Windows), using paramiko:
python -c "
import paramiko, tarfile, io, os
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

# Tar project (exclude node_modules, .next, .git, __pycache__)
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w:gz') as tar:
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.next', '.git', '__pycache__', 'data')]
        for f in files:
            if f.endswith('.pyc'): continue
            tar.add(os.path.join(root, f), os.path.relpath(os.path.join(root, f), SRC))

# Upload
sftp = client.open_sftp()
buf.seek(0)
sftp.putfo(buf, '/tmp/project.tar.gz')
sftp.close()

# Extract on remote
client.exec_command('rm -rf /home/administrator/project && mkdir -p /home/administrator/project && tar xzf /tmp/project.tar.gz -C /home/administrator/project')
client.close()
"
```

## Rebuild one service

```bash
ssh administrator@HOST "cd /home/administrator/news-intel-web && docker compose up -d --build frontend"
```

## Full redeploy

```bash
ssh administrator@HOST "cd /home/administrator/news-intel-web && docker compose up -d --build"
```

## Verify

```bash
curl http://HOST/api/v1/dashboard
curl http://HOST | grep '<title>'
```

## Check logs

```bash
ssh administrator@HOST "cd /home/administrator/news-intel-web && docker compose logs backend --tail=20"
```
