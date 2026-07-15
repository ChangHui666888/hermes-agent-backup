# Transition Page Pattern

## Layout

```
/articles/[id]
├── Source + Date + Tier Badge
├── 🤖 AI Summary (第三人称描述, 100-200 chars)
├── Entity Tags (companies, persons, countries)
├── [VIP] Expandable full content (toggle button)
└── → CTA: "Read Full Article on [Source]"
     rel="noopener noreferrer nofollow"
```

## Key Design Decisions

1. **AI Summary first** — users see a factual summary before deciding to leave
2. **Not raw content** — the summary is processed, not just RSS description
3. **External link with nofollow** — protects SEO while providing source credit
4. **VIP content gating** — full text only for logged-in VIP/Admin users
5. **Security attributes** — `noopener noreferrer` prevents tab-napping attacks

## Implementation

```tsx
// CTA button
<a href={article.url} target="_blank"
   rel="noopener noreferrer nofollow"
   className="bg-accent-amber text-black font-semibold">
  → Read Full Article on {article.source_name || "Source"}
</a>

// AI Summary section
<div className="bg-card border border-border rounded-xl p-5">
  <span className="text-sm">🤖</span>
  <span className="text-accent-amber">AI Summary</span>
  <p>{article.ai_description || article.summary_cn}</p>
</div>
```

## SEO Benefits

- Rich content (title + summary + tags) on your domain
- `nofollow` prevents PageRank leakage to source sites
- Internal page keeps users on your platform longer
- Transition page becomes indexable search result target
