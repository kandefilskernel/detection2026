"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Ban, Banknote, Crosshair, Flame, Layers, MapPinned, Moon, Radio, ShieldAlert, Sun, X } from "lucide-react";
import { LiveDot, PageHeader } from "@/components/app-shell";
import {
  type Basemap, DENSITY_COLORS, FraudMap, type FraudPoint, type ProvinceStat, RISK_COLOR,
} from "@/components/fraud-map";
import { RiskBadge } from "@/components/ui/badge";
import { Card, EmptyState } from "@/components/ui/card";
import { Segmented } from "@/components/ui/select";
import { Stat } from "@/components/ui/stat";
import { provinceGeo } from "@/lib/geo";
import { useTheme } from "@/lib/theme";
import { usePolling } from "@/lib/use-polling";
import { cn, FRAUD_TYPE_LABEL, fmtInt, fmtPct, fmtUsd, RISK_LABEL } from "@/lib/utils";

type FraudMapData = { window_minutes: number; total: number; truncated: boolean; provinces: ProvinceStat[]; frauds: FraudPoint[] };
type Window = "60" | "1440" | "10080" | "43200";
const WINDOWS: [Window, string][] = [["60", "1 h"], ["1440", "24 h"], ["10080", "7 j"], ["43200", "30 j"]];
const EMPTY_P: ProvinceStat[] = [];
const EMPTY_F: FraudPoint[] = [];

function timeAgo(iso: string) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "à l'instant";
  if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
  return `il y a ${Math.floor(s / 86400)} j`;
}

/** Bouton bascule flottant sur la carte. */
function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" aria-pressed={on} onClick={onClick}
      className={cn("inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-all [&_svg]:h-3.5 [&_svg]:w-3.5",
        on ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
      {children}
    </button>
  );
}
const FLOAT = "rounded-xl border bg-elevated/90 shadow-float backdrop-blur-md";

