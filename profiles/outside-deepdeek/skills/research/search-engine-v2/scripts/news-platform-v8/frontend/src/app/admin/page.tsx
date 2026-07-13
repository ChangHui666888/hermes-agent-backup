// app/admin/page.tsx
"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

export default function AdminPage() {
  const { token, isAdmin } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<Record<string,number> | null>(null);

  useEffect(() => {
    if (!token) { router.push("/login"); return; }
    fetch("/admin/dashboard", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(setStats);
  }, [token, router]);

  if (!isAdmin) return <p className="text-muted-foreground text-center py-12">Admin only</p>;
  if (!stats) return <div className="h-32 bg-card border border-border rounded-xl animate-pulse" />;

  return (
    <div className="max-w-[800px] mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-foreground">Admin Dashboard</h1>
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Total Articles", value: stats.articles_total, color: "text-accent-blue" },
          { label: "Published", value: stats.articles_published, color: "text-success" },
          { label: "Users", value: stats.users_total, color: "text-accent-amber" },
          { label: "Active Ads", value: stats.ads_active, color: "text-high" },
        ].map(s => (
          <div key={s.label} className="bg-card border border-border rounded-xl p-4">
            <p className="text-[10px] uppercase text-muted-foreground">{s.label}</p>
            <p className={`text-2xl font-bold mt-1 ${s.color}`}>{s.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
