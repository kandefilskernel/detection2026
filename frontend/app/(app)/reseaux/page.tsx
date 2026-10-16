"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Crosshair, FlaskConical, Network, Search, Share2, Users, Waypoints } from "lucide-react";
import { LiveDot, PageHeader } from "@/components/app-shell";
import { KIND_LETTER, type NetEdge, type NetNode, NetworkGraph, scoreColor } from "@/components/network-graph";
import { Pill } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@/components/ui/card";
import { Input, Segmented } from "@/components/ui/select";
import { Stat } from "@/components/ui/stat";
import { usePolling } from "@/lib/use-polling";
import { cn, fmtInt, fmtPct, fmtUsd } from "@/lib/utils";

type Ring = {
  id: string; score: number; n_accounts: number; n_entities: number; entity_kinds: Record<string, number>;
  n_tx: number; expected_frauds: number; amount_usd: number; top_entities: string[]; top_accounts: string[];
};
type TopEntity = { id: string; kind: string; kind_label: string; raw_id: string; score: number; direct: number; propagated: number; n_accounts: number };
type Overview = {
  window_minutes: number; n_tx: number; truncated: boolean; n_accounts: number; n_entities: number; n_edges: number;
  n_shared_entities: number; n_rings: number; accounts_in_rings: number; rings: Ring[]; top_entities: TopEntity[];
};
type Ego = { center: string; nodes: NetNode[]; edges: NetEdge[]; truncated: boolean };
type Window = "60" | "1440" | "10080" | "43200";
const WINDOWS: [Window, string][] = [["60", "1 h"], ["1440", "24 h"], ["10080", "7 j"], ["43200", "30 j"]];
const KIND_NAME: Record<string, string> = { U: "Compte", W: "Portefeuille", D: "Appareil", A: "Agent", M: "Marchand" };
const raw = (id: string) => id.slice(2);

function ScoreBar({ value }: { value: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-16 rounded-full bg-muted"><span className="block h-1.5 rounded-full" style={{ width: `${Math.max(4, value * 100)}%`, background: scoreColor(value) }} /></span>
      <span className="tabular text-xs font-semibold">{Math.round(value * 100)} %</span>
    </span>
  );
}

