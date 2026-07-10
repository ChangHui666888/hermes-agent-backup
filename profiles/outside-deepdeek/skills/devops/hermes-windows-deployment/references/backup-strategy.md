# Hermes 备份策略

## Git 备份（每日）

```bash
# 脚本: ~/.hermes/scripts/git-backup.sh
cd ~/AppData/Local/hermes
git add -A
git commit -m "auto-backup: $(date +%Y-%m-%d)"
git push origin master
```

## 全量备份到 F 盘（每 3 天）

```bash
# 脚本: ~/.hermes/scripts/full-backup.sh
rsync -av --exclude='node_modules/' \
          --exclude='.git/' \
          "$HOME/AppData/Local/hermes/" "F:/hermes-backup/hermes_$(date +%Y-%m-%d)/"
# 自动删除 7 天前的旧备份
```

## 一键恢复

双击 `C:\Users\<user>\AppData\Local\hermes\scripts\restore.bat`

自动：停止进程 → 备份当前版本 → 从 F 盘恢复 → 提示重启。
