---
name: html-zero-cost-infographics
description: "Generate Chinese infographics as PNG using HTML/CSS templates + Playwright screenshot. Zero AI image-gen cost, with multi-template layout switching."
version: 1.0.0
author: agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [infographic, chinese, html-to-image, playwright, zero-cost]
---

# HTML Zero-Cost Infographics

Generate clean Chinese-infographics as PNG files using HTML/CSS templates rendered headless by Playwright. No AI image generation API keys, no ComfyUI, no cost. Ideal for content pipelines where the alternative is spending on DALL-E, Midjourney, or local GPU inference.

## When to use

- You need illustrated infographics, cover images, or visual summaries in Chinese (or any CJK language).
- You have Playwright and a browser (Chrome/Edge) installed locally.
- The content is structured (title + key points + metadata) and fits in a card/cover layout.
- You want results under 5 seconds with zero API cost.

Do NOT use when you need photorealistic images, complex illustrations, or generative art — this produces clean diagram-style layouts only.

## Architecture

```
Structured data (JSON) → HTML template (inline CSS) → Playwright headless browser → PNG screenshot
```

Two built-in templates:

| Template | Best for | Style |
|---|---|---|
| `cover` | Article hero images, landing cards | Full-bleed gradient background, large title, subtitle, accent bar |
| `cards` | Listicles, key-point summaries, TL;DR visuals | White cards with numbered items, accent left border |

## Data Format

```json
{
  "title": "Cover or card title",
  "subtitle": "Subtitle or TL;DR line",
  "accent": "#2563eb",
  "tag": "Section label (cover only)",
  "footer": "Disclaimer or source line",
  "points": [
    {"h": "Point header", "t": "Point detail text"},
    {"h": "Another point", "t": "Detail for this point"}
  ]
}
```

For`cover`template only the `title` and `subtitle` fields are essential; `points` are ignored. For `cards`, `points` are the main content.

## Usage

```python
from playwright.sync_api import sync_playwright

TEMPLATES = {"cards": _cards_html, "cover": _cover_html}
ASPECTS = {"portrait": (1080, 1440), "square": (1080, 1080),
           "landscape": (1280, 720), "story": (1080, 1920)}

def render(data, out_path, template="cards", aspect="portrait"):
    w, h = ASPECTS.get(aspect, ASPECTS["portrait"])
    html = TEMPLATES.get(template, _cards_html)(data)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": w, "height": h},
                        device_scale_factor=2)
        pg.set_content(html, wait_until="networkidle")
        pg.screenshot(path=out_path, full_page=False)
        b.close()
```

## Chinese Font Stack

For Windows:

```css
font-family: 'Microsoft YaHei','PingFang SC','Noto Sans CJK SC',sans-serif;
```

For macOS: `'PingFang SC','Noto Sans CJK SC','Hiragino Sans GB',sans-serif;`

For Linux: `'Noto Sans CJK SC','WenQuanYi Micro Hei',sans-serif;`

Always provide a fallback with `sans-serif` to handle rare glyphs.

## Adding a New Template

Add a function returning a full HTML document string:

```python
def _my_template_html(d):
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    /* inline CSS */
    </style></head><body>
    <div class="title">{d.get("title","")}</div>
    </body></html>'''
```

Then register in the `TEMPLATES` dict:

```python
TEMPLATES["my-template"] = _my_template_html
```

All CSS must be inline (no external files) since Playwright renders a single string. Use `device_scale_factor=2` for retina-quality output.

## Pitfalls

1. **No external images in templates** — HTML is rendered as a single string. Image `src` needs absolute local paths or data URIs. If you want background images, pass them as data URIs or use `file://` paths.
2. **Content overflow in cards** — if a point header is very long ( > 30 chars), it may overflow the card visually. Pre-truncate before inserting into the data dict.
3. **Playwright must have a browser installed** — `playwright install chromium` if `pip install playwright` didn't auto-download one. Without it, the `with sync_playwright()` context will fail.
4. **Aspect ratio is strict** — `story` (1080×1920) is good for short vertical video slides/cover. `portrait` (1080×1440) is standard social media. Use `landscape` (1280×720) for blog header images.
5. **CRITICAL: Path escapes in subtitles filter** — when passing SRT paths to ffmpeg's `subtitles=` filter on Windows, use double backslashes or forward slashes. A single unescaped colon in the path will crash ffmpeg with a parse error.
