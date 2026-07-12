// components/common/Badge.tsx

type BadgeVariant = "critical" | "high" | "amber" | "blue" | "muted" | "success";

const variantClasses: Record<BadgeVariant, string> = {
  critical: "bg-critical/20 text-critical border-critical/30",
  high: "bg-high/20 text-high border-high/30",
  amber: "bg-accent-amber/20 text-accent-amber border-accent-amber/30",
  blue: "bg-accent-blue/20 text-accent-blue border-accent-blue/30",
  muted: "bg-muted/20 text-muted-foreground border-border",
  success: "bg-success/20 text-success border-success/30",
};

export default function Badge({
  children,
  variant = "muted",
}: {
  children: React.ReactNode;
  variant?: BadgeVariant;
}) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider border ${variantClasses[variant]}`}
    >
      {children}
    </span>
  );
}

export function stageBadgeVariant(stage: string): BadgeVariant {
  const map: Record<string, BadgeVariant> = {
    breaking: "critical",
    developing: "high",
    active: "blue",
    stable: "success",
    closed: "muted",
  };
  return map[stage] || "muted";
}

export function confidenceBadgeVariant(confidence: number): BadgeVariant {
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.6) return "amber";
  return "muted";
}
