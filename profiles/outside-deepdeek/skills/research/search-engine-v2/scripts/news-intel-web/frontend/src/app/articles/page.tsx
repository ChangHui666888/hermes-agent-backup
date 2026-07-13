// app/articles/page.tsx — Article List (merged old Home.vue)
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Badge, { stageBadgeVariant } from "@/components/common/Badge";

interface Article {
  id: number; title: string; summary_cn?: string;
  source_name?: string; published_at?: string;
  category?: string; tier?: string; score_total?: number;
  tags?: string[];
}

export default function ArticlesPage() {
  const [hot, setHot] = useState<Article[]>([]);
  const [latest, setLatest] = useState<Article[]>([]);
  const [categories, setCategories] = useState<{name:string;count:number}[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/news/hot?limit=6").then(r => r.json()),
      fetch("/news/latest?limit=12").then(r => r.json()),
      fetch("/categories").then(r => r.json()),
    ]).then(([h, l, c]) => {
      setHot(h.items || []);
      setLatest(l.items || []);
      setCategories(Array.isArray(c) ? c : []);
    }).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="space-y-4">{Array(5).fill(0).map((_,i) => <div key={i} className="h-24 bg-card border border-border rounded-xl animate-pulse" />)}</div>;

  return (
    <div className="max-w-[1000px] mx-auto space-y-6">
      {/* Category tags */}
      {categories.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {categories.slice(0, 12).map(c => (
            <Link key={c.name} href={`/articles/category/${c.name}`}
              className="px-3 py-1 bg-secondary border border-border rounded-full text-xs text-muted-foreground hover:text-foreground hover:border-accent-blue transition-colors">
              {c.name} ({c.count})
            </Link>
          ))}
        </div>
      )}

      {/* Hot */}
      <section>
        <h2 className="text-sm font-semibold text-foreground mb-3">🔥 Hot</h2>
        <div className="grid grid-cols-2 gap-3">
          {hot.map(a => <ArticleCard key={a.id} article={a} />)}
        </div>
      </section>

      {/* Latest */}
      <section>
        <h2 className="text-sm font-semibold text-foreground mb-3">🕐 Latest</h2>
        <div className="grid grid-cols-2 gap-3">
          {latest.map(a => <ArticleCard key={a.id} article={a} />)}
        </div>
      </section>
    </div>
  );
}

function ArticleCard({ article }: { article: Article }) {
  return (
    <Link href={`/articles/${article.id}`}
      className="block bg-card border border-border rounded-xl p-4 hover:-translate-y-0.5 hover:shadow-lg transition-all">
      <h3 className="text-sm font-medium text-foreground line-clamp-2 leading-snug">{article.title}</h3>
      <div className="flex items-center gap-2 mt-2 text-[11px] text-muted-foreground">
        {article.source_name && <span>{article.source_name}</span>}
        {article.published_at && <span>· {article.published_at.slice(0,10)}</span>}
        {article.tier && <Badge variant={article.tier === "A" ? "critical" : article.tier === "B" ? "amber" : "muted"}>T{article.tier}</Badge>}
        {article.category && <Badge variant="blue">{article.category}</Badge>}
      </div>
      {article.summary_cn && <p className="text-xs text-muted-foreground mt-1.5 line-clamp-2">{article.summary_cn}</p>}
    </Link>
  );
}
