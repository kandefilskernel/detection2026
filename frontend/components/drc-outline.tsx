"use client";

import { useEffect, useState } from "react";
import type { FeatureCollection, MultiPolygon } from "geojson";

/** Grandes villes signalées par un point lumineux (chef-lieu, coordonnées approximatives). */
const CITIES = [
  { name: "Kinshasa", lat: -4.325, lng: 15.322, major: true },
  { name: "Lubumbashi", lat: -11.664, lng: 27.479, major: true },
  { name: "Goma", lat: -1.679, lng: 29.222 },
  { name: "Bukavu", lat: -2.508, lng: 28.861 },
  { name: "Kisangani", lat: 0.515, lng: 25.191 },
  { name: "Mbuji-Mayi", lat: -6.136, lng: 23.59 },
  { name: "Kananga", lat: -5.896, lng: 22.417 },
  { name: "Mbandaka", lat: 0.048, lng: 18.26 },
  { name: "Kolwezi", lat: -10.716, lng: 25.473 },
];

const W = 600;

type Shape = { name: string; d: string };

/** Silhouette des 26 provinces de la RDC (contours locaux, sans service externe), avec les grandes villes. */
export function DrcOutline({ className }: { className?: string }) {
  const [shapes, setShapes] = useState<{ provinces: Shape[]; h: number; project: (lng: number, lat: number) => [number, number] } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/geo/rdc-provinces.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((geo: FeatureCollection<MultiPolygon, { name: string }> | null) => {
        if (!geo || cancelled) return;
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        for (const f of geo.features) for (const poly of f.geometry.coordinates) for (const [x, y] of poly[0]) {
          minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
        }
        const k = W / (maxX - minX);
        const h = (maxY - minY) * k;
        const project = (lng: number, lat: number): [number, number] => [(lng - minX) * k, (maxY - lat) * k];
        const provinces = geo.features.map((f) => ({
          name: f.properties.name,
          d: f.geometry.coordinates.map((poly) =>
            poly.map((ring) => "M" + ring.map(([x, y]) => project(x, y).map((v) => v.toFixed(1)).join(",")).join("L") + "Z").join("")).join(""),
        }));
        setShapes({ provinces, h, project });
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  // réserve la place de la carte pendant le chargement des contours : pas de saut de mise en page
  if (!shapes) return <div className={className} style={{ aspectRatio: "1 / 1" }} aria-hidden />;
  return (
    <svg viewBox={`-10 -10 ${W + 20} ${shapes.h + 20}`} className={className} role="img"
      aria-label="Carte des 26 provinces de la République démocratique du Congo">
      <defs>
        <linearGradient id="drc-fill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity="0.16" />
          <stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity="0.10" />
        </linearGradient>
      </defs>
      <g>
        {shapes.provinces.map((p) => (
          <path key={p.name} d={p.d} fill="url(#drc-fill)" stroke="hsl(var(--primary))" strokeOpacity="0.35"
            strokeWidth="0.8" strokeLinejoin="round" className="transition-[fill-opacity] duration-300 hover:fill-opacity-80">
            <title>{p.name}</title>
          </path>
        ))}
      </g>
      <g>
        {CITIES.map((c, i) => {
          const [x, y] = shapes.project(c.lng, c.lat);
          return (
            <g key={c.name} transform={`translate(${x.toFixed(1)} ${y.toFixed(1)})`}>
              <circle r={c.major ? 14 : 10} className="landing-pulse" style={{ animationDelay: `${(i * 0.45) % 3}s` }}
                fill="hsl(var(--primary))" fillOpacity="0.25" />
              <circle r={c.major ? 4.5 : 3.2} fill="hsl(var(--primary))" stroke="hsl(var(--background))" strokeWidth="1.5" />
              {c.major && (
                <text x="9" y="4" className="fill-foreground text-[13px] font-medium" style={{ paintOrder: "stroke" }}
                  stroke="hsl(var(--background))" strokeWidth="3">{c.name}</text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
