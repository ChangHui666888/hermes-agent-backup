// app/admin/pipeline/page.tsx — Pipeline Config
"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

const CONFIG_SECTIONS = [
  {
    title: "Scoring",
    keys: ["source_scores", "entity_weights", "event_keywords", "asset_graph"],
    type: "json" as const,
  },
  {
    title: "Aggregation",
    keys: ["MIN_SUBJECT_WEIGHT", "HUB_RATIO", "EVENT_THRESHOLD", "MERGE_THRESHOLD"],
    type: "number" as const,
  },
];

export default function PipelineConfigPage() {
  const { token, isAdmin } = useAuth();
  const router = useRouter();
  const [config, setConfig] = useState<Record<string, any>>({});
  const [saved, setSaved] = useState("");

  useEffect(() => {
    if (!token) { router.push("/login"); return; }
    fetch("/admin/pipeline/config", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.json()).then(setConfig);
  }, [token, router]);

  const save = async (key: string, value: any) => {
    const res = await fetch(`/admin/pipeline/config/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(value),
    });
    if (res.ok) setSaved(key);
    setTimeout(() => setSaved(""), 2000);
  };

  if (!isAdmin) return <p className="text-muted-foreground text-center py-12">Admin only</p>;

  return (
    <div className="max-w-[900px] mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-foreground">Pipeline Config</h1>

      {CONFIG_SECTIONS.map(section => (
        <div key={section.title} className="bg-card border border-border rounded-xl p-5">
          <h2 className="text-sm font-semibold text-foreground mb-4">{section.title}</h2>
          <div className="space-y-3">
            {section.keys.map(key => (
              <div key={key} className="flex items-start gap-3">
                <span className="text-xs text-muted-foreground w-40 shrink-0 pt-1 font-mono">{key}</span>
                {section.type === "json" ? (
                  <textarea
                    className="flex-1 bg-secondary border border-border rounded-md px-3 py-1.5 text-xs text-foreground font-mono h-20 focus:outline-none focus:border-accent-blue"
                    value={JSON.stringify(config[key] || {}, null, 2)}
                    onChange={e => setConfig({ ...config, [key]: JSON.parse(e.target.value || "{}") })}
                  />
                ) : (
                  <input
                    type="number" step="0.01"
                    className="flex-1 bg-secondary border border-border rounded-md px-3 py-1.5 text-xs text-foreground font-mono focus:outline-none focus:border-accent-blue"
                    value={config[key] ?? ""}
                    onChange={e => setConfig({ ...config, [key]: parseFloat(e.target.value) || 0 })}
                  />
                )}
                <button
                  onClick={() => save(key, config[key])}
                  className="px-3 py-1.5 bg-accent-blue text-white rounded-md text-xs hover:opacity-90 shrink-0"
                >
                  {saved === key ? "✓" : "Save"}
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