export default function ReseauxPage() {
  const [minutes, setMinutes] = useState<Window>("1440");
  const [tab, setTab] = useState<"rings" | "entities">("rings");
  const [center, setCenter] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  // Lien depuis une transaction : /reseaux?node=U:U000123
  useEffect(() => { const n = new URLSearchParams(window.location.search).get("node"); if (n) { setCenter(n); setQuery(raw(n)); } }, []);

  const { data, error } = usePolling<Overview>(`/network/overview?minutes=${minutes}`, 15000);
  const focus = center ?? data?.rings[0]?.id ?? data?.top_entities[0]?.id ?? null;
  const ego = usePolling<Ego>(focus ? `/network/ego?node=${encodeURIComponent(focus)}&minutes=${minutes}` : null, 15000);
  const { data: evaluation } = usePolling<any>("/network/evaluation", 0);
  useEffect(() => setSelected(null), [focus]);

  const nodes = ego.data?.nodes ?? [];
  const sel = nodes.find((n) => n.id === (selected ?? focus));
  const search = (e: React.FormEvent) => { e.preventDefault(); if (query.trim()) setCenter(query.trim()); };
  const evalTx = evaluation?.etiquettes_differees?.transactions;

  return (
    <>
      <PageHeader eyebrow="Investigation" title="Réseaux de fraude"
        subtitle="Comptes reliés par les mêmes portefeuilles, appareils, agents ou marchands à risque : mules, appareils de fraudeurs réutilisés, agents compromis.">
        <LiveDot error={error} />
        <Segmented value={minutes} onChange={setMinutes} options={WINDOWS} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Réseaux détectés" icon={<Waypoints />} tone="danger" value={data ? fmtInt(data.n_rings) : undefined}
          hint={data && `${fmtInt(data.accounts_in_rings)} comptes impliqués`} />
        <Stat label="Entités partagées" icon={<Share2 />} tone="warn" value={data ? fmtInt(data.n_shared_entities) : undefined}
          hint={data && `sur ${fmtInt(data.n_entities)} entités observées`} />
        <Stat label="Comptes analysés" icon={<Users />} value={data ? fmtInt(data.n_accounts) : undefined}
          hint={data && `${fmtInt(data.n_edges)} liens compte–entité`} />
        <Stat label="Transactions" icon={<Network />} tone="accent" value={data ? fmtInt(data.n_tx) : undefined}
          hint={data?.truncated ? "fenêtre tronquée aux plus récentes" : "dans la fenêtre"} />
      </div>

      <Card className="overflow-hidden">
        <div className="grid lg:grid-cols-[360px_minmax(0,1fr)]">
          {/* ------------------------------------------------------------ liste */}
          <aside className="flex min-h-0 flex-col border-b lg:h-[640px] lg:border-b-0 lg:border-r">
            <div className="flex gap-1 border-b p-2">
              {([["rings", "Réseaux", Waypoints], ["entities", "Entités à risque", Share2]] as const).map(([k, l, Icon]) => (
                <button key={k} onClick={() => setTab(k)}
                  className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-colors",
                    tab === k ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground")}>
                  <Icon className="h-3.5 w-3.5" />{l}
                </button>
              ))}
            </div>
            <div className="max-h-[420px] min-h-0 flex-1 overflow-y-auto lg:max-h-none">
              {tab === "rings" ? (
                <ul className="divide-y">
                  {data?.rings.map((r) => (
                    <li key={r.id}>
                      <button onClick={() => setCenter(r.id)}
                        className={cn("relative w-full px-4 py-3 text-left transition-colors hover:bg-muted/60", focus === r.id && "bg-primary/[.06]")}>
                        <span className="absolute inset-y-2 left-0 w-[3px] rounded-r-full" style={{ background: scoreColor(r.score) }} />
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="text-sm font-semibold">{fmtInt(r.n_accounts)} comptes · {fmtInt(r.n_entities)} entités</span>
                          <ScoreBar value={r.score} />
                        </div>
                        <div className="mt-1 truncate text-xs text-muted-foreground">
                          Pivot : {KIND_NAME[r.id[0]]} <span className="font-mono text-foreground">{raw(r.id)}</span>
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                          {Object.entries(r.entity_kinds).map(([k, v]) => <Pill key={k} dot={false}>{v} {k}{v > 1 ? "s" : ""}</Pill>)}
                          <span className="tabular ml-auto">{fmtUsd(r.amount_usd)} · ≈ {r.expected_frauds.toLocaleString("fr-FR")} fraudes</span>
                        </div>
                      </button>
                    </li>
                  ))}
                  {data && data.rings.length === 0 && <EmptyState icon={<Waypoints />} title="Aucun réseau">Aucune entité à risque n&apos;est partagée par plusieurs comptes sur cette période.</EmptyState>}
                </ul>
              ) : (
                <ul className="divide-y">
                  {data?.top_entities.map((e) => (
                    <li key={e.id}>
                      <button onClick={() => setCenter(e.id)}
                        className={cn("w-full px-4 py-3 text-left transition-colors hover:bg-muted/60", focus === e.id && "bg-primary/[.06]")}>
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="truncate text-sm"><span className="text-muted-foreground">{e.kind_label} </span><span className="font-mono">{e.raw_id}</span></span>
                          <ScoreBar value={e.score} />
                        </div>
                        <div className="tabular mt-1 text-[11px] text-muted-foreground">
                          {fmtInt(e.n_accounts)} comptes · direct {Math.round(e.direct * 100)} % · propagé {Math.round(e.propagated * 100)} %
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </aside>

          {/* ------------------------------------------------------------ graphe */}
          <div className="relative flex min-h-0 flex-col lg:h-[640px]">
            <form onSubmit={search} className="flex items-center gap-2 border-b p-2">
              <Search className="ml-2 h-4 w-4 shrink-0 text-muted-foreground" />
              <Input value={query} onChange={(e) => setQuery(e.target.value)} className="h-9 border-0 shadow-none focus-visible:ring-0"
                placeholder="Compte, portefeuille, appareil, agent ou marchand (ex. U000123, 2437…)" aria-label="Rechercher un nœud" />
              <button type="submit" className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90">Centrer</button>
            </form>
            <div className="relative h-[460px] min-h-0 flex-1 lg:h-auto">
              {ego.error ? (
                <EmptyState icon={<Crosshair />} title="Nœud introuvable">{ego.error}</EmptyState>
              ) : nodes.length ? (
                <NetworkGraph nodes={nodes} edges={ego.data!.edges} center={ego.data!.center} selected={selected} onSelect={setSelected} />
              ) : (
                <EmptyState icon={<Network />} title={data ? "Rien à afficher" : "Chargement…"}>Choisissez un réseau ou recherchez un identifiant.</EmptyState>
              )}

              <div className="absolute bottom-3 left-3 rounded-xl border bg-elevated/90 p-3 text-[11px] shadow-float backdrop-blur-md">
                <div className="mb-1.5 font-semibold">Légende</div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                  <span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded-full bg-muted-foreground" />Compte client</span>
                  <span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded-[3px] bg-muted-foreground" />Entité</span>
                  {Object.entries(KIND_LETTER).filter(([k]) => k !== "U").map(([k, l]) => <span key={k}><b>{l}</b> {KIND_NAME[k]}</span>)}
                </div>
                <div className="mt-2 flex items-center gap-1.5">
                  {[0.05, 0.2, 0.5, 0.8].map((v) => <span key={v} className="h-2 w-6 rounded" style={{ background: scoreColor(v) }} />)}
                  <span className="text-muted-foreground">risque réseau</span>
                </div>
              </div>

              {sel && (
                <div className="absolute right-3 top-3 w-64 animate-fade-up rounded-xl border bg-elevated/95 p-4 shadow-float backdrop-blur-md">
                  <div className="text-[10px] font-semibold uppercase tracking-[.14em] text-primary">{sel.kind_label}</div>
                  <div className="break-all font-mono text-sm font-semibold">{sel.raw_id}</div>
                  <div className="mt-3 space-y-1.5 text-xs">
                    <div className="flex justify-between"><span className="text-muted-foreground">{sel.kind === "U" ? "Exposition" : "Risque réseau"}</span><ScoreBar value={sel.score} /></div>
                    {sel.direct != null && <div className="flex justify-between"><span className="text-muted-foreground">Risque direct</span><span className="tabular font-medium">{Math.round(sel.direct * 100)} %</span></div>}
                    <div className="flex justify-between"><span className="text-muted-foreground">{sel.kind === "U" ? "Entités liées" : "Comptes liés"}</span><span className="tabular font-medium">{fmtInt(sel.degree)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Transactions</span><span className="tabular font-medium">{fmtInt(sel.n_tx)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Fraudes estimées</span><span className="tabular font-medium">{sel.expected_frauds.toLocaleString("fr-FR")}</span></div>
                  </div>
                  <div className="mt-3 flex gap-2">
                    {sel.id !== ego.data?.center && (
                      <button onClick={() => { setCenter(sel.id); setQuery(sel.raw_id); }} className="flex flex-1 items-center justify-center gap-1 rounded-lg border py-1.5 text-xs font-medium hover:bg-muted">
                        <Crosshair className="h-3.5 w-3.5" /> Centrer
                      </button>
                    )}
                    {sel.kind === "U" && (
                      <Link href={`/transactions?search=${encodeURIComponent(sel.raw_id)}`} className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-primary py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90">
                        Transactions <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    )}
                  </div>
                </div>
              )}
            </div>
            {ego.data?.truncated && <div className="border-t px-4 py-2 text-[11px] text-muted-foreground">Voisinage tronqué : seuls les voisins les plus risqués sont affichés.</div>}
          </div>
        </div>
      </Card>

      {evalTx && (
        <Card className="mt-4">
          <CardHeader>
            <div><CardTitle className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-primary" />Apport mesuré hors ligne</CardTitle>
              <CardDescription>Rejeu chronologique de la période de test, verdicts révélés après {evaluation.label_delay_days} jours (données simulées).</CardDescription></div>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-3">
            {[
              ["Rappel du modèle seul", fmtPct(evalTx.model_alone.recall), `${fmtPct(evalTx.model_alone.false_alert_rate, 2)} de fausses alertes`],
              ["Modèle OU réseau", fmtPct(evalTx.model_or_network.recall), `${fmtPct(evalTx.model_or_network.false_alert_rate, 2)} de fausses alertes`],
              ["Fraudes rattrapées", fmtInt(evalTx.frauds_rescued), `dont ${fmtInt(evalTx.by_fraud_type?.SOCIAL_ENGINEERING?.rescued ?? 0)} d'ingénierie sociale`],
            ].map(([k, v, h]) => (
              <div key={k} className="rounded-xl bg-muted/60 p-3">
                <div className="text-xs text-muted-foreground">{k}</div>
                <div className="tabular mt-1 text-xl font-semibold">{v}</div>
                <div className="text-[11px] text-muted-foreground">{h}</div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </>
  );
}
