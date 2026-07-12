#!/usr/bin/env python3
"""sync-db-to-cloud.py — Sync event_registry SQLite to cloud Docker.

Runs after pipeline aggregation. Replaces the cloud DB snapshot
and restarts the backend container to pick up changes.

Usage:
  python sync-db-to-cloud.py
  python sync-db-to-cloud.py --no-restart  (upload only, no restart)
"""

import paramiko
import os
import sys
import time

# Config
HOST = "100.107.117.23"
USER = "administrator"
PASS = "root123root!@"
LOCAL_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "news_intel", "news_intel.db",
)
REMOTE_DIR = "/home/administrator/news-intel-web/data"
REMOTE_COMPOSE = "/home/administrator/news-intel-web"


def main():
    no_restart = "--no-restart" in sys.argv

    if not os.path.exists(LOCAL_DB):
        print(f"[sync] DB not found: {LOCAL_DB}")
        sys.exit(1)

    local_size = os.path.getsize(LOCAL_DB)
    local_events = _count_events(LOCAL_DB)

    print(f"[sync] Local DB: {local_size/1024:.0f} KB, {local_events} events")

    # Connect
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, password=PASS, timeout=15)
    except Exception as e:
        print(f"[sync] SSH failed: {e}")
        sys.exit(1)

    # Upload
    print(f"[sync] Uploading to {HOST}...")
    sftp = client.open_sftp()
    sftp.put(LOCAL_DB, f"{REMOTE_DIR}/news_intel.db")
    sftp.close()
    print(f"[sync] Uploaded {local_size/1024:.0f} KB")

    # Verify
    stdin, stdout, stderr = client.exec_command(f"ls -la {REMOTE_DIR}/news_intel.db | awk '{{print $5}}'")
    remote_size = int(stdout.read().decode().strip())
    if remote_size == local_size:
        print(f"[sync] Size match ({remote_size} bytes)")
    else:
        print(f"[sync] WARNING: size mismatch local={local_size} remote={remote_size}")

    # Restart backend
    if not no_restart:
        print("[sync] Restarting backend container...")
        stdin, stdout, stderr = client.exec_command(
            f"cd {REMOTE_COMPOSE} && docker compose restart backend 2>&1"
        )
        out = stdout.read().decode().strip()
        print(f"[sync] {out}")

    # Health check
    time.sleep(2)
    stdin, stdout, stderr = client.exec_command(
        "curl -s localhost:80/api/v1/dashboard | python3 -c "
        "\"import sys,json; d=json.load(sys.stdin); "
        "print(d['metrics']['active_events'])\""
    )
    cloud_events = stdout.read().decode().strip()
    print(f"[sync] Cloud now serving {cloud_events} events")

    if int(cloud_events) != local_events and not no_restart:
        print(f"[sync] WARNING: cloud events ({cloud_events}) != local ({local_events})")

    client.close()


def _count_events(db_path: str) -> int:
    import sqlite3
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM event_registry").fetchone()[0]
    conn.close()
    return n


if __name__ == "__main__":
    main()
