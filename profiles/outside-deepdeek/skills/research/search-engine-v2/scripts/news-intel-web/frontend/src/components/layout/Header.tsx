"use client";

import { useEffect, useState } from "react";

export default function Header() {
  const [utcTime, setUtcTime] = useState("");

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setUtcTime(now.toISOString().replace("T", " ").slice(0, 19) + " UTC");
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="h-16 bg-background border-b border-border flex items-center px-6 shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-3 w-72 shrink-0">
        <div className="w-8 h-8 rounded-md bg-critical/80 flex items-center justify-center">
          <span className="text-white font-bold text-sm">S</span>
        </div>
        <span className="font-semibold text-sm text-foreground tracking-tight leading-tight">
          SENTINEL<br />
          <span className="text-[10px] text-muted-foreground font-normal tracking-wider">
            INTELLIGENCE
          </span>
        </span>
      </div>

      {/* Search */}
      <div className="flex-1 flex justify-center px-8">
        <div className="w-[360px]">
          <input
            type="text"
            placeholder="Search events, entities, countries..."
            className="w-full h-9 bg-secondary border border-border rounded-md px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent-blue focus:ring-1 focus:ring-accent-blue transition-colors"
          />
        </div>
      </div>

      {/* Stats + Pipeline + UTC */}
      <div className="flex items-center gap-6 w-80 justify-end shrink-0">
        <span className="text-[11px] text-muted-foreground font-mono tabular-nums">
          <span className="text-foreground font-semibold">9</span> EVENTS
        </span>
        <span className="text-[11px] text-muted-foreground font-mono tabular-nums">
          <span className="text-foreground font-semibold">12</span> SOURCES
        </span>
        <button
          title="Pipeline: RSS · Fetcher · Aggregator · LLM"
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-md hover:bg-accent transition-colors"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
          <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
            PIPELINE OK
          </span>
        </button>
        <span className="text-[11px] text-muted-foreground font-mono tabular-nums">
          {utcTime || "..."}
        </span>
      </div>
    </header>
  );
}
