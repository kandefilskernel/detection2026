"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import type * as Leaflet from "leaflet";
import type { Feature, FeatureCollection, MultiPolygon, Position } from "geojson";
import { DRC_BOUNDS, fraudPosition, provinceGeo } from "@/lib/geo";
import { fmtDate, fmtInt, fmtPct, fmtUsd, RISK_LABEL } from "@/lib/utils";

export type ProvinceStat = {
  province: string; frauds: number; confirmed: number; blocked: number; amount_usd: number; max_probability: number;
};
export type FraudPoint = {
  transaction_id: string; tx_time: string; scored_at: string; user_id: string; channel: string; operator: string | null;
  tx_type: string; amount_usd: number; province: string; fraud_probability: number; risk_level: string; action: string;
  label: number | null; fraud_type?: string | null;
};
export type Basemap = "clair" | "sombre";
type ProvinceFeature = Feature<MultiPolygon, { name: string; iso: string }>;

// Mêmes teintes que --risk-* (globals.css)
export const RISK_COLOR: Record<string, string> = {
  CRITIQUE: "hsl(0, 72%, 50%)", ELEVE: "hsl(24, 90%, 50%)", MOYEN: "hsl(42, 92%, 46%)", FAIBLE: "hsl(152, 55%, 38%)",
};
// Densité par province : palette bleue séquentielle (ne se confond pas avec les couleurs de risque des points)
export const DENSITY_COLORS = ["#dbe7fb", "#a9c6f3", "#6f9fe6", "#3f76cf", "#1f4fa3", "#13306a"];
const EMPTY_FILL = { clair: "#f8fafc", sombre: "#1e293b" };
// Aucun fond de tuiles externe : la carte se dessine avec les contours locaux (/geo/rdc-provinces.json). Les services de
// tuiles gratuits imposent des clés ou des quotas, révèlent à un tiers les zones consultées et tombent en panne hors
// ligne ; les noms et totaux des provinces sont déjà affichés par les pastilles de la carte.
const BG = { clair: "#e8edf4", sombre: "#0b1220" };
const MASK = { clair: { color: BG.clair, opacity: 1 }, sombre: { color: BG.sombre, opacity: 1 } };
// Fond OpenStreetMap OPTIONNEL (désactivé par défaut) : tuiles publiques sans clé, mais soumises à la politique d'usage
// d'OpenStreetMap (usage modéré) et vues par un tiers ; pour une exploitation intensive, héberger ses propres tuiles.
const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const MASK_WITH_TILES = 0.55;      // les pays voisins restent visibles sous le voile

export const densityColor = (n: number, max: number) =>
  n <= 0 || max <= 0 ? null
    : DENSITY_COLORS[Math.min(DENSITY_COLORS.length - 1, Math.floor((n / max) * DENSITY_COLORS.length))];

// Les identifiants viennent des opérateurs : tout ce qui part dans du HTML Leaflet est échappé.
const esc = (v: unknown) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

