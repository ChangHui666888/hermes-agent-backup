// app/map/page.tsx — Geo Monitor V2 (MapLibre + Event-Map linkage)
"use client";

import { useEffect, useState, useCallback } from "react";
import type { MapEvent } from "@/lib/types";
import WorldMap from "@/components/dashboard/WorldMap";
import Link from "next/link";

const REGIONS: Record<string, string[]> = {
  "Middle East": ["Iran","Iraq","Israel","Saudi Arabia","Turkey","Syria","Lebanon","UAE","Jordan","Bahrain","Kuwait","Qatar","Oman","Yemen"],
  "Europe": ["United Kingdom","France","Germany","Ukraine","Russia","Poland","Sweden","Norway","Netherlands","Switzerland","Italy","Spain"],
  "Asia-Pacific": ["China","Japan","South Korea","North Korea","Taiwan","India","Philippines","Vietnam","Indonesia","Thailand","Singapore","Pakistan","Australia"],
  "Americas": ["United States","Canada","Mexico","Brazil","Argentina","Cuba"],
  "Africa": ["Egypt","Nigeria","South Africa","Kenya","Sudan"],
};
const EVENT_TYPES = ["All","Military","Diplomacy","Economic","Political","Legal","Technology"];

export default function GeoMonitorPage() {
  const [allEvents, setAllEvents] = useState<MapEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [region, setRegion] = useState("All");
  const [eventType, setEventType] = useState("All");
  const [limit, setLimit] = useState(50);
  const [hoverId, setHoverId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/map/events")
      .then(r => r.json()).then(d => setAllEvents(d.events || []))
      .catch(() => setError("Failed to load")).finally(() => setLoading(false));
  }, []);

  const filtered = allEvents.filter(ev => {
    if (region !== "All" && ev.country) {
      const countries = REGIONS[region] || [];
      if (!countries.some(c => ev.country === c)) return false;
    }
    if (eventType !== "All" && ev.impact_level !== eventType) return false;
    return true;
  });
  const displayed = filtered.slice(0, limit);

  if (loading) return <div className="h-[520px] bg-card border border-border rounded-xl animate-pulse" />;
  if (error) return <div className="h-[520px] bg-card border border-border rounded-xl flex items-center justify-center"><p className="text-muted-foreground">{error}</p></div>;

  return (
    <div className="space-y-4 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Geo Monitor</h1>
        <span className="text-xs text-muted-foreground">{displayed.length} of {allEvents.length}</span>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <select value={region} onChange={e => setRegion(e.target.value)}
          className="bg-secondary border border-border rounded-md px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-accent-blue">
          <option value="All">All Regions</option>
          {Object.keys(REGIONS).map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <select value={eventType} onChange={e => setEventType(e.target.value)}
          className="bg-secondary border border-border rounded-md px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-accent-blue">
          {EVENT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={limit} onChange={e => setLimit(Number(e.target.value))}
          className="bg-secondary border border-border rounded-md px-3 py-1.5 text-xs text-foreground focus:outline-none focus:border-accent-blue">
          <option value={25}>Top 25</option><option value={50}>Top 50</option><option value={100}>Top 100</option><option value={999}>All</option>
        </select>
      </div>

      {/* Map + Event List */}
      <div className="grid grid-cols-5 gap-4">
        <div className="col-span-3">
          <WorldMap events={displayed} height={520} />
        </div>
        <div className="col-span-2 space-y-2 max-h-[580px] overflow-y-auto">
          <h2 className="text-xs uppercase tracking-wider text-muted-foreground font-semibold sticky top-0 bg-background py-1">Events</h2>
          {displayed.map(ev => (
            <Link key={ev.event_id} href={`/events/${ev.event_id}`}
              onMouseEnter={() => setHoverId(ev.event_id)}
              onMouseLeave={() => setHoverId(null)}
              className={`block p-3 rounded-lg border transition-all text-xs ${
                hoverId === ev.event_id ? "border-accent-blue bg-accent/20" : "border-border bg-card hover:border-accent-blue/50"
              }`}>
              <p className="text-foreground font-medium line-clamp-2 leading-snug">{ev.title}</p>
              <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
                <span>{ev.country || "?"}</span>
                <span>·</span>
                <span>{(ev.confidence*100).toFixed(0)}%</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
