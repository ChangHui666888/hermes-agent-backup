// components/event/SourceChain.tsx — Information Flow
import type { SourceChainItem } from "@/lib/types";

export default function SourceChain({ items }: { items: SourceChainItem[] }) {
  if (!items || items.length === 0) {
    return (
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
          Information Flow
        </h2>
        <p className="text-sm text-muted-foreground">No source chain data</p>
      </div>
    );
  }

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">
            Information Flow
      </h2>
      <div className="flex flex-wrap items-center gap-2">
        {items.map((sc, i) => (
          <div key={i} className="flex items-center gap-2">
            <div
              className={`px-3 py-2 rounded-lg border text-sm ${
                sc.role === "break"
                  ? "border-primary bg-primary/10 text-primary font-medium"
                  : "border-border bg-secondary text-muted-foreground"
              }`}
            >
              <div className="font-medium">{sc.source_name}</div>
              <div className="text-[10px] opacity-70 mt-0.5">
                {sc.role === "break" ? "BREAK" : "FOLLOW"}
              </div>
            </div>
            {i < items.length - 1 && (
              <span className="text-muted-foreground text-lg">→</span>
            )}
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-1">
        {items.map((sc, i) => (
          <div key={i} className="text-[11px] text-muted-foreground">
            {sc.time && <span className="font-mono">{sc.time}</span>}
            {sc.url && (
              <a
                href={sc.url}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-2 text-primary hover:underline"
              >
                View →
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
