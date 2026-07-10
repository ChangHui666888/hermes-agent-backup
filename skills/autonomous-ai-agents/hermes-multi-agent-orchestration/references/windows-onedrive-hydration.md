# Windows OneDrive folder hydration (WinError 2 on mkdir/write)

## Symptom
On Windows, creating a subdir or file under a path like
`C:\Users\<user>\Documents\<Vault>` fails with:
`FileNotFoundError: [WinError 2] 系统找不到指定的文件` (The system cannot find
the file specified) — **even though** `os.path.exists()` and `os.listdir()` on
that same directory succeed, and the registry `Shell Folders\Personal` points
to the local path.

`cmd //c mkdir` fails the same way. `fsutil reparsepoint query` errors 123.

## Root cause
The `Documents` folder (and children) is a OneDrive "Known Folder" whose
contents are **dehydrated placeholders** (files-on-demand). The directory entry
exists for enumeration but the backing store isn't materialized, so the Win32
create call can't resolve the parent until OneDrive hydrates it.

## Fix (reliable)
Touch the directory to trigger hydration, then retry the create:
```python
import os, time
target_dir = r"C:\Users\<user>\Documents\<Vault>"
os.listdir(target_dir)          # forces hydration
for attempt in range(3):
    try:
        os.mkdir(os.path.join(target_dir, "sub")); break
    except FileNotFoundError:
        time.sleep(1)
```
After the first successful `listdir` + retry, subsequent `makedirs`/`write_file`
calls in that tree work normally. Prefer building the whole directory tree in a
single Python `os.makedirs` pass right after hydration rather than shelling out
`mkdir` per directory (MSYS bash also mangles paths with spaces).

## Not a durable constraint
This is environment state, not a broken tool. The fix is the hydration retry —
do NOT record "can't write to Documents" as a rule.