/** Point [lat, lng] dans un MultiPolygon GeoJSON ([lng, lat]) — lancer de rayon, trous compris. */
function inProvince(f: ProvinceFeature, [lat, lng]: [number, number]) {
  const inRing = (ring: Position[]) => {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if (yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  };
  return f.geometry.coordinates.some(([outer, ...holes]) => inRing(outer) && !holes.some(inRing));
}

const operatorLabel = (f: FraudPoint) => (f.channel === "VISA_VIRTUAL" ? "Visa virtuelle" : f.operator ?? "Mobile Money");
const statusLabel = (f: FraudPoint) => (f.label === 1 ? "Fraude confirmée" : f.action === "BLOCK" ? "Bloquée" : "À vérifier");

function fraudPopup(f: FraudPoint, capital: string) {
  const color = RISK_COLOR[f.risk_level] ?? "#64748b";
  return `<div class="fm-pop">
    <div class="fm-pop-head" style="--c:${color}">
      <span class="fm-pop-risk">${esc(RISK_LABEL[f.risk_level] ?? f.risk_level)}</span>
      <span class="fm-pop-status">${esc(statusLabel(f))}</span>
    </div>
    <div class="fm-pop-body">
      <div class="fm-pop-amount">${esc(fmtUsd(f.amount_usd))}</div>
      <div class="fm-pop-id">${esc(f.transaction_id)}</div>
      <dl>
        <dt>Probabilité</dt><dd>${esc(fmtPct(f.fraud_probability))}</dd>
        <dt>Lieu</dt><dd>${esc(f.province)} · ${esc(capital)}</dd>
        <dt>Client</dt><dd>${esc(f.user_id)}</dd>
        <dt>Opération</dt><dd>${esc(f.tx_type)} · ${esc(operatorLabel(f))}</dd>
        <dt>Date</dt><dd>${esc(fmtDate(f.tx_time))}</dd>
      </dl>
      <a class="fm-pop-link" href="/transactions/${encodeURIComponent(f.transaction_id)}">Ouvrir l'analyse →</a>
    </div>
  </div>`;
}

function provinceTooltip(name: string, s: ProvinceStat | undefined, total: number) {
  const capital = provinceGeo(name)?.capital ?? "";
  if (!s) return `<div class="fm-tip-title">${esc(name)}</div><div class="fm-tip-sub">Chef-lieu : ${esc(capital)}</div>
    <div class="fm-tip-empty">Aucune fraude sur la période</div>`;
  return `<div class="fm-tip-title">${esc(name)}</div><div class="fm-tip-sub">Chef-lieu : ${esc(capital)}</div>
    <div class="fm-tip-grid">
      <span>Fraudes</span><b>${fmtInt(s.frauds)}</b>
      <span>Part du total</span><b>${esc(fmtPct(total ? s.frauds / total : 0))}</b>
      <span>Bloquées</span><b>${fmtInt(s.blocked)}</b>
      <span>Montant</span><b>${esc(fmtUsd(s.amount_usd))}</b>
    </div>`;
}

type Ctx = {
  L: typeof Leaflet; map: Leaflet.Map;
  mask: Leaflet.GeoJSON | null; tiles: Leaflet.TileLayer | null;
  densityGroup: Leaflet.LayerGroup; badgeGroup: Leaflet.LayerGroup; pointGroup: Leaflet.LayerGroup;
  features: Map<string, ProvinceFeature>;                 // nom canonique (lib/geo) -> contour
  provinceLayers: Map<string, Leaflet.GeoJSON>;
  markers: Map<string, Leaflet.Layer>;                     // transaction_id -> point
};

export type FraudMapProps = {
  provinces: ProvinceStat[]; frauds: FraudPoint[];
  selected: string | null; hovered: string | null; focus: { id: string; n: number } | null;
  showDensity: boolean; showPoints: boolean; basemap: Basemap; showTiles?: boolean;
  onSelect: (province: string | null) => void; onHover: (province: string | null) => void;
};

export function FraudMap(props: FraudMapProps) {
  const { provinces, frauds, selected, hovered, focus, showDensity, showPoints, basemap, showTiles = false } = props;
  const el = useRef<HTMLDivElement>(null);
  const ctx = useRef<Ctx | null>(null);
  const cb = useRef(props);
  cb.current = props;
  const sig = useRef({ provinces: "", points: "" });
  const [ready, setReady] = useState(false);
  const [geoError, setGeoError] = useState(false);
  const canon = (p: string | null) => (p ? provinceGeo(p)?.name ?? p : null);

  // ------------------------------------------------------------------ création (navigateur uniquement)
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const L = (await import("leaflet")).default;
      const geo: FeatureCollection<MultiPolygon, { name: string; iso: string }> | null =
        await fetch("/geo/rdc-provinces.json").then((r) => (r.ok ? r.json() : null)).catch(() => null);
      if (cancelled || !el.current) return;
      if (!geo) setGeoError(true);

      const map = L.map(el.current, {
        preferCanvas: true, zoomControl: false, minZoom: 4, maxZoom: 12, zoomSnap: 0.25,
        maxBounds: [[-25, 0], [15, 45]], attributionControl: true,
      }).fitBounds(DRC_BOUNDS, { padding: [12, 12] });
      L.control.zoom({ position: "bottomright", zoomInTitle: "Zoom avant", zoomOutTitle: "Zoom arrière" }).addTo(map);
      L.control.scale({ imperial: false, position: "bottomright" }).addTo(map);
      map.attributionControl.setPrefix(false);

      map.attributionControl.addAttribution("provinces : geoBoundaries (ODbL)");
      el.current.style.background = BG[cb.current.basemap];
      // la carte suit les changements de taille du conteneur (barre latérale, fenêtre, panneau) : sans cela Leaflet
      // garde la taille mesurée au chargement et n'affiche qu'une partie du territoire
      const ro = new ResizeObserver(() => map.invalidateSize());
      ro.observe(el.current);
      (map as any)._ro = ro;

      const features = new Map<string, ProvinceFeature>();
      let mask: Leaflet.GeoJSON | null = null;
      if (geo) {
        for (const f of geo.features) features.set(provinceGeo(f.properties.name)?.name ?? f.properties.name, f);
        // Voile sur les pays voisins : le monde moins le territoire de la RDC
        const world: Position[] = [[-180, -90], [180, -90], [180, 90], [-180, 90], [-180, -90]];
        const holes = geo.features.flatMap((f) => f.geometry.coordinates.map((poly) => poly[0]));
        mask = L.geoJSON({ type: "Polygon", coordinates: [world, ...holes] } as any, { interactive: false }).addTo(map);
      }
      const densityGroup = L.layerGroup().addTo(map);
      const pointGroup = L.layerGroup().addTo(map);
      const badgeGroup = L.layerGroup().addTo(map);
      map.on("click", () => cb.current.onSelect(null));
      ctx.current = { L, map, mask, tiles: null, densityGroup, badgeGroup, pointGroup, features,
                      provinceLayers: new Map(), markers: new Map() };
      setReady(true);
    })();
    return () => {
      cancelled = true;
      (ctx.current?.map as any)?._ro?.disconnect();
      ctx.current?.map.remove();
      ctx.current = null;
    };
  }, []);

  // ------------------------------------------------------------------ fond de carte clair / sombre
  useEffect(() => {
    const c = ctx.current;
    if (!ready || !c) return;
    c.mask?.setStyle({ stroke: false, fillColor: MASK[basemap].color,
                       fillOpacity: showTiles ? MASK_WITH_TILES : MASK[basemap].opacity });
    el.current!.style.background = BG[basemap];
    sig.current.provinces = "";   // couleurs « aucune fraude » à recalculer
  }, [ready, basemap, showTiles]);

  // ------------------------------------------------------------------ fond OpenStreetMap (optionnel)
  useEffect(() => {
    const c = ctx.current;
    if (!ready || !c) return;
    if (showTiles && !c.tiles) {
      c.tiles = c.L.tileLayer(OSM_TILES, { attribution: OSM_ATTRIBUTION, maxZoom: 19, className: "fm-osm" }).addTo(c.map);
      c.tiles.bringToBack();
    } else if (!showTiles && c.tiles) {
      c.map.removeLayer(c.tiles);
      c.tiles = null;
    }
    c.map.getContainer().classList.toggle("fm-osm-dark", showTiles && basemap === "sombre");
  }, [ready, showTiles, basemap]);

  // ------------------------------------------------------------------ provinces (choroplèthe + étiquettes)
  useEffect(() => {
    const c = ctx.current;
    if (!ready || !c) return;
    const signature = JSON.stringify([basemap, provinces]);
    if (signature === sig.current.provinces) return;
    sig.current.provinces = signature;
    const { L, densityGroup, badgeGroup, features, provinceLayers } = c;
    densityGroup.clearLayers();
    badgeGroup.clearLayers();
    provinceLayers.clear();

    const stats = new Map(provinces.map((p) => [canon(p.province)!, p]));
    const max = Math.max(0, ...provinces.map((p) => p.frauds));
    const total = provinces.reduce((s, p) => s + p.frauds, 0);
    for (const [name, feature] of features) {
      const s = stats.get(name);
      const fill = densityColor(s?.frauds ?? 0, max) ?? EMPTY_FILL[basemap];
      const layer = L.geoJSON(feature, { style: { fillColor: fill, fillOpacity: s ? 0.78 : 0.55 } })
        .bindTooltip(provinceTooltip(name, s, total), { sticky: true, className: "fm-tip", direction: "top", offset: [0, -8] })
        .on("mouseover", () => cb.current.onHover(name))
        .on("mouseout", () => cb.current.onHover(null))
        .on("click", (e) => {
          L.DomEvent.stopPropagation(e);
          cb.current.onSelect(canon(cb.current.selected) === name ? null : (s?.province ?? name));
        })
        .addTo(densityGroup);
      provinceLayers.set(name, layer);
      if (s) {
        L.marker(layer.getBounds().getCenter(), {
          interactive: false, keyboard: false,
          icon: L.divIcon({
            className: "", iconSize: [0, 0],
            html: `<div class="fm-badge"><span>${esc(name)}</span><b>${fmtInt(s.frauds)}</b></div>`,
          }),
        }).addTo(badgeGroup);
      }
    }
    styleProvinces();
    sig.current.points = "";   // les points doivent être redessinés au-dessus des provinces
    drawPoints();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, provinces, basemap]);

  // ------------------------------------------------------------------ points de fraude
  function drawPoints() {
    const c = ctx.current;
    if (!c) return;
    const list = cb.current.frauds;
    const signature = JSON.stringify(list.map((f) => [f.transaction_id, f.label]));
    if (signature === sig.current.points) return;
    sig.current.points = signature;
    const { L, pointGroup, features, markers } = c;
    pointGroup.clearLayers();
    markers.clear();
    const now = Date.now();
    let pulses = 0;
    for (const f of list) {   // les plus récentes d'abord
      const geo = provinceGeo(f.province);
      if (!geo) continue;
      // Autour du chef-lieu, en restant dans la province (Goma, Bukavu… sont sur une frontière)
      const shape = features.get(geo.name);
      let pos: [number, number] = [geo.lat, geo.lng];
      for (let k = 0; k < 8; k++) {
        const p = fraudPosition(geo, `${f.transaction_id}#${k}`, geo.name === "Kinshasa" ? 0.12 : 0.3);
        if (!shape || inProvince(shape, p)) { pos = p; break; }
      }
      const color = RISK_COLOR[f.risk_level] ?? "#64748b";
      const recent = pulses < 6 && now - new Date(f.scored_at).getTime() < 3 * 60_000;
      const marker = recent
        ? L.marker(pos, { icon: L.divIcon({ className: "", iconSize: [0, 0], html: `<div class="fm-pulse" style="--c:${color}"><i></i></div>` }) })
        : L.circleMarker(pos, {
            radius: 6, color: f.label === 1 ? "#0f172a" : "#ffffff", weight: f.label === 1 ? 2.2 : 1.4,
            fillColor: color, fillOpacity: 0.95,
          });
      if (recent) pulses++;
      marker.bindPopup(fraudPopup(f, geo.capital), { className: "fm-popup", maxWidth: 300, autoPanPadding: [40, 40] })
        .on("click", (e: Leaflet.LeafletEvent) => L.DomEvent.stopPropagation(e as any))
        .addTo(pointGroup);
      markers.set(f.transaction_id, marker);
    }
  }
  useEffect(() => { if (ready) drawPoints(); }, [ready, frauds]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------ survol / sélection (sans redessiner)
  function styleProvinces() {
    const c = ctx.current;
    if (!c) return;
    const sel = canon(cb.current.selected), hov = cb.current.hovered;
    const dark = cb.current.basemap === "sombre";
    for (const [name, layer] of c.provinceLayers) {
      const isSel = name === sel, isHov = name === hov;
      layer.setStyle({
        color: isSel ? (dark ? "#f8fafc" : "#0f172a") : isHov ? (dark ? "#cbd5e1" : "#1e293b") : (dark ? "#334155" : "#ffffff"),
        weight: isSel ? 2.6 : isHov ? 2 : 1.2, opacity: 1,
      });
    }
  }
  useEffect(() => { if (ready) styleProvinces(); }, [ready, selected, hovered]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------ couches visibles
  useEffect(() => {
    const c = ctx.current;
    if (!ready || !c) return;
    const toggle = (layer: Leaflet.Layer, on: boolean) => (on ? c.map.addLayer(layer) : c.map.removeLayer(layer));
    toggle(c.densityGroup, showDensity);
    toggle(c.badgeGroup, showDensity);
    toggle(c.pointGroup, showPoints);
  }, [ready, showDensity, showPoints]);

  // ------------------------------------------------------------------ zoom sur la province choisie
  useEffect(() => {
    const c = ctx.current;
    if (!ready || !c) return;
    const shape = c.features.get(canon(selected) ?? "");
    if (shape) c.map.flyToBounds(c.L.geoJSON(shape).getBounds(), { padding: [48, 48], duration: 0.7 });
    else c.map.flyToBounds(DRC_BOUNDS, { padding: [12, 12], duration: 0.7 });
  }, [ready, selected]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------ « voir sur la carte » depuis le flux
  useEffect(() => {
    const c = ctx.current;
    if (!ready || !c || !focus) return;
    const m = c.markers.get(focus.id) as (Leaflet.Marker | Leaflet.CircleMarker) | undefined;
    if (!m) return;
    c.map.flyTo(m.getLatLng(), Math.max(c.map.getZoom(), 8), { duration: 0.7 });
    c.map.once("moveend", () => m.openPopup());
  }, [ready, focus]);

  return (
    <div className="fm-map relative h-full w-full">
      <div ref={el} className="h-full w-full" style={{ background: "#e2e8f0" }} aria-label="Carte des fraudes en RD Congo" />
      {geoError && (
        <div className="absolute bottom-3 left-1/2 z-[500] -translate-x-1/2 rounded-md bg-white/95 px-3 py-1.5 text-xs text-risk-critique shadow">
          Contours des provinces indisponibles (/geo/rdc-provinces.json)
        </div>
      )}
    </div>
  );
}
