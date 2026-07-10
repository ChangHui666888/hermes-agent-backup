# Windows Wiki Setup: Hermes + Obsidian + Git + GitHub

Complete transcript of a verified setup session on Windows 10 (git-bash).

**Environment:** Windows 10, git-bash (Hermes terminal backend), Hermes profile `outside-deepdeek`.

## Path Resolution Quirk

On Windows under git-bash, Hermes overrides `$HOME` to the profile's home:
`C:/Users/<user>/AppData/Local/hermes/profiles/<profile-name>/home/`

So `~/wiki` → `.../profiles/outside-deepdeek/home/wiki/`, NOT `C:/Users/<user>/wiki/`.

**Fix:** Always set `WIKI_PATH` to an absolute Windows path in `.env`:
```
WIKI_PATH=C:/Users/<user>/wiki
OBSIDIAN_VAULT_PATH=C:/Users/<user>/wiki
```

Then use the absolute path consistently in both tools (`read_file`, `write_file`)
and terminal commands (`cd /c/Users/<user>/wiki`).

## Directory Structure

```
wiki/
├── SCHEMA.md              # Conventions, tag taxonomy, frontmatter rules
├── index.md               # Content catalog (sectioned by type)
├── log.md                 # Chronological action log
├── .gitattributes         # * text=auto
├── .gitignore             # OS files, Obsidian cache
├── .obsidian/
│   └── app.json           # attachmentFolderPath: raw/assets
├── raw/{articles,papers,transcripts,assets}/
├── entities/
├── concepts/
├── comparisons/
├── queries/
└── _archive/
```

## Git + GitHub Setup (behind GFW)

### 1. Git identity
```bash
git config --global user.name "YourName"
git config --global user.email "your@email.com"
```

### 2. Proxy (only if GitHub is inaccessible)
```bash
git config --global http.https://github.com.proxy socks5h://127.0.0.1:10808
```

### 3. Credential store for private repos
```bash
git credential approve <<- EOF
protocol=https
host=github.com
username=<your-github-username>
password=<your-personal-access-token>

EOF
```

### 4. Remote + push
```bash
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin master
```

## Convenience Scripts

**`~/wiki-push.cmd`** for CMD/PowerShell:
```batch
@echo off
cd /d C:\Users\<user>\wiki
git push %*
```

**`~/wiki-push.sh`** for git-bash:
```bash
#!/bin/bash
cd /c/Users/<user>/wiki
git push "$@"
```

## Verification

```bash
cd /c/Users/<user>/wiki
git log --oneline --graph --all
git branch -vv
git ls-remote --heads origin
```

All three should show consistent commit hashes.
