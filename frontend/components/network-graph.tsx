"use client";

import { useMemo } from "react";
import { cn } from "@/lib/utils";

export type NetNode = {
  id: string; kind: "U" | "W" | "D" | "A" | "M"; kind_label: string; raw_id: string; depth: number;
  score: number; direct: number | null; degree: number; n_tx: number; expected_frauds: number;
};
export type NetEdge = { source: string; target: string; n_tx: number; expected_frauds: number; amount_usd: number };

/** Couleur du score réseau (mêmes paliers que les niveaux de risque). */
export function scoreColor(s: number) {
  if (s >= 0.7) return "hsl(var(--risk-critique))";
  if (s >= 0.4) return "hsl(var(--risk-eleve))";
  if (s >= 0.15) return "hsl(var(--risk-moyen))";
  return "hsl(var(--risk-faible))";
}
export const KIND_LETTER: Record<string, string> = { U: "C", W: "P", D: "A", A: "Ag", M: "M" };

const W = 800, H = 560;

/** Placement par forces (répulsion, ressorts, gravité), calculé une fois par jeu de données : déterministe. */
function layout(nodes: NetNode[], edges: NetEdge[], center: string) {
  const idx = new Map(nodes.map((n, i) => [n.id, i]));
  const byDepth = new Map<number, number>();
  const pos = nodes.map((n) => {
    const k = byDepth.get(n.depth) ?? 0;
    byDepth.set(n.depth, k + 1);
    const ring = nodes.filter((m) => m.depth === n.depth).length;
    const a = (2 * Math.PI * k) / Math.max(ring, 1) + n.depth;
    const r = n.id === center ? 0 : 90 * n.depth;
    return { x: W / 2 + r * Math.cos(a), y: H / 2 + r * Math.sin(a), vx: 0, vy: 0 };
  });
  const links = edges.map((e) => [idx.get(e.source)!, idx.get(e.target)!]).filter(([a, b]) => a != null && b != null);
  for (let it = 0; it < 320; it++) {
    const cool = 1 - it / 320;
    for (let i = 0; i < pos.length; i++) {
      for (let j = i + 1; j < pos.length; j++) {
        const dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y;
        const d2 = Math.max(dx * dx + dy * dy, 25);
        const f = 2400 / d2;
        const d = Math.sqrt(d2);
        pos[i].vx += (dx / d) * f; pos[i].vy += (dy / d) * f;
        pos[j].vx -= (dx / d) * f; pos[j].vy -= (dy / d) * f;
      }
    }
    for (const [a, b] of links) {
      const dx = pos[b].x - pos[a].x, dy = pos[b].y - pos[a].y;
      const d = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const f = (d - 70) * 0.04;
      pos[a].vx += (dx / d) * f; pos[a].vy += (dy / d) * f;
      pos[b].vx -= (dx / d) * f; pos[b].vy -= (dy / d) * f;
    }
    pos.forEach((p, i) => {
      p.vx += (W / 2 - p.x) * 0.012; p.vy += (H / 2 - p.y) * 0.012;
      if (nodes[i].id === center) { p.x = W / 2; p.y = H / 2; p.vx = p.vy = 0; return; }
      p.x = Math.min(W - 24, Math.max(24, p.x + Math.max(-12, Math.min(12, p.vx)) * cool));
      p.y = Math.min(H - 24, Math.max(24, p.y + Math.max(-12, Math.min(12, p.vy)) * cool));
      p.vx *= 0.5; p.vy *= 0.5;
    });
  }
  return new Map(nodes.map((n, i) => [n.id, pos[i]]));
}

export function NetworkGraph({ nodes, edges, center, selected, onSelect }: {
  nodes: NetNode[]; edges: NetEdge[]; center: string; selected: string | null; onSelect: (id: string) => void;
}) {
  const pos = useMemo(() => layout(nodes, edges, center), [nodes, edges, center]);
  const maxTx = Math.max(1, ...edges.map((e) => e.n_tx));
  const linked = useMemo(() => {
    if (!selected) return null;
    const s = new Set([selected]);
    edges.forEach((e) => { if (e.source === selected) s.add(e.target); if (e.target === selected) s.add(e.source); });
    return s;
  }, [edges, selected]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full select-none" role="img" aria-label="Graphe du réseau">
      <g>
        {edges.map((e) => {
          const a = pos.get(e.source), b = pos.get(e.target);
          if (!a || !b) return null;
          const risky = e.n_tx > 0 && e.expected_frauds / e.n_tx >= 0.5;
          const dim = linked && !(linked.has(e.source) && linked.has(e.target));
          return (
            <line key={`${e.source}|${e.target}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={risky ? "hsl(var(--risk-critique))" : "hsl(var(--muted-foreground))"}
              strokeOpacity={dim ? 0.08 : risky ? 0.75 : 0.3} strokeWidth={1 + 3 * Math.sqrt(e.n_tx / maxTx)}>
              <title>{`${e.n_tx} transaction(s) · ${e.expected_frauds} fraude(s) estimée(s) · ${Math.round(e.amount_usd)} $US`}</title>
            </line>
          );
        })}
      </g>
      <g>
        {nodes.map((n) => {
          const p = pos.get(n.id)!;
          const r = 7 + Math.min(11, Math.log2(1 + n.n_tx) * 1.6);
          const color = scoreColor(n.score);
          const dim = linked && !linked.has(n.id);
          const isSel = n.id === selected, isCenter = n.id === center;
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} onClick={() => onSelect(n.id)}
              className={cn("cursor-pointer transition-opacity", dim && "opacity-25")}>
              {(isSel || isCenter) && (
                n.kind === "U"
                  ? <circle r={r + 5} fill="none" stroke="hsl(var(--primary))" strokeWidth={isSel ? 2.5 : 1.5} strokeDasharray={isSel ? undefined : "3 3"} />
                  : <rect x={-r - 5} y={-r - 5} width={2 * r + 10} height={2 * r + 10} rx={6} fill="none" stroke="hsl(var(--primary))" strokeWidth={isSel ? 2.5 : 1.5} strokeDasharray={isSel ? undefined : "3 3"} />
              )}
              {n.kind === "U"
                ? <circle r={r} fill={color} stroke="hsl(var(--card))" strokeWidth={2} />
                : <rect x={-r} y={-r} width={2 * r} height={2 * r} rx={4} fill={color} stroke="hsl(var(--card))" strokeWidth={2} />}
              <text textAnchor="middle" dy="0.35em" className="pointer-events-none fill-white text-[9px] font-bold">{KIND_LETTER[n.kind]}</text>
              {(isSel || isCenter || n.score >= 0.4) && (
                <text y={r + 12} textAnchor="middle" className="pointer-events-none fill-foreground font-mono text-[9px]">
                  {n.raw_id.length > 14 ? `${n.raw_id.slice(0, 13)}…` : n.raw_id}
                </text>
              )}
              <title>{`${n.kind_label} ${n.raw_id} · score ${Math.round(n.score * 100)} % · ${n.n_tx} transaction(s)`}</title>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
