"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Clock, Crosshair, Dice5, Gauge, Network, ScanSearch, Sparkles, Target } from "lucide-react";
import { LiveDot, PageHeader } from "@/components/app-shell";
import { REVIEW_REASON_LABEL } from "@/components/review-panel";
import { RiskBadge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@/components/ui/card";
import { Segmented } from "@/components/ui/select";
import { Stat } from "@/components/ui/stat";
import { usePolling } from "@/lib/use-polling";
import { cn, fmtInt, fmtPct, fmtUsd, RISK_LABEL } from "@/lib/utils";

type Rate = { k: number; n: number; rate: number | null; low: number | null; high: number | null };
type QueueItem = {
  transaction_id: string; scored_at: string; user_id: string; channel: string; operator: string | null; tx_type: string;
  province: string; amount_usd: number; fraud_probability: number; risk_level: string; why: string;
};
type Queue = { threshold: number; days: number; reasons: Record<string, QueueItem[]> };
type Quality = {
  days: number; threshold: number; n_tx: number; alerts: number; alerts_reviewed: number; approved: number;
  alert_precision: Rate; control_sample: Rate; complaints: number;
  estimate: { missed_frauds: number; missed_frauds_ci: [number, number]; caught_frauds: number; recall: number | null; recall_ci: [number | null, number | null] } | null;
  labels_by_reason: { reason: string; n: number; frauds: number; fraud_rate: number | null }[];
  precision_by_risk: ({ risk_level: string } & Rate)[];
  calibration: { bin: number; n: number; predicted: number; observed: number }[];
  open_cases: number; median_hours_to_verdict: number | null;
};
type Days = "7" | "30" | "90";
const DAYS: [Days, string][] = [["7", "7 j"], ["30", "30 j"], ["90", "90 j"]];
const REASONS = [
  { key: "INCERTITUDE", label: "Incertitude", icon: Target, help: "Le modèle a hésité : leurs verdicts déplacent la frontière de décision (apprentissage actif)." },
  { key: "NOUVEAUTE", label: "Nouveauté", icon: Sparkles, help: "Comportements jamais vus par l'autoencodeur : de nouvelles typologies possibles." },
  { key: "RESEAU", label: "Réseau", icon: Network, help: "Approuvées mais liées à une entité à risque (mule, appareil de fraudeur, agent)." },
  { key: "TEMOIN", label: "Témoin", icon: Dice5, help: "Tirage aléatoire du jour : seule mesure sans biais des fraudes que le modèle laisse passer." },
] as const;
const RISK_ORDER = ["CRITIQUE", "ELEVE", "MOYEN", "FAIBLE"];

const ci = (r: { low: number | null; high: number | null }) => r.low == null || r.high == null ? "" : `IC 95 % : ${fmtPct(r.low)} – ${fmtPct(r.high)}`;

export default function RevuePage() {
  const [days, setDays] = useState<Days>("30");
  const [tab, setTab] = useState<(typeof REASONS)[number]["key"]>("INCERTITUDE");
  const q = usePolling<Quality>(`/feedback/quality?days=${days}`, 30000);
  const queue = usePolling<Queue>(`/feedback/queue?days=${Math.min(+days, 30)}&per_reason=15`, 60000);
  const d = q.data;
  const items = queue.data?.reasons[tab] ?? [];
  const current = REASONS.find((r) => r.key === tab)!;
  const maxReason = Math.max(1, ...(d?.labels_by_reason.map((r) => r.n) ?? []));

  return (
    <>
      <PageHeader eyebrow="Boucle de retour" title="Revue & qualité du modèle"
        subtitle="Ce que valent réellement les alertes d'après les verdicts, ce que le modèle laisse passer, et les transactions dont la revue lui apprend le plus.">
        <LiveDot error={q.error} />
        <Segmented value={days} onChange={setDays} options={DAYS} />
      </PageHeader>

      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Précision réelle des alertes" icon={<Crosshair />} tone="success"
          value={d ? (d.alert_precision.rate == null ? "—" : fmtPct(d.alert_precision.rate)) : undefined}
          hint={d && (d.alert_precision.n ? `${fmtInt(d.alert_precision.n)} alertes jugées · ${ci(d.alert_precision)}` : "aucune alerte jugée")} />
        <Stat label="Fraudes manquées (estimation)" icon={<ScanSearch />} tone="danger"
          value={d ? (d.estimate ? fmtInt(d.estimate.missed_frauds) : "—") : undefined}
          hint={d && (d.estimate ? `IC 95 % : ${fmtInt(d.estimate.missed_frauds_ci[0])} – ${fmtInt(d.estimate.missed_frauds_ci[1])} · ${fmtInt(d.control_sample.n)} témoins jugés`
            : `échantillon témoin : ${fmtInt(d.control_sample.n)} revue(s) — à compléter`)} />
        <Stat label="Rappel estimé" icon={<Gauge />} tone="accent"
          value={d ? (d.estimate?.recall != null ? fmtPct(d.estimate.recall) : "—") : undefined}
          hint={d?.estimate?.recall_ci[0] != null ? `entre ${fmtPct(d.estimate.recall_ci[0])} et ${fmtPct(d.estimate.recall_ci[1])}` : "nécessite des témoins jugés"} />
        <Stat label="Dossiers en attente" icon={<Clock />} tone="warn" value={d ? fmtInt(d.open_cases) : undefined}
          hint={d && (d.median_hours_to_verdict != null ? `verdict en ${d.median_hours_to_verdict.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} h (médiane) · ${fmtInt(d.complaints)} plainte(s)` : `${fmtInt(d.complaints)} plainte(s)`)} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        {/* ------------------------------------------------------------ file de revue */}
        <Card className="overflow-hidden">
          <CardHeader>
            <div><CardTitle>File de revue prioritaire</CardTitle>
              <CardDescription>Transactions approuvées et non jugées, choisies pour ce que leur verdict apprend au modèle.</CardDescription></div>
          </CardHeader>
          <div className="flex gap-1 border-y bg-muted/30 p-2">
            {REASONS.map(({ key, label, icon: Icon }) => (
              <button key={key} onClick={() => setTab(key)}
                className={cn("flex flex-1 items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium transition-colors",
                  tab === key ? "bg-card text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground")}>
                <Icon className="h-3.5 w-3.5" />{label}
                <span className="tabular rounded-full bg-muted px-1.5 text-[10px]">{queue.data?.reasons[key]?.length ?? 0}</span>
              </button>
            ))}
          </div>
          <p className="px-5 pt-3 text-xs text-muted-foreground">{current.help}</p>
          <ul className="divide-y">
            {items.map((t) => (
              <li key={t.transaction_id}>
                <Link href={`/transactions/${encodeURIComponent(t.transaction_id)}?reason=${tab}`}
                  className="group flex items-center gap-4 px-5 py-3 transition-colors hover:bg-muted/60">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="tabular text-sm font-semibold">{fmtUsd(t.amount_usd)}</span>
                      <span className="truncate text-xs text-muted-foreground">{t.tx_type} · {t.channel === "VISA_VIRTUAL" ? "Visa" : t.operator} · {t.province} · {t.user_id}</span>
                    </div>
                    <div className="mt-0.5 truncate text-xs text-foreground/80">{t.why}</div>
                  </div>
                  <span className="tabular hidden text-xs font-medium sm:block">{fmtPct(t.fraud_probability)}</span>
                  <RiskBadge level={t.risk_level} />
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                </Link>
              </li>
            ))}
            {queue.data && items.length === 0 && <EmptyState icon={<current.icon />} title="Rien à revoir">Aucune transaction ne correspond sur la période.</EmptyState>}
          </ul>
        </Card>

        {/* ------------------------------------------------------------ indicateurs */}
        <div className="space-y-4">
          <Card>
            <CardHeader><div><CardTitle>Apport de chaque source d&apos;étiquettes</CardTitle>
              <CardDescription>Verdicts rendus sur la période, par motif de revue.</CardDescription></div></CardHeader>
            <CardContent className="space-y-2.5">
              {d?.labels_by_reason.map((r) => (
                <div key={r.reason}>
                  <div className="flex justify-between text-xs"><span className="font-medium">{REVIEW_REASON_LABEL[r.reason] ?? r.reason}</span>
                    <span className="tabular text-muted-foreground">{fmtInt(r.n)} · {fmtInt(r.frauds)} fraudes ({fmtPct(r.fraud_rate)})</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-muted"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${(r.n / maxReason) * 100}%` }} /></div>
                </div>
              ))}
              {d && d.labels_by_reason.length === 0 && <p className="text-xs text-muted-foreground">Aucun verdict sur la période.</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><div><CardTitle>Précision par niveau de risque</CardTitle>
              <CardDescription>Part de fraudes confirmées parmi les alertes jugées.</CardDescription></div></CardHeader>
            <CardContent className="space-y-2">
              {RISK_ORDER.map((lvl) => d?.precision_by_risk.find((r) => r.risk_level === lvl)).filter(Boolean).map((r) => (
                <div key={r!.risk_level} className="flex items-center gap-3 text-xs">
                  <span className="w-20 shrink-0">{RISK_LABEL[r!.risk_level]}</span>
                  <div className="relative h-2 flex-1 rounded-full bg-muted">
                    <div className="absolute inset-y-0 rounded-full bg-primary/25" style={{ left: `${(r!.low ?? 0) * 100}%`, width: `${((r!.high ?? 0) - (r!.low ?? 0)) * 100}%` }} />
                    <div className="absolute -top-0.5 h-3 w-1 rounded bg-primary" style={{ left: `calc(${(r!.rate ?? 0) * 100}% - 2px)` }} />
                  </div>
                  <span className="tabular w-24 text-right">{fmtPct(r!.rate)} <span className="text-muted-foreground">({fmtInt(r!.n)})</span></span>
                </div>
              ))}
              {d && d.precision_by_risk.length === 0 && <p className="text-xs text-muted-foreground">Aucune alerte jugée.</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><div><CardTitle>Calibration</CardTitle>
              <CardDescription>Probabilité annoncée par le modèle contre part de fraudes observée (transactions jugées).</CardDescription></div></CardHeader>
            <CardContent>
              <div className="grid grid-cols-[auto_1fr_1fr_auto] gap-x-3 gap-y-1.5 text-xs">
                <span className="text-muted-foreground">Tranche</span><span className="text-muted-foreground">Annoncée</span><span className="text-muted-foreground">Observée</span><span className="text-right text-muted-foreground">n</span>
                {d?.calibration.map((c) => (
                  <div key={c.bin} className="contents">
                    <span className="tabular">{Math.min(c.bin - 1, 9) * 10}–{Math.min(c.bin, 10) * 10} %</span>
                    <div className="flex items-center"><div className="h-1.5 rounded-full bg-muted-foreground/50" style={{ width: `${Math.max(2, c.predicted * 100)}%` }} /></div>
                    <div className="flex items-center"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${Math.max(2, c.observed * 100)}%` }} /></div>
                    <span className="tabular text-right">{fmtInt(c.n)}</span>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-[11px] text-muted-foreground">Les transactions jugées sont surtout des alertes : la calibration des faibles probabilités repose sur l&apos;échantillon témoin.</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
