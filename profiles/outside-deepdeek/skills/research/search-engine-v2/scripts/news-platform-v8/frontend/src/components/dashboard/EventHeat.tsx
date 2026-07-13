// components/dashboard/EventHeat.tsx — Top entities ranked
import type { EventDossier } from "@/lib/types";

interface HeatEntry {
  name: string;
  count: number;
  confidence: number;
}

function buildHeatData(events: EventDossier[], limit = 8): HeatEntry[] {
  const entityMap = new Map<string, { count: number; confSum: number }>();

  for (const ev of events) {
    const names = new Set<string>();
    if (ev.subject.name) names.add(ev.subject.name);
    if (ev.object.name) names.add(ev.object.name);
    for (const a of ev.actors) names.add(a.entity);
    for (const e of ev.related_entities) names.add(e.name);

    for (const name of names) {
      const prev = entityMap.get(name) || { count: 0, confSum: 0 };
      prev.count += 1;
      prev.confSum += ev.confidence;
      entityMap.set(name, prev);
    }
  }

  return Array.from(entityMap.entries())
    .map(([name, v]) => ({
      name,
      count: v.count,
      confidence: v.confSum / v.count,
    }))
    .sort((a, b) => b.count - a.count || b.confidence - a.confidence)
    .slice(0, limit);
}

function confidenceColor(conf: number): string {
  if (conf >= 0.8) return "bg-accent-amber";
  if (conf >= 0.6) return "bg-accent-blue";
  return "bg-muted";
}

export default function EventHeat({ events }: { events: EventDossier[] }) {
  const data = buildHeatData(events);
  const maxCount = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
        Event Heat
      </h2>

      <div className="space-y-2.5">
        {data.map((item) => (
          <div key={item.name} className="flex items-center gap-3">
            <span className="w-24 text-xs text-foreground truncate text-right shrink-0">
              {item.name}
            </span>
            <div className="flex-1 h-4 bg-secondary rounded-sm overflow-hidden">
              <div
                className={`h-full rounded-sm transition-all ${confidenceColor(item.confidence)}`}
                style={{ width: `${(item.count / maxCount) * 100}%` }}
              />
            </div>
            <span className="w-8 text-[11px] text-muted-foreground text-right font-mono tabular-nums shrink-0">
              {item.count}
            </span>
          </div>
        ))}
      </div>

      {data.length === 0 && (
        <p className="text-sm text-muted-foreground">No entity data</p>
      )}
    </div>
  );
}
