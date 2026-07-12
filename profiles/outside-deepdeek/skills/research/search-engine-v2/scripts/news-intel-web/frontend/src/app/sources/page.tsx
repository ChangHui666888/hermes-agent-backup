// app/sources/page.tsx — Source Registry
"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import type { SourceEntity } from "@/lib/types";
import Badge from "@/components/common/Badge";

function typeBadgeVariant(type: string): "blue" | "amber" | "muted" | "success" {
  const map: Record<string, "blue" | "amber" | "muted" | "success"> = {
    GOVERNMENT: "amber",
    MEDIA: "blue",
    RESEARCH: "success",
    SOCIAL: "muted",
  };
  return map[type] || "muted";
}

export default function SourcesPage() {
  const [sources, setSources] = useState<SourceEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchAPI<{ items: SourceEntity[] }>("/sources")
      .then((d) => setSources(d.items || []))
      .catch(() => setError("Failed to load sources"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4 max-w-[1200px] mx-auto">
      <h1 className="text-2xl font-bold text-foreground">Source Registry</h1>
      <p className="text-sm text-muted-foreground">
        Authority rating and event coverage per information source.
      </p>

      {loading && (
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-32 bg-card border border-border rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {error && <p className="text-muted-foreground">{error}</p>}

      {!loading && !error && (
        <div className="grid grid-cols-3 gap-3">
          {sources.map((src) => (
            <div
              key={src.source_id}
              className="bg-card border border-border rounded-xl p-4 hover:-translate-y-0.5 hover:shadow-lg transition-all"
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h3 className="text-sm font-semibold text-foreground">{src.name}</h3>
                  <Badge variant={typeBadgeVariant(src.type)}>{src.type}</Badge>
                </div>
              </div>

              {/* Authority gauge */}
              <div className="space-y-2 mt-3">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-muted-foreground uppercase tracking-wider">Authority</span>
                  <span className="font-mono text-foreground font-bold">{src.authority}</span>
                </div>
                <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                  <div
                    className="h-full bg-accent-blue rounded-full transition-all"
                    style={{ width: `${(src.authority / 20) * 100}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-muted-foreground uppercase tracking-wider">Events</span>
                  <span className="font-mono text-foreground">{src.event_count}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {!loading && !error && sources.length === 0 && (
        <p className="text-sm text-muted-foreground">No sources registered.</p>
      )}
    </div>
  );
}
