// components/dashboard/IntelligenceFeed.tsx — Live intelligence stream
import Link from "next/link";
import type { EventDossier } from "@/lib/types";
import { formatDistanceToNow } from "date-fns";

function feedItemClass(stage: string): string {
  if (stage === "breaking") return "border-l-critical";
  if (stage === "developing") return "border-l-high";
  return "border-l-accent-blue";
}

function feedLabel(ev: EventDossier): string {
  if (ev.stage === "breaking") return "NEW";
  if (ev.stage === "developing") return "UPDATE";
  return "ACTIVE";
}

function feedLabelColor(ev: EventDossier): string {
  if (ev.stage === "breaking") return "bg-critical/20 text-critical";
  if (ev.stage === "developing") return "bg-high/20 text-high";
  return "bg-accent-blue/20 text-accent-blue";
}

export default function IntelligenceFeed({ events }: { events: EventDossier[] }) {
  if (!events || events.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-4">
        <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
          Intelligence Feed
        </h2>
        <p className="text-sm text-muted-foreground">No recent intelligence</p>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
        Intelligence Feed
      </h2>

      <div className="space-y-0">
        {events.slice(0, 5).map((ev) => (
          <Link
            key={ev.event_id}
            href={`/events/${ev.event_id}`}
            className={`block border-l-2 pl-3 py-2.5 hover:bg-accent/50 transition-colors rounded-r-md ${
              ev.stage === "breaking"
                ? "border-l-critical"
                : ev.stage === "developing"
                ? "border-l-high"
                : "border-l-accent-blue"
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider ${feedLabelColor(ev)}`}>
                {feedLabel(ev)}
              </span>
              {ev.confidence >= 0.8 && (
                <span className="text-[9px] text-accent-amber font-bold">CONF {Math.round(ev.confidence * 100)}%</span>
              )}
            </div>
            <p className="text-sm text-foreground mt-1 line-clamp-2 leading-snug">
              {ev.title}
            </p>
            {ev.last_updated && (
              <p className="text-[10px] text-muted-foreground mt-1 font-mono">
                {(() => {
                  try {
                    return formatDistanceToNow(new Date(ev.last_updated), { addSuffix: true });
                  } catch {
                    return ev.last_updated;
                  }
                })()}
              </p>
            )}
          </Link>
        ))}
      </div>

      {/* Summary */}
      <div className="mt-3 pt-3 border-t border-border flex items-center justify-between text-[10px] text-muted-foreground">
        <span>{events.filter((e) => e.stage === "breaking").length} breaking</span>
        <span>{events.filter((e) => e.stage === "developing").length} developing</span>
        <span>{events.filter((e) => e.stage === "active").length} active</span>
      </div>
    </div>
  );
}
