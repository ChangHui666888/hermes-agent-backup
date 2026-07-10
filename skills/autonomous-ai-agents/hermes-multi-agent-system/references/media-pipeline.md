# Chinese-Friendly Media Production Pipeline (zero AI-image cost)

One source → three product lines: graphic (图文), podcast (播客), short-video (短视频). All Chinese-first, all open-source/free tools. Every product passes a legal sandbox before publish; publishing stays human-reviewed.

## Content flow
material (RSS topic bridge from an archive DB, or local files)
→ `content_distiller.py` (DeepSeek rewrites硬核素材 into TL;DR + points + 爆款 article, JSON output via `response_format:{type:json_object}`)
→ `legal_sandbox.py` (blacklist + regex block of 诱导性投资建议: 明示买入点位/承诺收益率/目标价/稳赚; force-append 免责声明; verdict PASS/REJECT, exit 3 on reject)
→ product lines.

## Line 1 — Graphic (`infographic_render.py`)
**Zero AI-image cost:** render an HTML/CSS template and screenshot it with **playwright** (`chromium.launch()`, `set_content`, `page.screenshot`, `device_scale_factor=2`). Chinese renders perfectly with a font stack `'Microsoft YaHei','PingFang SC','Noto Sans CJK SC'`. Ship a few templates (cards流 / cover) and aspect presets (portrait 1080×1440, story 1080×1920, square, landscape). This beats waiting on an image-gen API/key and is free.

## Line 2 — Podcast (`podcast_gen.py`)
`edge-tts` (free Microsoft Chinese voices) for narration, then ffmpeg mixes BGM under the voice (`aloop`+`volume`+`afade`, `adelay` for intro, `amix`). Voices used: 温暖女声=zh-CN-XiaoxiaoNeural, 专业男声=zh-CN-YunyangNeural, 阳光男声=zh-CN-YunxiNeural, 活泼女声=zh-CN-XiaoyiNeural, 激情男声=zh-CN-YunjianNeural.

## Line 3 — Short video (`shortvideo_gen.py`)
Narration + subtitles from `edge-tts --write-media … --write-subtitles out.srt`, Ken Burns zoom on the infographic PNGs (ffmpeg `zoompan`), concat clips, then `subtitles=…:force_style='FontName=Microsoft YaHei,…'` burns Chinese subs; mux AAC audio → 1080×1920 H264 mp4 (抖音/视频号 format). ~1-2 min per clip.

## TTS engine abstraction (`tts_engine.py`)
Wrap the backend so it's swappable: `TTS_BACKEND` env (edge now; cosyvoice/index-tts reserved for local upgrade — 8G GPU can run CosyVoice for near-human 中文). `synthesize()` and `synthesize_with_subtitles()`.

## edge-tts reliability gotcha (IMPORTANT — this is a retry pattern, not a broken tool)
edge-tts hits `speech.platform.bing.com`; it **intermittently fails** with `ClientConnectorError … 指定的网络名不再可用`, then works again seconds later. This is transient service flakiness, NOT a dead tool. Fix = **exponential backoff retry** (`time.sleep(5*attempt)`, 3 tries) built into the TTS calls, and validate `os.path.getsize(out) > 0`. Do not conclude edge-tts is unusable — retry.

## Deps
`pip install edge-tts playwright psutil paramiko pyyaml` into the SYSTEM python (not Hermes venv). ffmpeg + a Chrome/Edge for playwright already present on most hosts; `playwright install chromium` if browser missing.

## Publish
Graphic → WeChat MP draft box (`/cgi-bin/draft/add`) — needs egress IP in the公众号 IP whitelist (errcode 40164 otherwise; return exit 4 with a clear message, don't crash). Podcast/video land locally for human review / manual post. Humanized jitter scheduler (±30min random + per-action random pauses) to dodge platform matrix风控.
