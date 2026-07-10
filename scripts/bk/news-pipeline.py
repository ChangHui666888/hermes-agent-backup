import os, sys

os.environ["PYTHONUNBUFFERED"] = "1"
os.environ["NEWS_API_BASE"] = os.environ.get("NEWS_API_BASE", "http://100.107.117.23:8001")

SCRIPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
    "..", "profiles", "outside-deepdeek", "skills", "research",
    "search-engine-v2", "scripts")
if not os.path.isdir(SCRIPT_DIR):
    # Fallback: absolute path
    SCRIPT_DIR = r"C:\Users\ChangHui\AppData\Local\hermes\profiles\outside-deepdeek\skills\research\search-engine-v2\scripts"

sys.path.insert(0, SCRIPT_DIR)
print(f"[pipeline] 开始...", flush=True)

from news_intel.pipeline import run_pipeline
run_pipeline(hours=1, limit=200)
