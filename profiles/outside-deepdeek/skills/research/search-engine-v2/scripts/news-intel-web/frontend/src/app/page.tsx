// app/page.tsx — Situation Awareness Center
"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import type { DashboardResponse } from "@/lib/types";
import WorldMap from "@/components/dashboard/WorldMap";
import EventHeat from "@/components/dashboard/EventHeat";
import IntelligenceFeed from "@/components/dashboard/IntelligenceFeed";
import EventCard from "@/components/event/EventCard";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchAPI<DashboardResponse>("/dashboard")
      .then(setData)
      .catch(() => setError("API unavailable"));
  }, []);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-lg text-muted-foreground">API unavailable</p>
        <p className="text-sm text-muted-foreground">Ensure the FastAPI backend is running.</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4 max-w-[1200px] mx-auto">
        <div className="grid grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 bg-card border border-border rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  const { metrics, hot_events, map_events } = data;
  const breaking = hot_events.filter((e) => e.stage === "breaking").length;
  const highConf = hot_events.filter((e) => e.confidence >= 0.8).length;

  return (
    <div className="space-y-4 max-w-[1240px] mx-auto">

      {/* ================================================================ */}
      {/* LAYER 1: Global Situation — 5 seconds, system state              */}
      {/* ================================================================ */}
      <div className="bg-card border border-border rounded-xl p-5">
        <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-3 font-semibold">
          Global Situation
        </h2>
        <div className="grid grid-cols-5 gap-6">
          <div>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Active</span>
            <p className="text-2xl font-bold text-foreground mt-0.5">{metrics.active_events}</p>
          </div>
          <div>
            <span className="text-[10px] uppercase tracking-wider text-critical">Breaking</span>
            <p className="text-2xl font-bold text-critical mt-0.5">{breaking}</p>
          </div>
          <div>
            <span className="text-[10px] uppercase tracking-wider text-high">High Impact</span>
            <p className="text-2xl font-bold text-high mt-0.5">{highConf}</p>
          </div>
          <div>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Today</span>
            <p className="text-2xl font-bold text-foreground mt-0.5">{metrics.today_updates}</p>
          </div>
          <div>
            <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Sources</span>
            <p className="text-2xl font-bold text-foreground mt-0.5">{metrics.sources}</p>
          </div>
        </div>
      </div>

      {/* ================================================================ */}
      {/* LAYER 2: World Map (60%) + Hot Events (40%)                      */}
      {/* ================================================================ */}
      <div className="grid grid-cols-5 gap-4">
        {/* Map: answers "where is the world changing?" */}
        <div className="col-span-3">
          <WorldMap events={map_events} />
        </div>

        {/* Hot events: answers "what matters most right now?" */}
        <div className="col-span-2 space-y-3">
          <h2 className="text-xs uppercase tracking-wider text-muted-foreground font-semibold px-1">
            Hot Events
          </h2>
          {hot_events.slice(0, 3).map((ev) => (
            <EventCard key={ev.event_id} event={ev} />
          ))}
        </div>
      </div>

      {/* ================================================================ */}
      {/* LAYER 3: Event Heat (entity ranking) + Intelligence Feed         */}
      {/* ================================================================ */}
      <div className="grid grid-cols-5 gap-4">
        {/* Entity heat: answers "which entities are driving events?" */}
        <div className="col-span-3">
          <EventHeat events={hot_events} />
        </div>

        {/* Feed: answers "what changed recently?" */}
        <div className="col-span-2">
          <IntelligenceFeed events={hot_events} />
        </div>
      </div>
    </div>
  );
}
