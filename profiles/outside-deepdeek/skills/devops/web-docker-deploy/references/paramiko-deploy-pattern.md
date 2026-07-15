# Cloud Docker Deploy — Paramiko Upload Pattern

## Single File Upload
```python
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect('100.107.117.23', username='administrator', password='root123root!@', timeout=30)

sftp = c.open_sftp()
with open('LOCAL_FILE', 'rb') as f:
    sftp.putfo(f, '/home/administrator/news-platform-v8/REMOTE_PATH')
sftp.close()
```

## Directory Upload (tar)
```python
import tarfile, io
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode='w:gz') as tar:
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in ('__pycache__', 'node_modules', '.next')]
        for f in files:
            if f.endswith('.pyc'): continue
            tar.add(os.path.join(root, f), os.path.relpath(os.path.join(root, f), SRC))
buf.seek(0)
sftp.putfo(buf, '/tmp/upload.tar.gz')
c.exec_command('cd /home/administrator/news-platform-v8 && tar xzf /tmp/upload.tar.gz')
```

## Rebuild + Restart
```python
# Rebuild specific service
c.exec_command('cd /home/administrator/news-platform-v8 && docker compose up -d --build frontend 2>&1', timeout=300)

# Restart nginx (clears stale upstream cache)
c.exec_command('cd /home/administrator/news-platform-v8 && docker compose restart nginx')
```

## Verify After Deploy
```python
stdin, stdout, stderr = c.exec_command('curl -s localhost:80/api/v1/dashboard | python3 -c "..."')
print(stdout.read().decode())
```

## Common Pitfalls
- `--no-cache` build can crash 3.9GB server → avoid
- After frontend rebuild, MUST restart nginx or get 502
- Large binary files (.rar, .zip) cause SFTP timeout → tar without them
- Python inline strings with quotes inside exec_command need chr() encoding
- `putfo` needs directory to exist on remote; `mkdir -p` first
