// components/dashboard/MapLibreWorldMap.tsx — WebGL map (V2)
"use client";

import { useEffect, useRef, useState } from "react";
import type { MapEvent } from "@/lib/types";

// CartoDB Dark Matter — free CDN, no API key needed
const MAP_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

const COUNTRY_COORDS: Record<string, [number, number]> = {
  "United States": [-95, 38], "China": [104, 35], "Russia": [90, 60],
  "Iran": [53, 32], "Ukraine": [31, 49], "United Kingdom": [-3, 55],
  "France": [2, 47], "Germany": [10, 51], "Israel": [35, 31],
  "India": [78, 21], "Japan": [138, 36], "Brazil": [-55, -5],
  "Australia": [133, -25], "Canada": [-105, 55], "Mexico": [-102, 23],
  "Turkey": [35, 39], "Saudi Arabia": [45, 25], "South Korea": [127, 36],
  "North Korea": [127, 40], "Taiwan": [121, 24], "Philippines": [122, 13],
  "Vietnam": [108, 14], "Indonesia": [117, -2], "Pakistan": [70, 30],
  "Iraq": [43, 33], "Syria": [38, 35], "Lebanon": [36, 34],
  "Egypt": [31, 26], "Nigeria": [8, 10], "South Africa": [24, -29],
  "Kenya": [38, 1], "UAE": [54, 24], "Switzerland": [8, 47],
  "Sweden": [18, 63], "Norway": [8, 62], "Netherlands": [5, 52],
  "Poland": [19, 52], "Argentina": [-64, -34], "Singapore": [104, 1],
  "Thailand": [100, 15], "Cuba": [-77, 21], "Albania": [20, 41],
};

export default function MapLibreWorldMap({
  events, height = 300,
}: {
  events: MapEvent[]; height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let maplibre: any;
    import("maplibre-gl").then(m => {
      maplibre = m.default;
      if (!containerRef.current) return;
      const map = new maplibre.Map({
        container: containerRef.current,
        style: MAP_STYLE,
        center: [20, 15],
        zoom: 1.5,
        attributionControl: false,
        renderWorldCopies: false,
      });
      map.scrollZoom.disable();
      mapRef.current = map;
      map.on("load", () => setReady(true));
    });
    return () => { mapRef.current?.remove(); };
  }, []);

  // Update markers when events change
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    // Clear old markers
    markersRef.current.forEach(m => m.remove());
    markersRef.current = [];

    const validMarkers = events.filter(ev => ev.country && COUNTRY_COORDS[ev.country]);
    if (validMarkers.length === 0) return;

    // Fit bounds
    const bounds = new (window as any).maplibregl.LngLatBounds();
    validMarkers.forEach(ev => {
      bounds.extend(COUNTRY_COORDS[ev.country!]);
    });
    map.fitBounds(bounds, { padding: 40, maxZoom: 5, duration: 1000 });

    // Add markers
    validMarkers.forEach(ev => {
      const coords = COUNTRY_COORDS[ev.country!];
      const color = ev.confidence >= 0.8 ? "#EF4444" : ev.confidence >= 0.6 ? "#F97316" : "#F59E0B";
      const el = document.createElement("div");
      el.className = "map-marker";
      el.style.cssText = `width:${8 + ev.confidence * 10}px;height:${8 + ev.confidence * 10}px;background:${color};border-radius:50%;border:2px solid ${color};opacity:0.8;cursor:pointer;`;
      el.title = ev.title;
      if ((window as any).maplibregl) {
        const marker = new (window as any).maplibregl.Marker({ element: el })
          .setLngLat(coords)
          .addTo(map);
        markersRef.current.push(marker);
      }
    });
  }, [events, ready]);

  const validCount = events.filter(ev => ev.country && COUNTRY_COORDS[ev.country]).length;

  return (
    <div className="bg-card border border-border rounded-xl p-4 relative overflow-hidden">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-2 font-semibold">
        Global Situation
      </h2>
      <div ref={containerRef} style={{ height: `${height}px`, width: "100%" }} />
      <div className="flex items-center gap-3 mt-2 text-[10px] text-muted-foreground">
        <span className="text-critical">● High</span>
        <span className="text-high">● Medium</span>
        <span className="text-accent-amber">● Other</span>
        <span className="ml-auto">{validCount} events</span>
      </div>
    </div>
  );
}
