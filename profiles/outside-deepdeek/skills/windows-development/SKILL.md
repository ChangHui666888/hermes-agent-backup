---
name: windows-development
description: Windows-specific development tooling quirks and fixes for Hermes Agent on Windows/git-bash
version: 1.0.0
---

# Windows Development (Hermes Agent on Windows/git-bash)

This skill covers Windows-specific tooling quirks when running Hermes Agent on Windows 10+ with git-bash (MSYS2) terminal.

## Write_file Path Resolution

**Problem**: On Windows, `write_file(path="/c/Users/name/file.py", ...)` resolves to `C:\c\Users\name\file.py` instead of `C:\Users\name\file.py`. The tool prepends the workspace root when given POSIX-style paths.

**Fix**: Always use Windows absolute paths with forward slashes:
- ✅ `write_file(path="C:/Users/ChangHui/file.py", ...)`
- ❌ `write_file(path="/c/Users/ChangHui/file.py", ...)`
- ❌ `write_file(path="C:\\Users\\ChangHui\\file.py", ...)`

**Detection**: When a file isn't found after writing, check `resolved_path` in write_file's output. If it shows `C:\c\Users\...`, the path was wrong. Also verify with `ls -la "C:/Users/.../file.py"` from terminal (use absolute Windows path in quotes).

## Python Venv Mismatch

**Problem**: On Windows/git-bash, `which python` resolves to Hermes venv (`.../hermes-agent/venv/Scripts/python`), but `pip` resolves to system Python (`C:/Users/.../Python311/Scripts/pip`). So `pip install` installs to system site-packages, NOT the Hermes venv.

**Fix**: Use `uv pip install <package>` which correctly targets the Hermes venv. Always verify imports with `python -c "import <pkg>"` after installation, not just `pip show`.

## Shell: git-bash (MSYS2), NOT PowerShell

**Problem**: The `terminal` tool on Windows runs commands through git-bash (MSYS2), NOT PowerShell or cmd.exe.

**Fix**: Use POSIX shell syntax:
- ✅ `ls`, `$HOME`, `&&`, `|`, single-quoted strings
- ❌ PowerShell builtins like `Get-ChildItem`, `$env:FOO`, `Select-String`
- MSYS-style paths (`/c/Users/...`) work alongside native paths (`C:\Users\...`)

## Proxy Environment Variables

Check with `reg query HKCU\Environment` to see Windows-level proxy vars. Do NOT modify registry proxy settings manually — proxy software manages these.

## Key Ports

| Port | Service |
|------|---------|
| 8648 | Hermes Studio Web UI |
| 8650 | Content Factory Dashboard |
| 8642 | Hermes API Server |
