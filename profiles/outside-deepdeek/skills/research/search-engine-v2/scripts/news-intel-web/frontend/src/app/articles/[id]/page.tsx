// app/articles/[id]/page.tsx — Article Detail (VIP content masking)
"use client";

import { useEffect, useState, use } from "react";
import { useAuth } from "@/lib/auth";
import Badge from "@/components/common/Badge";

interface ArticleDetail {
  id: number; title: string; summary_cn?: string; content_md?: string;
  source_name?: string; source_domain?: string; published_at?: string;
  category?: string; tier?: string; score_total?: number;
  tags?: string[]; entities?: Record<string,string[]>;
  analysis?: Record<string,unknown>; key_points?: string[];
  extraction_method?: string;
}

export default function ArticleDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { token, isVip } = useAuth();
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const headers: Record<string,string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    fetch(`/news/${id}`, { headers })
      .then(r => r.ok ? r.json() : Promise.reject("Not found"))
      .then(setArticle)
      .catch(() => setError("Article not found"));
  }, [id, token]);

  if (error) return <div className="text-muted-foreground text-center py-12">{error}</div>;
  if (!article) return <div className="h-64 bg-card border border-border rounded-xl animate-pulse" />;

  return (
    <div className="max-w-[800px] mx-auto space-y-4">
      <h1 className="text-xl font-bold text-foreground leading-tight">{article.title}</h1>
      <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
        {article.source_name && <span>{article.source_name}</span>}
        {article.published_at && <span>· {article.published_at.slice(0,10)}</span>}
        {article.tier && <Badge variant={article.tier === "A" ? "critical" : "amber"}>T{article.tier}</Badge>}
        {article.category && <Badge variant="blue">{article.category}</Badge>}
      </div>

      {/* VIP content */}
      {article.content_md ? (
        <div className="prose prose-invert max-w-none text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
          {article.content_md}
        </div>
      ) : !isVip ? (
        <div className="bg-[#172554] border border-blue-900/50 rounded-xl p-6 text-center">
          <p className="text-blue-200">🔒 VIP content — <a href="/login" className="text-accent-amber underline">login</a> to read full article</p>
        </div>
      ) : (
        <p className="text-muted-foreground text-sm">{article.summary_cn || "No content available"}</p>
      )}

      {/* AI Analysis */}
      {article.analysis && isVip && (
        <div className="bg-[#172554] border border-blue-900/50 rounded-xl p-4">
          <h3 className="text-xs uppercase text-blue-300 font-semibold mb-2">📊 AI Analysis</h3>
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
