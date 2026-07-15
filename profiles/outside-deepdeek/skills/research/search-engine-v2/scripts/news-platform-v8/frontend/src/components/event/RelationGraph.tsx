// components/event/RelationGraph.tsx — D3 force-directed SAO graph
"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";

interface RelationNode { id: string; label: string; type: string; group: number; }
interface RelationLink { source: string; target: string; type: string; }

export default function RelationGraph({ nodes, links }: { nodes: RelationNode[]; links: RelationLink[] }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (nodes.length === 0 || !svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    const W = 600, H = 280;

    const color = (d: RelationNode) =>
      ({ Country: "#3B82F6", Company: "#22C55E", Person: "#F59E0B", Event: "#EF4444" } as any)[d.type] || "#94A3B8";

    const sim = d3.forceSimulation(nodes as any)
      .force("link", d3.forceLink(links).id((d: any) => d.id).distance(80))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(W / 2, H / 2));

    const g = svg.append("g");
    svg.call(d3.zoom().on("zoom", (e: any) => g.attr("transform", e.transform)) as any);

    const link = g.append("g").selectAll("line").data(links).join("line")
      .attr("stroke", "#334155").attr("stroke-width", 1.5);

    const node = g.append("g").selectAll("circle").data(nodes).join("circle")
      .attr("r", d => d.type === "Event" ? 8 : 5).attr("fill", d => color(d))
      .attr("stroke", "#1E2A3A").attr("stroke-width", 1)
      .call(d3.drag().on("start", (e: any, d: any) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e: any, d: any) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e: any, d: any) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }) as any);

    const label = g.append("g").selectAll("text").data(nodes).join("text")
      .text(d => d.label).attr("font-size", "9px").attr("fill", "#94A3B8").attr("dx", 8).attr("dy", 3);

    sim.on("tick", () => {
      link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y)
          .attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
    });
  }, [nodes, links]);

  if (nodes.length === 0) return <div className="bg-card border border-border rounded-xl p-5"><h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">Relation Graph</h2><p className="text-sm text-muted-foreground">No data</p></div>;

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <h2 className="text-xs uppercase tracking-wider text-muted-foreground mb-4 font-semibold">Relation Graph</h2>
      <svg ref={svgRef} width="100%" height="280" />
    </div>
  );
}
