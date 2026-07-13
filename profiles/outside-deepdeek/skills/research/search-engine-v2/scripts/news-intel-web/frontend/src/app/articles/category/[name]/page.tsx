// app/articles/category/[name]/page.tsx
"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";

interface Article { id: number; title: string; source_name?: string; tier?: string; category?: string; summary_cn?: string; }

export default function CategoryPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = use(params);
  const [items, setItems] = useState<Article[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/news?category=${encodeURIComponent(name)}&page_size=50`)
      .then(r => r.json()).then(d => setItems(d.items || []))
      .finally(() => setLoading(false));
  }, [name]);

  return (
    <div className="max-w-[800px] mx-auto space-y-4">
      <h1 className="text-xl font-bold text-foreground">📂 {name}</h1>
      {loading ? <div className="space-y-3">{Array(3).fill(0).map((_,i) => <div key={i} className="h-24 bg-card border border-border rounded-xl animate-pulse" />)}</div>
      : items.length === 0 ? <p className="text-muted-foreground">No articles</p>
      : items.map(a => (
        <Link key={a.id} href={`/articles/${a.id}`}
          className="block bg-card border border-border rounded-xl p-4 hover:-translate-y-0.5 transition-all">
          <h3 className="text-sm font-medium text-foreground line-clamp-2">{a.title}</h3>
          <div className="flex items-center gap-2 mt-1.5 text-[11px] text-muted-foreground">
            {a.source_name && <span>{a.source_name}</span>}
            {a.tier && <span className="text-accent-blue">T{a.tier}</span>}
          </div>
        </Link>
      ))}
    </div>
  );
}
