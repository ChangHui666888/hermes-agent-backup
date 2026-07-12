// contracts/source.ts — Frozen API Contract v1.0

export interface SourceEntity {
  source_id: string;
  name: string;
  type: 'MEDIA' | 'GOVERNMENT' | 'RESEARCH' | 'SOCIAL';
  authority: number;
  event_count: number;
}
