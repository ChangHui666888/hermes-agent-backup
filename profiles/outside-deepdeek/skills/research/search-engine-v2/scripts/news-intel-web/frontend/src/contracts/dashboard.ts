// contracts/dashboard.ts — Frozen API Contract v1.0

import type { EventDossier } from './event';

export interface DashboardMetrics {
  active_events: number;
  critical_events: number;
  today_updates: number;
  sources: number;
}

export interface MapEvent {
  event_id: string;
  title: string;
  country?: string;
  impact_level?: string;
  confidence: number;
}

export interface DashboardResponse {
  metrics: DashboardMetrics;
  hot_events: EventDossier[];
  map_events: MapEvent[];
}
