// app/events/page.tsx — Event Explorer
"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, Suspense } from "react";
import Link from "next/link";
import type { EventListItem, EventListResponse } from "@/lib/types";
import { fetchAPI } from "@/lib/api";
import Badge, { stageBadgeVariant, confidenceBadgeVariant } from "@/components/common/Badge";

const PAGE_SIZE = 20;

function ExplorerContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [data, setData] = useState<EventListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const page = parseInt(searchParams.get("page") || "1");
  const eventType = searchParams.get("event_type") || "";
  const country = searchParams.get("country") || "";
  const stage = searchParams.get("stage") || "";

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("limit", String(PAGE_SIZE));
      if (eventType) params.set("event_type", eventType);
      if (country) params.set("location_country", country);
      if (stage) params.set("stage", stage);
      const res = await fetchAPI<EventListResponse>(`/events?${params}`);
      setData(res);
    } catch {
      setError("Failed to load events");
    } finally {
      setLoading(false);
    }
  }, [page, eventType, country, stage]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const setFilter = (key: string, value: string) => {
    const p = new URLSearchParams(searchParams.toString());
    if (value) p.set(key, value); else p.delete(key);
    p.set("page", "1");
    router.push(`/events?${p}`);
  };

  const totalPages = Math.ceil((data?.total || 0) / PAGE_SIZE);

  return (
    <div className="space-y-4 max-w-[1200px] mx-auto">
      <h1 className="text-2xl font-bold text-foreground">Event Explorer</h1>

      <div className="flex items-center gap-3 flex-wrap">
        <select value={eventType} onChange={(e) => setFilter("event_type", e.target.value)}
          className="bg-secondary border border-border rounded-md px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-accent-blue">
          <option value="">All Topics</option>
          {["Military","Diplomacy","Legal","Economic","Political","Technology","Leadership","Crisis"].map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={stage} onChange={(e) => setFilter("stage", e.target.value)}
          className="bg-secondary border border-border rounded-md px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-accent-blue">
          <option value="">All Stages</option>
          {["breaking","developing","active","stable","closed"].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <input type="text" placeholder="Filter by country..." value={country}
          onChange={(e) => setFilter("country", e.target.value)}
          className="bg-secondary border border-border rounded-md px-3 py-1.5 text-xs text-foreground w-40 placeholder:text-muted-foreground focus:outline-none focus:border-accent-blue" />
        {data && <span className="text-xs text-muted-foreground ml-auto">{data.total} events</span>}
      </div>

      {loading && (
        <div className="bg-card border border-border rounded-xl p-8">
          <div className="space-y-3 animate-pulse">
            {[1,2,3,4,5].map(i => <div key={i} className="h-16 bg-secondary rounded-lg" />)}
          </div>
        </div>
      )}

      {error && (
        <div className="bg-card border border-border rounded-xl p-8 text-center">
          <p className="text-muted-foreground">{error}</p>
          <button onClick={fetchEvents} className="mt-3 text-xs text-accent-blue hover:underline">Retry</button>
        </div>
      )}

      {data && !loading && (
        <>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="grid grid-cols-[1fr_120px_80px_80px_140px] bg-secondary border-b border-border px-4 py-3 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
              <span>Event</span><span>Stage</span><span>Confidence</span><span>Sources</span><span>Updated</span>
            </div>
            {data.items.length === 0 && (
              <div className="px-4 py-12 text-center text-sm text-muted-foreground">No events match filters.</div>
            )}
            {data.items.map(ev => (
              <Link key={ev.event_id} href={`/events/${ev.event_id}`}
                className="grid grid-cols-[1fr_120px_80px_80px_140px] px-4 py-3 border-b border-border last:border-b-0 hover:bg-accent transition-colors cursor-pointer items-center">
                <div className="min-w-0 pr-4">
                  <p className="text-sm font-medium text-foreground truncate">{ev.title}</p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {ev.subject_name && <span className="text-[10px] text-muted-foreground">{ev.subject_name}</span>}
                    {ev.action_type && ev.action_type !== "OTHER" && <Badge variant="blue">{ev.action_type}</Badge>}
                    {ev.object_name && <span className="text-[10px] text-muted-foreground">{ev.object_name}</span>}
                  </div>
                </div>
                <Badge variant={stageBadgeVariant(ev.stage)}>{ev.stage}</Badge>
                <span className="text-sm font-mono tabular-nums text-foreground">{Math.round(ev.confidence * 100)}%</span>
                <span className="text-sm text-muted-foreground">{ev.source_count}</span>
                <span className="text-xs text-muted-foreground font-mono truncate">{ev.last_updated || "—"}</span>
              </Link>
            ))}
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-1">
              <button disabled={page <= 1} onClick={() => setFilter("page", String(page - 1))}
                className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-30">← Prev</button>
              {Array.from({length: Math.min(totalPages, 10)}, (_, i) => {
                const p = i + 1;
                return <button key={p} onClick={() => setFilter("page", String(p))}
                  className={`w-8 h-8 rounded text-xs font-medium ${p === page ? "bg-accent-blue text-white" : "text-muted-foreground hover:bg-accent hover:text-foreground"}`}>{p}</button>;
              })}
              <button disabled={page >= totalPages} onClick={() => setFilter("page", String(page + 1))}
                className="px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-30">Next →</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function ExplorerPage() {
  return (
    <Suspense fallback={<div className="p-8 text-muted-foreground">Loading...</div>}>
      <ExplorerContent />
    </Suspense>
  );
}
