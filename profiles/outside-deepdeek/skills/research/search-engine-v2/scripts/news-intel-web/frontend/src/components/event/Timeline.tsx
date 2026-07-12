// components/event/Timeline.tsx — v2: Stage progress
import type { TimelineItem } from "@/lib/types";

const STAGE_ORDER = ["breaking", "developing", "active", "stable", "closed"];
const STAGE_LABELS: Record<string, string> = {
  breaking: "Breaking",
  developing: "Official / Developing",
  active: "Follow-up / Reaction",
  stable: "Analysis",
  closed: "Verified / Closed",
};

export default function Timeline({
  items,
  stage,
}: {
  items: TimelineItem[];
  stage?: string;
}) {
  if (!items || items.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
          Evolution
        </h2>
        <p className="text-sm text-muted-foreground">No timeline data</p>
      </div>
    );
  }

  const currentIdx = STAGE_ORDER.indexOf(stage || "");
  const currentLabel = STAGE_LABELS[stage || ""] || stage;

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
          Evolution
        </h2>
        {currentLabel && (
          <span className="text-[10px] px-2 py-0.5 bg-accent-blue/20 text-accent-blue rounded font-medium">
            {currentLabel}
          </span>
        )}
      </div>

      {/* Stage progress bar */}
      <div className="flex gap-1 mb-6">
        {STAGE_ORDER.map((s, i) => {
          const reached = currentIdx >= i;
          const isActive = i === currentIdx;
          return (
            <div
              key={s}
              className={`flex-1 h-1 rounded-full transition-colors ${
                isActive
                  ? "bg-accent-amber"
                  : reached
                  ? "bg-accent-blue/60"
                  : "bg-border"
              }`}
            />
          );
        })}
      </div>

      {/* Timeline nodes */}
      <div className="relative">
        {items.map((item, i) => (
          <div key={i} className="flex gap-4 pb-4 last:pb-0">
            <div className="flex flex-col items-center shrink-0">
              <div
                className={`w-2.5 h-2.5 rounded-full mt-1.5 ${
                  i === items.length - 1
                    ? "bg-accent-amber ring-2 ring-accent-amber/30"
                    : i === 0
                    ? "bg-accent-blue ring-2 ring-accent-blue/30"
                    : "bg-border"
                }`}
              />
              {i < items.length - 1 && (
                <div className="w-px flex-1 bg-border mt-1" />
              )}
            </div>
            <div className="flex-1 min-w-0 pb-2">
              <p className="text-sm text-foreground leading-snug">{item.update}</p>
              <div className="flex items-center gap-2 mt-0.5">
                {item.time && (
                  <span className="text-[11px] text-muted-foreground font-mono">
                    {item.time}
                  </span>
                )}
                {item.source && (
                  <span className="text-[11px] text-muted-foreground">
                    · {item.source}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
