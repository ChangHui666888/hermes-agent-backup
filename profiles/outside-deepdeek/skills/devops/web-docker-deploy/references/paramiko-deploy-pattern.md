# Paramiko SCP Deploy Pattern

Use this Python snippet to tar a project directory and upload to cloud via SSH.

```python
import paramiko, tarfile, io, os

HOST = "100.107.117.23"
USER = "administrator"
PASS = "your-password"
SRC = os.path.expanduser("~/workspace/my-project")

# 1. Create tar (exclude heavy dirs)
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w:gz") as tar:
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", ".git", "__pycache__")]
        for f in files:
            if f.endswith(".pyc"):
                continue
            full = os.path.join(root, f)
            tar.add(full, os.path.relpath(full, SRC))

# 2. Connect
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)

# 3. Upload
buf.seek(0)
sftp = client.open_sftp()
sftp.putfo(buf, "/tmp/project.tar.gz")
sftp.close()

# 4. Extract
stdin, stdout, stderr = client.exec_command(
    "rm -rf /home/administrator/project && "
    "mkdir -p /home/administrator/project && "
    "tar xzf /tmp/project.tar.gz -C /home/administrator/project"
)

# 5. Build and start
stdin, stdout, stderr = client.exec_command(
    "cd /home/administrator/project && docker compose up -d --build",
    timeout=300
)

client.close()
```

## Key points

- Use `buf.seek(0)` before `putfo()` — the tar buffer position must be reset
- Use `putfo()` not `put()` to avoid Windows path escaping issues
- `tarfile.open(fileobj=buf, mode="w:gz")` for gzip compression
- `os.walk()` with `dirs[:]` mutation to skip directories in place
- `timeout=300` for `docker compose build` which takes minutes on small VMs
- NEVER use `--no-cache` on VMs with <4GB RAM — incremental builds are fine
