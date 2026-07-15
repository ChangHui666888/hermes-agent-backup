// components/event/RelationGraph.tsx — D3 force-directed event relations
"use client";

import { useEffect, useRef } from "react";

interface RelationNode {
  id: string; label: string; type: string; group: number;
}
interface RelationLink {
  source: string; target: string; type: string;
}

export default function RelationGraph({
  nodes, links,
}: {
  nodes: RelationNode[]; links: RelationLink[];
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (nodes.length === 0) return;
    // Dynamic import D3
    import("d3").then(async d3 => {
      const d3Force = await import("d3-force");
      const d3Select = await import("d3-selection");
      const d3Drag = await import("d3-drag");
      const d3Zoom = await import("d3-zoom");

      const svg = d3Select.select(svgRef.current);
      svg.selectAll("*").remove();
      const width = 600, height = 300;

      const color = (d: RelationNode) => {
        const map: Record<string, string> = { Country: "#3B82F6", Company: "#22C55E", Person: "#F59E0B", Event: "#EF4444" };
        return map[d.type] || "#94A3B8";
      };

      const simulation = d3Force.forceSimulation(nodes as any)
        .force("link", d3Force.forceLink(links).id((d: any) => d.id).distance(80))
        .force("charge", d3Force.forceManyBody().strength(-200))
        .force("center", d3Force.forceCenter(width / 2, height / 2));

      const g = svg.append("g");
      const zoom = d3Zoom.zoom().on("zoom", (e: any) => g.attr("transform", e.transform));
      (svg as any).call(zoom);

      const link = g.append("g").selectAll("line").data(links).join("line")
        .attr("stroke", "#334155").attr("stroke-width", 1.5).attr("stroke-dasharray", "4,2");

      const node = g.append("g").selectAll("circle").data(nodes).join("circle")
        .attr("r", d => d.type === "Event" ? 8 : 5)
        .attr("fill", d => color(d))
        .attr("stroke", "#1E2A3A").attr("stroke-width", 1)
        .call((d3Drag.drag() as any)
          .on("start", (e: any, d: any) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
          .on("drag", (e: any, d: any) => { d.fx = e.x; d.fy = e.y; })
          .on("end", (e: any, d: any) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }));

      const label = g.append("g").selectAll("text").data(nodes).join("text")
        .text(d => d.label).attr("font-size", "9px").attr("fill", "#94A3B8")
        .attr("dx", 8).attr("dy", 3);

      simulation.on("tick", () => {
        link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y)
            .attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
        node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
        label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
      });
    });
  }, [nodes, links]);

  if (nodes.length === 0) return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">Relation Graph</h2>
      <p className="text-sm text-muted-foreground">No relation data</p>
    </div>
  );

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">Relation Graph</h2>
      <svg ref={svgRef} width="100%" height="300" />
      <div className="flex gap-3 mt-2 text-[10px] text-muted-foreground">
        {[["Event","#EF4444"],["Country","#3B82F6"],["Company","#22C55E"],["Person","#F59E0B"]].map(([label,color]) => (
          <span key={label} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full" style={{background:color}} /> {label}
          </span>
        ))}
      </div>
    </div>
  );
}
