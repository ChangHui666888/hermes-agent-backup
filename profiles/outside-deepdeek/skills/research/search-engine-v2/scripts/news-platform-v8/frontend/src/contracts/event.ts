// contracts/event.ts — Frozen API Contract v1.0
// Mirrors backend/models/schemas.py EventDossier

export interface SAOEntity {
  entity_id?: string;
  name: string;
  type: string;
}

export interface Action {
  type: string;
  detail?: string;
}

export interface Location {
  country?: string;
  region?: string;
}

export interface SourceInfo {
  primary_source: string;
  primary_source_id?: string;
  authority: number;
  source_count: number;
  sources: string[];
}

export interface Actor {
  entity: string;
  type: string;
  role: 'Initiator' | 'Target' | 'Participant';
}

export interface EntityRef {
  entity_id?: string;
  name: string;
  type: string;
}

export interface Evidence {
  quote: string;
  source: string;
  url: string;
}

export interface SourceChainItem {
  source_id: string;
  source_name: string;
  time?: string;
  role: 'break' | 'follow';
  url: string;
}

export interface TimelineItem {
  time?: string;
  update: string;
  source: string;
}

export interface DocRef {
  url: string;
  title: string;
}

export interface EventDossier {
  event_id: string;
  title: string;
  summary?: string;
  event_type: string;
  stage: 'breaking' | 'developing' | 'active' | 'stable' | 'closed';
  confidence: number;
  coherence: number;
  subject: SAOEntity;
  action: Action;
  object: SAOEntity;
  location: Location;
  source: SourceInfo;
  actors: Actor[];
  keywords: string[];
  related_entities: EntityRef[];
  article_count: number;
  first_seen?: string;
  last_updated?: string;
  evidence: Evidence[];
  source_chain: SourceChainItem[];
  timeline: TimelineItem[];
  llm_analysis?: Record<string, unknown>;
}

export interface EventListItem {
  event_id: string;
  title: string;
  event_type: string;
  stage: string;
  confidence: number;
  location_country?: string;
  subject_name?: string;
  action_type?: string;
  object_name?: string;
  source_count: number;
  article_count: number;
  last_updated?: string;
}

export interface EventListResponse {
  total: number;
  page: number;
  limit: number;
  items: EventListItem[];
}
