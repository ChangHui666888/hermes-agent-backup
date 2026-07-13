# Cloud Deployment Pattern (Paramiko tar upload)

```python
import paramiko, os, tarfile, io, time

HOST = "100.107.117.23"
USER = "administrator"
PASS = "root123root!@"
SRC = os.path.expanduser("~/workspace/project")

# 1. Tar (exclude node_modules, .next, .git, __pycache__)
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w:gz') as tar:
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ('node_modules', '.next', '.git', '__pycache__')]
        for f in files:
            if f.endswith('.pyc'): continue
            full = os.path.join(root, f)
            arc = os.path.relpath(full, SRC)
            tar.add(full, arc)

# 2. Upload via SFTP
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)
buf.seek(0)
sftp = client.open_sftp()
sftp.putfo(buf, '/tmp/project.tar.gz')
sftp.close()

# 3. Extract on remote
stdin, stdout, stderr = client.exec_command(
    'cd /home/administrator/project && tar xzf /tmp/project.tar.gz && echo DONE'
)

# 4. Rebuild Docker
stdin, stdout, stderr = client.exec_command(
    'cd /home/administrator/project && docker compose up -d --build 2>&1 | tail -5',
    timeout=300
)

# 5. Restart nginx (if config changed)
client.exec_command('cd /home/administrator/project && docker compose restart nginx')
time.sleep(2)

# 6. Verify
stdin, stdout, stderr = client.exec_command(
    'curl -s localhost:80/api/v1/dashboard | python3 -c "import sys,json; print(json.load(sys.stdin)[chr(109)+chr(101)+chr(116)+chr(114)+chr(105)+chr(99)+chr(115)])"'
)
print(stdout.read().decode().strip())
client.close()
```

## Important Notes
- Use `putfo()` with BytesIO for SFTP (avoids Windows path escaping)
- Docker build timeout: set to 300s for frontend (npm install + next build)
- Always `docker compose restart nginx` after config changes
- Always `time.sleep(2)` after container operations before health checks
- For single file uploads: `sftp.putfo(open(local, 'rb'), remote_path)`
