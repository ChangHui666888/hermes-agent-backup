// app/search/page.tsx — Global search
"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { fetchAPI } from "@/lib/api";
import type { EventListItem } from "@/lib/types";
import Badge, { stageBadgeVariant } from "@/components/common/Badge";

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<EventListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  const search = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }
    setLoading(true);
    setSearched(true);
    try {
      const data = await fetchAPI<{ query: string; events: EventListItem[] }>(
        `/search?q=${encodeURIComponent(q)}`
      );
      setResults(data.events || []);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => search(query), 300);
    return () => clearTimeout(t);
  }, [query, search]);

  return (
    <div className="max-w-[720px] mx-auto space-y-6">
      {/* Search input */}
      <div>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search events by title, summary, or keywords..."
          autoFocus
          className="w-full h-12 bg-card border border-border rounded-lg px-4 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue transition-colors"
        />
      </div>

      {/* Results */}
      {loading && (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-card border border-border rounded-lg animate-pulse" />
          ))}
        </div>
      )}

      {searched && !loading && results.length === 0 && (
        <div className="text-center py-12">
          <p className="text-muted-foreground">
            No events found for &ldquo;{query}&rdquo;
          </p>
        </div>
      )}

      {results.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            {results.length} result{results.length !== 1 ? "s" : ""} for &ldquo;{query}&rdquo;
          </p>

          {results.map((ev) => (
            <Link
              key={ev.event_id}
              href={`/events/${ev.event_id}`}
              className="block bg-card border border-border rounded-lg p-4 hover:bg-accent/50 transition-colors"
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground leading-snug">
                    {ev.title}
                  </p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <Badge variant={stageBadgeVariant(ev.stage)}>{ev.stage}</Badge>
                    {ev.action_type && ev.action_type !== "OTHER" && (
                      <Badge variant="blue">{ev.action_type}</Badge>
                    )}
                    {ev.location_country && (
                      <span className="text-[10px] text-muted-foreground">{ev.location_country}</span>
                    )}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-sm font-mono font-bold text-foreground">
                    {Math.round(ev.confidence * 100)}%
                  </p>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    {ev.source_count} src
                  </p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
