// components/event/FactPanel.tsx
import type { EventDossier } from "@/lib/types";

const ENTITY_EMOJI: Record<string, string> = {
  Country: "🌍",
  Company: "🏢",
  Person: "👤",
  Organization: "🏛",
  Location: "📍",
};

function emojiFor(type: string): string {
  return ENTITY_EMOJI[type] || "🔹";
}

export default function FactPanel({ event }: { event: EventDossier }) {
  const facts = [
    { label: "Subject", value: event.subject.name, type: event.subject.type, id: event.subject.entity_id },
    { label: "Action", value: event.action.type, type: "", id: undefined, detail: event.action.detail },
    { label: "Object", value: event.object.name, type: event.object.type, id: event.object.entity_id },
    { label: "Location", value: event.location.country || "Unknown", type: "Country", id: undefined },
    { label: "Time", value: event.first_seen || "Unknown", type: "", id: undefined },
  ];

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
        Facts
      </h2>
      <div className="space-y-3">
        {facts.map((f) => (
          <div key={f.label} className="flex items-center gap-3">
            <span className="text-[10px] uppercase font-semibold text-muted-foreground w-16 shrink-0 text-right">
              {f.label}
            </span>
            <span className="text-sm text-foreground font-medium">
              {f.type && <span className="mr-1.5">{emojiFor(f.type)}</span>}
              {f.value || "—"}
            </span>
            {f.detail && (
              <span className="text-xs text-muted-foreground italic ml-1">
                — {f.detail}
              </span>
            )}
            {f.id && (
              <code className="text-[10px] text-muted-foreground bg-secondary px-1.5 py-0.5 rounded">
                {f.id}
              </code>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
