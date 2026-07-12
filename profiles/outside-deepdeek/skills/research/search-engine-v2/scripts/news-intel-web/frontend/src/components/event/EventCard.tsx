// components/event/EventCard.tsx — v2: SAO + stage bar + source chain
"use client";

import Link from "next/link";
import type { EventDossier } from "@/lib/types";

function stageDot(stage: string): { color: string; label: string } {
  const map: Record<string, { color: string; label: string }> = {
    breaking: { color: "bg-critical", label: "Breaking" },
    developing: { color: "bg-high", label: "Developing" },
    active: { color: "bg-accent-amber", label: "Active" },
    stable: { color: "bg-success", label: "Stable" },
    closed: { color: "bg-muted", label: "Closed" },
  };
  return map[stage] || { color: "bg-muted", label: stage };
}

export default function EventCard({ event }: { event: EventDossier }) {
  const st = stageDot(event.stage);
  const confidencePct = Math.round(event.confidence * 100);
  const isHighConf = event.confidence >= 0.8;

  return (
    <Link
      href={`/events/${event.event_id}`}
      className={`block bg-card border rounded-xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/30 ${
        isHighConf ? "border-l-4 border-l-critical border-border" : "border-border"
      }`}
    >
      {/* Stage indicator */}
      <div className="flex items-center gap-2 mb-2">
        <span className={`w-2 h-2 rounded-full ${st.color}`} />
        <span className="text-[10px] uppercase font-semibold tracking-wider text-muted-foreground">
          {st.label}
        </span>
        {isHighConf && (
          <span className="text-[10px] uppercase font-bold text-critical">HIGH</span>
        )}
      </div>

      {/* Title */}
      <h3 className="text-sm font-semibold text-foreground leading-snug line-clamp-2 mb-2">
        {event.title}
      </h3>

      {/* SAO */}
      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        {event.subject.name && (
          <span className="text-[11px] text-muted-foreground bg-secondary px-1.5 py-0.5 rounded">
            {event.subject.name}
          </span>
        )}
        {event.action.type !== "OTHER" && (
          <span className="text-[11px] text-foreground font-semibold">
            {event.action.type}
          </span>
        )}
        {event.object.name && (
          <span className="text-[11px] text-muted-foreground bg-secondary px-1.5 py-0.5 rounded">
            {event.object.name}
          </span>
        )}
      </div>

      {/* Stage progress bar */}
      <div className="flex gap-0.5 mb-3">
        {["breaking", "developing", "active", "stable"].map((s) => {
          const STAGES = ["breaking", "developing", "active", "stable", "closed"];
          const curr = STAGES.indexOf(event.stage);
          const idx = STAGES.indexOf(s);
          const reached = curr >= idx;
          return (
            <div
              key={s}
              className={`flex-1 h-1 rounded-full ${
                curr === idx
                  ? "bg-accent-amber"
                  : reached
                  ? "bg-accent-blue/60"
                  : "bg-border"
              }`}
            />
          );
        })}
      </div>

      {/* Sources + Confidence */}
      <div className="flex items-center justify-between text-[11px]">
        <div className="flex items-center gap-2 text-muted-foreground">
          <span>{event.source.source_count} src</span>
          {event.source.primary_source && (
            <>
              <span>·</span>
              <span className="font-medium text-foreground/80">
                {event.source.primary_source}
              </span>
            </>
          )}
        </div>
        <span className={`font-mono font-bold tabular-nums ${isHighConf ? "text-critical" : "text-accent-blue"}`}>
          {confidencePct}%
        </span>
      </div>
    </Link>
  );
}
