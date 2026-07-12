// app/events/[id]/page.tsx — Event Dossier Detail (client component)
"use client";

import { useEffect, useState, use } from "react";
import { fetchAPI } from "@/lib/api";
import type { EventDossier } from "@/lib/types";
import EventHeader from "@/components/event/EventHeader";
import FactPanel from "@/components/event/FactPanel";
import Timeline from "@/components/event/Timeline";
import EvidenceCard from "@/components/event/EvidenceCard";
import SourceChain from "@/components/event/SourceChain";
import IntelligencePanel from "@/components/event/IntelligencePanel";

export default function EventDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [event, setEvent] = useState<EventDossier | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchAPI<EventDossier>(`/events/${id}`)
      .then(setEvent)
      .catch(() => setError("Event not found"));
  }, [id]);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <p className="text-lg text-muted-foreground">{error}</p>
        <p className="text-sm text-muted-foreground">
          <code className="text-accent-blue">{id}</code>
        </p>
      </div>
    );
  }

  if (!event) {
    return (
      <div className="max-w-5xl mx-auto space-y-6">
        <div className="h-40 bg-card border border-border rounded-xl animate-pulse" />
        <div className="h-32 bg-card border border-border rounded-xl animate-pulse" />
        <div className="h-48 bg-card border border-border rounded-xl animate-pulse" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <EventHeader event={event} />
      <FactPanel event={event} />
      <EvidenceCard items={event.evidence} />
      <Timeline items={event.timeline} stage={event.stage} />
      <SourceChain items={event.source_chain} />
      <IntelligencePanel event={event} />
    </div>
  );
}
