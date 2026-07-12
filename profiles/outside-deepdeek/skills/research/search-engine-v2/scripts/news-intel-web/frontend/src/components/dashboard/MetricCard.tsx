// components/dashboard/MetricCard.tsx
export default function MetricCard({
  label,
  value,
  detail,
  color = "accent-blue",
}: {
  label: string;
  value: number | string;
  detail?: string;
  color?: string;
}) {
  const colorMap: Record<string, string> = {
    "accent-blue": "text-accent-blue",
    "accent-amber": "text-accent-amber",
    critical: "text-critical",
    high: "text-high",
    success: "text-success",
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 flex flex-col justify-between h-28">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
        {label}
      </span>
      <div>
        <span className={`text-3xl font-bold tabular-nums ${colorMap[color] || "text-foreground"}`}>
          {value}
        </span>
        {detail && (
          <p className="text-[11px] text-muted-foreground mt-1">{detail}</p>
        )}
      </div>
    </div>
  );
}
