"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const MENU_SECTIONS = [
  {
    label: "NEWS",
    items: [
      { href: "/articles", label: "Articles", icon: "📰" },
    ],
  },
  {
    label: "INTELLIGENCE",
    items: [
      { href: "/", label: "Situation", icon: "◉" },
    ],
  },
  {
    label: "EVENTS",
    items: [
      { href: "/events", label: "Event Explorer", icon: "▣" },
    ],
  },
  {
    label: "WORLD",
    items: [
      { href: "/map", label: "Geo Monitor", icon: "◎" },
    ],
  },
  {
    label: "SOURCES",
    items: [
      { href: "/sources", label: "Source Network", icon: "◈" },
    ],
  },
  {
    label: "ANALYSIS",
    items: [
      { href: "/search", label: "Search", icon: "⌕" },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <aside className="w-60 bg-secondary border-r border-border flex flex-col shrink-0 h-full">
      <nav className="flex-1 px-3 py-4 space-y-6">
        {MENU_SECTIONS.map((section) => (
          <div key={section.label}>
            <div className="px-3 mb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              {section.label}
            </div>
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 h-10 rounded-md text-sm transition-colors ${
                  isActive(item.href)
                    ? "bg-primary text-primary-foreground font-medium"
                    : "text-foreground/70 hover:bg-accent hover:text-foreground"
                }`}
              >
                <span className="w-5 text-center">{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-border">
        <div className="space-y-1.5 text-[10px] text-muted-foreground">
          <div className="flex justify-between">
            <span>Breaking</span>
            <span className="text-critical font-semibold">2</span>
          </div>
          <div className="flex justify-between">
            <span>Active</span>
            <span className="text-accent-amber font-semibold">5</span>
          </div>
          <div className="flex justify-between">
            <span>Stable</span>
            <span className="text-success font-semibold">2</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
