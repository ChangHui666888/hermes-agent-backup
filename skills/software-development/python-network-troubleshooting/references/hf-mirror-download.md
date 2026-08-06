# HF 模型下载绕过 GFW：hf-mirror + 直连（2026-08 实测）

## 场景

国内网络环境安装 GLiNER / REBEL 等 IE 专用模型时：
- `huggingface.co` 直连超时（被墙）
- `hf-mirror.com` 可达（HTTP 200）

## 坑 1：走代理反而卡死

hf-mirror 的 `/resolve/main/<file>` 会 **302 重定向到 AWS CDN**（`us.aws.cdn.hf.co`）。
huggingface_hub 的 xet 下载客户端读取 **Windows 系统代理**（而非环境变量），把 AWS CDN 请求也绕道境外代理：

| 方式 | 速度 |
|------|------|
| 走代理 (HTTPS_PROXY=127.0.0.1:10808) 下载 hf-mirror | **663 B/s（卡死）** |
| unset 代理直连 | **9.7 MB/s** |

## 修复

```bash
# 持久化（用户级 + .env）
setx HF_ENDPOINT "https://hf-mirror.com"
setx NO_PROXY "hf-mirror.com,huggingface.co"

# 每次会话
export HF_ENDPOINT=https://hf-mirror.com
export NO_PROXY=hf-mirror.com,huggingface.co
unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy
```

## 坑 2：huggingface_hub 下载大文件仍可能卡

即使 NO_PROXY 设了，`snapshot_download()` 也可能 0 字节不动（xet 客户端路径问题）。
**大权重文件直接用 curl 直连下载**：

```bash
unset HTTPS_PROXY HTTP_PROXY https_proxy http_proxy
curl -sSL -o ~/models/GLiNER/gliner_small-v1/pytorch_model.bin \
  --connect-timeout 15 --max-time 600 \
  "https://hf-mirror.com/urchade/gliner_small-v1/resolve/main/pytorch_model.bin"
```

小文件（config/tokenizer/README）用 snapshot_download 能下，大文件 curl 补。

## 坑 3：gliner 等库只认 HF 缓存结构，不认本地路径

`GLiNER.from_pretrained('/path/to/local')` 会报 `HFValidationError`（Repo id 必须是 `org/repo` 格式）。
手动下载的文件需部署到标准 HF 缓存：

```
~/.cache/huggingface/hub/models--urchade--gliner_small-v1/
├── refs/main                                  # 内容 = revision hash
└── snapshots/0f0f4e7d3f10e48844110162d6b5c6072ddd5a4e/
    ├── gliner_config.json
    ├── pytorch_model.bin
    └── README.md
```

revision hash 来源：
1. 之前 snapshot_download 报错信息里的 `IncompleteSnapshotError ... commit 0f0f...`
2. 或 `~/.cache/huggingface/trees/<hash>.json` 文件名

然后 `GLiNER.from_pretrained('urchade/gliner_small-v1')` 即可离线加载。

## 坑 4：模型仓库文件名差异

| 仓库 | 实际文件名 | 没有的文件 |
|------|-----------|-----------|
| `urchade/gliner_small-v1` | `gliner_config.json` + `pytorch_model.bin` | `config.json`（404） |
| `Babelscape/rebel-large` | `model.safetensors` + tokenizer 全套 | — |

查真实文件列表：
```bash
curl -sSL "https://hf-mirror.com/api/models/<org>/<repo>" | jq '.siblings[].rfilename'
```

## 安装与验证

```bash
# 清华源装依赖（Python 3.11 系统环境，勿装进 Hermes venv）
python -m pip install torch --index-url https://pypi.tuna.tsinghua.edu.cn/simple
python -m pip install transformers gliner accelerate --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

验证（2026-08 实测，CPU）：
- torch 2.13.0+cpu, transformers 5.13.1, gliner 0.2.28, accelerate 1.14.0
- GLiNER small-v1：加载 22.3s，`Apple(1.00) Tesla(0.99) Federal Reserve(0.95)` 全部正确
- REBEL large：加载 11.6s（1.56GB safetensors）

## REBEL 三元组输出解析

REBEL 输出格式为 `<s> head <triplet> relation <sep> tail </s>`，多个三元组以 `<s>...</s>` 重复：

```python
import re
decoded = tok.batch_decode(gen, skip_special_tokens=False)[0]
for t in re.findall(r'<s>(.*?)</s>', decoded):
    h, _, rest = t.partition('<triplet>')
    r, _, o = rest.partition('<sep>')
    print(f'({h.strip()}) -[{r.strip()}]-> ({o.strip()})')
```

（注：若模型输出带 `<mask>` 或特殊 token 需按实际 decoded 文本调整。）
