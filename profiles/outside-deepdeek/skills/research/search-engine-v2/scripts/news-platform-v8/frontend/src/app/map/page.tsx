// app/map/page.tsx — Geo Monitor
"use client";

import { useEffect, useState } from "react";
import { fetchAPI } from "@/lib/api";
import type { MapEvent } from "@/lib/types";
import WorldMap from "@/components/dashboard/WorldMap";

export default function GeoMonitorPage() {
  const [events, setEvents] = useState<MapEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchAPI<{ events: MapEvent[] }>("/map/events")
      .then((d) => setEvents(d.events || []))
      .catch(() => setError("Failed to load map data"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4 max-w-[1200px] mx-auto">
      <h1 className="text-2xl font-bold text-foreground">Geo Monitor</h1>
      <p className="text-sm text-muted-foreground">
        Geographic event distribution — {events.length} events with known locations.
      </p>

      {loading && (
        <div className="h-[500px] bg-card border border-border rounded-xl animate-pulse flex items-center justify-center">
          <p className="text-muted-foreground">Loading map...</p>
        </div>
      )}

      {error && (
        <div className="h-[500px] bg-card border border-border rounded-xl flex items-center justify-center">
          <p className="text-muted-foreground">{error}</p>
        </div>
      )}

      {!loading && !error && (
        <WorldMap events={events} height={520} />
      )}
    </div>
  );
}