export default function CartePage() {
  const { theme } = useTheme();
  const [minutes, setMinutes] = useState<Window>("1440");
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ id: string; n: number } | null>(null);
  const [tab, setTab] = useState<"provinces" | "flux">("provinces");
  const [showDensity, setShowDensity] = useState(true);
  const [showPoints, setShowPoints] = useState(true);
  const [showTiles, setShowTiles] = useState(false);
  useEffect(() => { try { setShowTiles(localStorage.getItem("fraud-rdc-osm") === "1"); } catch { /* navigation privée */ } }, []);
  const toggleTiles = () => { const v = !showTiles; setShowTiles(v); try { localStorage.setItem("fraud-rdc-osm", v ? "1" : "0"); } catch { /* navigation privée */ } };
  const [basemap, setBasemap] = useState<Basemap>("clair");
  useEffect(() => setBasemap(theme === "dark" ? "sombre" : "clair"), [theme]);
  // Lien depuis une transaction ou le tableau de bord : /carte?province=Nord-Kivu
  useEffect(() => { setSelected(new URLSearchParams(window.location.search).get("province")); }, []);

  const { data, error } = usePolling<FraudMapData>(`/reports/fraud-map?minutes=${minutes}&limit=2000`, 10000);
  const provinces = data?.provinces ?? EMPTY_P;
  const frauds = data?.frauds ?? EMPTY_F;

  const s = useMemo(() => {
    const located = provinces.filter((p) => provinceGeo(p.province));
    const blocked = provinces.reduce((a, p) => a + p.blocked, 0);
    const confirmed = provinces.reduce((a, p) => a + p.confirmed, 0);
    const amount = provinces.reduce((a, p) => a + p.amount_usd, 0);
    const unlocated = provinces.filter((p) => !provinceGeo(p.province)).reduce((a, p) => a + p.frauds, 0);
    return { located, blocked, confirmed, amount, unlocated, max: Math.max(1, ...provinces.map((p) => p.frauds)) };
  }, [provinces]);
  const total = data?.total ?? 0;
  const top = provinces[0];
  const sel = selected ? provinces.find((p) => p.province === selected) : undefined;
  const feed = selected ? frauds.filter((f) => f.province === selected) : frauds;

  return (
    <>
      <PageHeader eyebrow="Supervision géographique" title="Carte des fraudes — RD Congo"
        subtitle="Alertes à vérifier, transactions bloquées et fraudes confirmées dans les 26 provinces.">
        <LiveDot error={error} />
        <Segmented value={minutes} onChange={setMinutes} options={WINDOWS} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Fraudes détectées" icon={<ShieldAlert />} tone="danger" value={data ? fmtInt(total) : undefined}
          hint={data && `${fmtInt(s.blocked)} bloquées · ${fmtInt(total - s.blocked)} à vérifier · ${fmtInt(s.confirmed)} confirmées`} />
        <Stat label="Montant exposé" icon={<Banknote />} tone="warn" value={data ? fmtUsd(s.amount) : undefined}
          hint={data && total ? `${fmtUsd(s.amount / total)} en moyenne par fraude` : "—"} />
        <Stat label="Provinces touchées" icon={<MapPinned />} value={data ? <>{fmtInt(s.located.length)}<span className="text-base font-medium text-muted-foreground"> / 26</span></> : undefined}>
          <div className="mt-3 h-1.5 rounded-full bg-muted">
            <div className="h-1.5 rounded-full bg-gradient-to-r from-primary to-accent transition-all" style={{ width: `${(s.located.length / 26) * 100}%` }} />
          </div>
        </Stat>
        <Stat label="Foyer principal" icon={<Flame />} tone="accent" value={data ? top?.province ?? "—" : undefined}
          hint={top && `${fmtInt(top.frauds)} fraudes · ${fmtPct(total ? top.frauds / total : 0)} du total`} />
      </div>

      <Card className="overflow-hidden">
        <div className="grid lg:grid-cols-[minmax(0,1fr)_380px]">
          {/* ------------------------------------------------------------ carte */}
          <div className="relative h-[520px] lg:h-[calc(100vh-300px)] lg:min-h-[600px]">
            <FraudMap provinces={provinces} frauds={frauds} selected={selected} hovered={hovered} focus={focus}
              showDensity={showDensity} showPoints={showPoints} basemap={basemap} showTiles={showTiles} onSelect={setSelected} onHover={setHovered} />

            <div className={cn("absolute left-3 top-3 z-[500] flex flex-wrap items-center gap-1 p-1", FLOAT)}>
              <span className="px-1.5 text-muted-foreground"><Layers className="h-3.5 w-3.5" /></span>
              <Toggle on={showDensity} onClick={() => setShowDensity(!showDensity)}>Densité</Toggle>
              <Toggle on={showPoints} onClick={() => setShowPoints(!showPoints)}>Fraudes</Toggle>
              <Toggle on={showTiles} onClick={toggleTiles}>Fond OSM</Toggle>
              <span className="mx-1 h-4 w-px bg-border" />
              <Toggle on={basemap === "clair"} onClick={() => setBasemap("clair")}><Sun /> Clair</Toggle>
              <Toggle on={basemap === "sombre"} onClick={() => setBasemap("sombre")}><Moon /> Sombre</Toggle>
            </div>

            {selected && (
              <div className={cn("absolute right-3 top-3 z-[500] w-64 animate-fade-up p-4", FLOAT)}>
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[.14em] text-primary">Province</div>
                    <div className="text-lg font-semibold leading-tight">{selected}</div>
                    <div className="text-xs text-muted-foreground">Chef-lieu : {provinceGeo(selected)?.capital ?? "—"}</div>
                  </div>
                  <button onClick={() => setSelected(null)} aria-label="Retour à la RDC entière" className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><X className="h-4 w-4" /></button>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  {[["Fraudes", fmtInt(sel?.frauds ?? 0)], ["Bloquées", fmtInt(sel?.blocked ?? 0)], ["Confirmées", fmtInt(sel?.confirmed ?? 0)]].map(([k, v]) => (
                    <div key={k} className="rounded-lg bg-muted/70 py-2"><div className="tabular text-base font-semibold">{v}</div><div className="text-[10px] text-muted-foreground">{k}</div></div>
                  ))}
                </div>
                <div className="mt-2 flex justify-between text-xs"><span className="text-muted-foreground">Montant</span><span className="tabular font-semibold">{fmtUsd(sel?.amount_usd ?? 0)}</span></div>
                <button onClick={() => setSelected(null)} className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border py-1.5 text-xs font-medium hover:bg-muted">
                  <Crosshair className="h-3.5 w-3.5" /> Toute la RDC
                </button>
              </div>
            )}

            <div className={cn("absolute bottom-3 left-3 z-[500] w-56 p-3 text-[11px]", FLOAT)}>
              <div className="mb-1.5 font-semibold">Fraudes par province</div>
              <div className="flex overflow-hidden rounded">{DENSITY_COLORS.map((c) => <span key={c} className="h-2 flex-1" style={{ background: c }} />)}</div>
              <div className="tabular mt-1 flex justify-between text-muted-foreground"><span>1</span><span>{fmtInt(s.max)}</span></div>
              <div className="mb-1.5 mt-2.5 font-semibold">Niveau de risque</div>
              <div className="grid grid-cols-2 gap-x-2 gap-y-1">
                {["CRITIQUE", "ELEVE", "MOYEN", "FAIBLE"].map((l) => (
                  <span key={l} className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full ring-2 ring-white/80" style={{ background: RISK_COLOR[l] }} />{RISK_LABEL[l]}</span>
                ))}
                <span className="col-span-2 inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full border-2 border-slate-900 bg-risk-critique" />Fraude confirmée</span>
              </div>
            </div>
          </div>

          {/* ------------------------------------------------------------ panneau latéral */}
          <aside className="flex min-h-0 flex-col border-t lg:h-[calc(100vh-300px)] lg:min-h-[600px] lg:border-l lg:border-t-0">
            <div className="flex gap-1 border-b p-2">
              {([["provinces", "Classement", MapPinned], ["flux", "Flux en direct", Radio]] as const).map(([k, l, Icon]) => (
                <button key={k} onClick={() => setTab(k)}
                  className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-colors",
                    tab === k ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground")}>
                  <Icon className="h-3.5 w-3.5" />{l}
                  {k === "flux" && <span className="tabular rounded-full bg-risk-critique/10 px-1.5 text-[10px] text-risk-critique">{fmtInt(feed.length)}</span>}
                </button>
              ))}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto">
              {tab === "provinces" ? (
                <ol className="p-2">
                  {provinces.map((p, i) => (
                    <li key={p.province}>
                      <button onClick={() => setSelected(selected === p.province ? null : p.province)}
                        onMouseEnter={() => setHovered(provinceGeo(p.province)?.name ?? p.province)} onMouseLeave={() => setHovered(null)}
                        className={cn("w-full rounded-lg px-3 py-2.5 text-left transition-colors",
                          selected === p.province ? "bg-primary/[.08] ring-1 ring-primary/30" : "hover:bg-muted/70")}>
                        <div className="flex items-center gap-3">
                          <span className={cn("tabular grid h-6 w-6 shrink-0 place-items-center rounded-md text-[11px] font-semibold",
                            i < 3 ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground")}>{i + 1}</span>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-baseline justify-between gap-2">
                              <span className="truncate text-sm font-medium">{p.province}</span>
                              <span className="tabular text-sm font-semibold">{fmtInt(p.frauds)}</span>
                            </div>
                            <div className="mt-0.5 flex justify-between text-[11px] text-muted-foreground">
                              <span>{provinceGeo(p.province)?.capital ?? "non localisée"}</span>
                              <span className="tabular">{fmtUsd(p.amount_usd)}</span>
                            </div>
                            <div className="mt-1.5 h-1 rounded-full bg-muted">
                              <div className="h-1 rounded-full bg-gradient-to-r from-primary to-accent" style={{ width: `${(p.frauds / s.max) * 100}%` }} />
                            </div>
                          </div>
                        </div>
                      </button>
                    </li>
                  ))}
                  {data && provinces.length === 0 && <EmptyState icon={<MapPinned />} title="Aucune fraude">Rien à signaler sur cette période.</EmptyState>}
                </ol>
              ) : (
                <ul className="divide-y">
                  {feed.slice(0, 150).map((f) => (
                    <li key={f.transaction_id}>
                      <button onClick={() => { setShowPoints(true); setFocus({ id: f.transaction_id, n: Date.now() }); }}
                        className="group relative flex w-full gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/60">
                        <span className="absolute inset-y-2 left-0 w-[3px] rounded-r-full" style={{ background: RISK_COLOR[f.risk_level] }} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-baseline justify-between gap-2">
                            <span className="tabular text-sm font-semibold">{fmtUsd(f.amount_usd)}</span>
                            <span className="shrink-0 text-[11px] text-muted-foreground">{timeAgo(f.scored_at)}</span>
                          </div>
                          <div className="mt-0.5 truncate text-xs text-muted-foreground">
                            {f.fraud_type ? `${FRAUD_TYPE_LABEL[f.fraud_type] ?? f.fraud_type} · ` : ""}{f.tx_type} · {f.channel === "VISA_VIRTUAL" ? "Visa" : f.operator} · <span className="text-foreground">{f.province}</span>
                          </div>
                          <div className="mt-1.5 flex items-center justify-between gap-2">
                            <span className="truncate font-mono text-[10px] text-muted-foreground">{f.transaction_id}</span>
                            <span className="flex shrink-0 items-center gap-1.5">
                              {f.action === "BLOCK" && <Ban className="h-3 w-3 text-risk-critique" />}
                              <RiskBadge level={f.risk_level} />
                            </span>
                          </div>
                        </div>
                      </button>
                    </li>
                  ))}
                  {data && feed.length === 0 && <EmptyState icon={<Radio />} title="Aucune fraude">Le flux s&apos;alimente en temps réel.</EmptyState>}
                </ul>
              )}
            </div>
            {tab === "flux" && feed.length > 0 && (
              <div className="border-t px-4 py-2 text-[11px] text-muted-foreground">Cliquez sur une fraude pour la localiser · <Link href="/alertes" className="text-primary hover:underline">dossiers</Link></div>
            )}
          </aside>
        </div>
      </Card>

      <p className="mt-3 text-xs text-muted-foreground">
        Position approximative : les opérateurs transmettent la province, pas de coordonnées GPS ; chaque fraude est placée autour du chef-lieu, à l&apos;intérieur de sa province.
        {data?.truncated && ` Seules les ${fmtInt(frauds.length)} fraudes les plus récentes sont dessinées individuellement.`}
        {s.unlocated > 0 && ` ${fmtInt(s.unlocated)} fraude(s) avec une province non reconnue ne sont pas sur la carte.`}
        {" "}Contours : geoBoundaries (ODbL).
      </p>
    </>
  );
}
