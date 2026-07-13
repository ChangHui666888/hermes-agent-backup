// components/event/EvidenceCard.tsx
import type { Evidence } from "@/lib/types";

export default function EvidenceCard({ items }: { items: Evidence[] }) {
  if (!items || items.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
          Evidence
        </h2>
        <p className="text-sm text-muted-foreground">No evidence collected</p>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
        Evidence
      </h2>
      <div className="space-y-4">
        {items.map((ev, i) => (
          <div key={i} className="border-l-2 border-primary/30 pl-4">
            <blockquote className="text-sm text-foreground italic leading-relaxed">
              &ldquo;{ev.quote}&rdquo;
            </blockquote>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-xs text-muted-foreground">
                — {ev.source}
              </span>
              {ev.url && (
                <a
                  href={ev.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline"
                >
                  View Source →
                </a>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
