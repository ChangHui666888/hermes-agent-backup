// app/articles/[id]/page.tsx — Article Transition Page
"use client";

import { useEffect, useState, use } from "react";
import { useAuth } from "@/lib/auth";
import Badge from "@/components/common/Badge";

interface ArticleDetail {
  id: number; title: string; url: string;
  summary_cn?: string; content_md?: string;
  source_name?: string; source_domain?: string; published_at?: string;
  category?: string; tier?: string; score_total?: number;
  tags?: string[]; entities?: Record<string,string[]>;
  analysis?: Record<string,unknown>; key_points?: string[];
  ai_description?: string;
}

export default function ArticleDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { token, isVip } = useAuth();
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [error, setError] = useState("");
  const [showFull, setShowFull] = useState(false);

  useEffect(() => {
    const headers: Record<string,string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    fetch(`/news/${id}`, { headers })
      .then(r => r.ok ? r.json() : Promise.reject("Not found"))
      .then(setArticle)
      .catch(() => setError("Article not found"));
  }, [id, token]);

  if (error) return <div className="text-muted-foreground text-center py-12">{error}</div>;
  if (!article) return <div className="max-w-[700px] mx-auto"><div className="h-40 bg-card border border-border rounded-xl animate-pulse" /><div className="h-32 bg-card border border-border rounded-xl animate-pulse mt-4" /></div>;

  const entities = article.entities || {};
  const allTags = [...(article.tags || []), ...Object.keys(entities).flatMap(k => entities[k] || [])].slice(0, 8);

  return (
    <div className="max-w-[700px] mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {article.source_name && <span>{article.source_name}</span>}
        {article.published_at && <span>· {article.published_at.slice(0,10)}</span>}
        {article.tier && <Badge variant={article.tier === "A" ? "critical" : "amber"}>Tier {article.tier}</Badge>}
      </div>

      {/* Title */}
      <h1 className="text-xl font-bold text-foreground leading-tight">{article.title}</h1>

      {/* AI Description or Summary */}
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-sm">🤖</span>
          <span className="text-[10px] uppercase tracking-wider text-accent-amber font-semibold">AI Summary</span>
        </div>
        <p className="text-sm text-foreground/90 leading-relaxed">
          {article.ai_description || article.summary_cn || "No summary available."}
        </p>
      </div>

      {/* Tags */}
      {allTags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {allTags.map((tag, i) => (
            <span key={i} className="text-[10px] bg-secondary border border-border px-2 py-0.5 rounded text-muted-foreground">{tag}</span>
          ))}
        </div>
      )}

      {/* VIP content */}
      {isVip && showFull && article.content_md ? (
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="text-sm text-foreground/80 leading-relaxed whitespace-pre-wrap">
            {article.content_md.slice(0, 3000)}
          </div>
        </div>
      ) : isVip && !showFull ? (
        <button onClick={() => setShowFull(true)}
          className="w-full py-3 bg-accent-blue/20 border border-accent-blue/30 rounded-xl text-sm text-accent-blue hover:bg-accent-blue/30 transition-colors">
          Show Full Content ({article.content_md ? Math.round(article.content_md.length/1000) : 0}K chars)
        </button>
      ) : null}

      {/* CTA Button */}
      <div className="bg-[#172554] border border-blue-900/50 rounded-xl p-5 text-center space-y-3">
        <p className="text-sm text-blue-200">
          This is an AI-generated summary. Read the full article on the original source.
        </p>
        <a
          href={article.url}
          target="_blank"
          rel="noopener noreferrer nofollow"
          className="inline-block px-8 py-3 bg-accent-amber text-black font-semibold rounded-lg hover:opacity-90 transition-opacity text-sm"
        >
          → Read Full Article on {article.source_name || "Source"}
        </a>
        <p className="text-[10px] text-blue-400/60">
          Opens in new tab · {article.source_domain || ""}
        </p>
      </div>

      {/* AI Analysis (VIP only) */}
      {article.analysis && isVip && (
        <div className="bg-[#172554] border border-blue-900/50 rounded-xl p-4">
          <h3 className="text-xs uppercase text-blue-300 font-semibold mb-2">AI Analysis</h3>
          <div className="text-sm text-blue-100 space-y-1">
            {article.analysis.event && <p><b>Event:</b> {String(article.analysis.event)}</p>}
            {article.analysis.impact && <p><b>Impact:</b> {String(article.analysis.impact)}</p>}
            {article.analysis.risk_level && <p><b>Risk:</b> {String(article.analysis.risk_level)}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
