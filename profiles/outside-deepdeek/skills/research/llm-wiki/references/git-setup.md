# Git Setup for LLM Wiki

## Windows git-bash HOME Quirk

When Hermes terminal runs on Windows via git-bash, `$HOME` is overridden to
the profile's home directory (`~/.hermes/profiles/<name>/home/`), NOT the
user's actual home (`C:/Users/<you>/`). This means:

- `~/wiki` resolves to `<profile>/home/wiki` in the terminal, but
- The user's intended wiki path is usually `C:/Users/<you>/wiki`
- `read_file`/`write_file` tools use the user's actual home resolution

**Always use absolute paths** (`C:/Users/<you>/wiki` or `/c/Users/<you>/wiki`)
when mixing terminal commands and file tools, never `~/wiki`.

## Authentication

### Git Credential (All Platforms)
```bash
git credential approve <<- EOF
protocol=https
host=github.com
username=YOUR_USERNAME
password=YOUR_TOKEN
EOF
```

Never embed tokens in remote URLs (`https://user:token@github.com/...`),
as they'll be stored in plaintext in `.git/config`.

### Windows (git-bash) Credential Manager
The `manager-core` helper may timeout. If it does, use `store` instead:
```bash
git config --global credential.helper store
```
Then push once — credentials saved to `~/.git-credentials`.

### macOS Keychain
```bash
git config --global credential.helper osxkeychain
```

### Linux (libsecret)
```bash
sudo apt install libsecret-1-0 libsecret-1-dev
git config --global credential.helper /usr/share/doc/git/contrib/credential/libsecret/git-credential-libsecret
```

## Proxy Configuration

For users behind firewalls (e.g., mainland China), configure git to use a
SOCKS5/HTTP proxy **only for github.com**, never globally:

```bash
git config --global http.https://github.com.proxy socks5h://127.0.0.1:10808
```

This scoped config means:
- `git push` to github.com → goes through proxy
- `git clone` of internal repos → direct connection (no proxy interference)
- All other git operations (local, company git) → unaffected

Verify the proxy config:
```bash
git config --global --list | grep proxy
```
Expected: `http.https://github.com.proxy=socks5h://127.0.0.1:10808`

## Troubleshooting

### "Recv failure: Connection was reset" on push
GitHub is blocked by your network. Configure proxy as above.

### "fatal: not a git repository"
You're running `git` commands from outside the wiki directory.
```bash
cd /c/Users/<you>/wiki && git status
```

### "Author identity unknown"
```bash
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
```

### "dialog already exited" / credential helper hangs on Windows
The `manager-core` helper can hang in git-bash. Switch to `store`:
```bash
git config --global credential.helper store
```
