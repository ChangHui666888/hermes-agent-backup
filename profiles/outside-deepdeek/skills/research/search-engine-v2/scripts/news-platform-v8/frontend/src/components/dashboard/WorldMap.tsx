// components/dashboard/WorldMap.tsx — Situational Awareness
"use client";

import { useState } from "react";
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from "react-simple-maps";
import type { MapEvent } from "@/lib/types";

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

const GEO_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";

export default function WorldMap({
  events,
  height = 300,
}: {
  events: MapEvent[];
  height?: number;
}) {
  const [tooltip, setTooltip] = useState<MapEvent | null>(null);

  const markers = events
    .filter((ev) => ev.country && COUNTRY_COORDS[ev.country])
    .map((ev) => ({
      ...ev,
      coords: COUNTRY_COORDS[ev.country!],
    }));

  const maxConf = Math.max(...markers.map((m) => m.confidence), 0.5);
  const scale = height > 400 ? 140 : 100;
  const markerBase = height > 400 ? 6 : 4;
  const markerRange = height > 400 ? 12 : 8;

  const markerColor = (confidence: number): string => {
    if (confidence >= 0.8) return "#EF4444";
    if (confidence >= 0.6) return "#F97316";
    return "#F59E0B";
  };

  const markerSize = (confidence: number): number => {
    return markerBase + (confidence / maxConf) * markerRange;
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 relative overflow-hidden">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-2 font-semibold">
        Global Situation
      </h2>
      <div style={{ height: `${height}px`, width: "100%" }}>
        <ComposableMap
          projection="geoMercator"
          projectionConfig={{ scale, center: [20, 15] }}
          style={{ width: "100%", height: "100%" }}
        >
          <ZoomableGroup zoom={1} maxZoom={6}>
            <Geographies geography={GEO_URL}>
              {({ geographies }) =>
                geographies.map((geo) => (
                  <Geography
                    key={geo.rsmKey}
                    geography={geo}
                    fill="#1A2030"
                    stroke="#263244"
                    strokeWidth={0.5}
                    style={{
                      default: { outline: "none" },
                      hover: { fill: "#1E2A3A", outline: "none" },
                      pressed: { outline: "none" },
                    }}
                  />
                ))
              }
            </Geographies>
            {markers.map((m) => (
              <Marker key={m.event_id} coordinates={m.coords}>
                <circle
                  r={markerSize(m.confidence)}
                  fill={markerColor(m.confidence)}
                  fillOpacity={0.8}
                  stroke={markerColor(m.confidence)}
                  strokeWidth={1}
                  style={{ cursor: "pointer", transition: "r 0.2s" }}
                  onMouseEnter={() => setTooltip(m)}
                  onMouseLeave={() => setTooltip(null)}
                />
              </Marker>
            ))}
          </ZoomableGroup>
        </ComposableMap>
      </div>

      {tooltip && (
        <div className="absolute bottom-4 left-4 right-4 bg-elevated border border-border rounded-lg p-3 pointer-events-none z-10">
          <p className="text-sm font-medium text-foreground">{tooltip.title}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-xs text-muted-foreground">{tooltip.country}</span>
            <span className="text-xs text-muted-foreground">·</span>
            <span className="text-xs text-muted-foreground">
              {(tooltip.confidence * 100).toFixed(0)}% confidence
            </span>
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 mt-2 text-[10px] text-muted-foreground">
        <span className="text-critical">● High</span>
        <span className="text-high">● Medium</span>
        <span className="text-accent-amber">● Other</span>
        <span className="ml-auto">{markers.length} events</span>
      </div>
    </div>
  );
}
