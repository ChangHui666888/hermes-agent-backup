// components/event/EventHeader.tsx — v2: summary + significance first
"use client";

import type { EventDossier } from "@/lib/types";

function stageColor(stage: string): string {
  const map: Record<string, string> = {
    breaking: "bg-critical text-white",
    developing: "bg-high text-white",
    active: "bg-info text-white",
    stable: "bg-success text-black",
    closed: "bg-muted text-muted-foreground",
  };
  return map[stage] || "bg-muted text-muted-foreground";
}

export default function EventHeader({ event }: { event: EventDossier }) {
  const analysis = event.llm_analysis as Record<string, unknown> | null;
  const confidencePct = Math.round(event.confidence * 100);
  const isHigh = event.confidence >= 0.8;

  return (
    <div className="bg-card border border-border rounded-xl p-6 relative overflow-hidden">
      {/* Confidence top bar */}
      <div
        className={`absolute top-0 left-0 h-1 transition-all ${isHigh ? "bg-accent-amber" : "bg-accent-blue"}`}
        style={{ width: `${confidencePct}%` }}
      />

      {/* Row 1: Title + Confidence */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 space-y-2">
          <h1 className="text-xl font-bold text-foreground leading-tight">
            {event.title}
          </h1>
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`px-2.5 py-0.5 rounded text-xs font-medium ${stageColor(event.stage)}`}>
              {event.stage.toUpperCase()}
            </span>
            {isHigh && (
              <span className="px-2.5 py-0.5 rounded text-xs font-bold bg-critical/20 text-critical border border-critical/30">
                HIGH IMPACT
              </span>
            )}
            <span className="text-xs text-muted-foreground">{event.event_type}</span>
            <span className="text-xs text-muted-foreground">
              {event.article_count} articles · {event.source.source_count} sources
            </span>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Confidence</span>
          <span className={`text-2xl font-bold tabular-nums ${isHigh ? "text-accent-amber" : "text-accent-blue"}`}>
            {confidencePct}%
          </span>
        </div>
      </div>

      {/* Row 2: One-line summary — "what happened" */}
      {event.summary && (
        <p className="mt-4 text-sm text-muted-foreground leading-relaxed border-t border-border pt-4">
          {event.summary}
        </p>
      )}

      {/* Row 3: AI significance — "why it matters" */}
      {analysis?.significance && (
        <div className="mt-3 flex items-start gap-2">
          <span className="text-accent-amber shrink-0 mt-0.5 text-xs">◆</span>
          <p className="text-sm text-accent-amber/90 leading-relaxed">
            {String(analysis.significance)}
          </p>
        </div>
      )}
    </div>
  );
}
