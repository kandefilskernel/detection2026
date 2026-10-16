"use client";

import { useState } from "react";
import { FlaskConical, Radio, Scale3d, TriangleAlert } from "lucide-react";
import { LiveDot, PageHeader } from "@/components/app-shell";
import { Pill } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@/components/ui/card";
import { Segmented } from "@/components/ui/select";
import { usePolling } from "@/lib/use-polling";
import { cn, fmtInt, fmtPct } from "@/lib/utils";

type LiveGroup = {
  group: string; n: number; alerts: number; blocks: number; alert_rate: number | null; alert_ci: [number | null, number | null];
  ratio: number | null; reviewed: number; false_positive_share: number | null; judged: boolean; flagged: boolean;
};
type Live = { label: string; days: number; n: number; overall_alert_rate: number | null; ratio_rule: number; min_n: number;
  max_min_ratio: number | null; dimensions: Record<string, string>; groups: LiveGroup[] };
type OffGroup = { group: string; n: number; n_legit: number; n_fraud: number; false_alert_rate: number | null;
  false_alert_ci: [number | null, number | null]; false_alert_ratio: number | null; recall: number | null; judged: boolean;
  flag_false_alerts: boolean; flag_recall: boolean };
type Off = { n: number; ratio_rule: number; decision: { intercept: { overall: { false_alert_rate: number; recall: number };
  dimensions: Record<string, { label: string; groups: OffGroup[]; max_min_ratio: number | null; n_flagged: number }> } } };

const LIVE_DIMS: [string, string][] = [["province", "Province"], ["operator", "Opérateur"], ["access_channel", "Accès"],
  ["kyc_level", "KYC"], ["device", "Téléphone"]];
type Days = "7" | "30" | "90";

/** Barre de taux avec son intervalle de confiance et le repère du taux global. */
function RateBar({ rate, ci, overall, max, flagged }: { rate: number | null; ci: [number | null, number | null]; overall: number | null; max: number; flagged: boolean }) {
  const x = (v: number | null) => `${Math.min(100, ((v ?? 0) / max) * 100)}%`;
  return (
    <div className="relative h-3 w-full rounded-full bg-muted">
      <div className="absolute inset-y-0 rounded-full bg-primary/20" style={{ left: x(ci[0]), width: `calc(${x(ci[1])} - ${x(ci[0])})` }} />
      <div className={cn("absolute inset-y-0 left-0 rounded-full", flagged ? "bg-risk-critique" : "bg-primary")} style={{ width: x(rate) }} />
      {overall != null && <div className="absolute -inset-y-1 w-0.5 bg-foreground/70" style={{ left: x(overall) }} title="taux global" />}
    </div>
  );
}

export default function EquitePage() {
  const [dim, setDim] = useState("province");
  const [days, setDays] = useState<Days>("30");
  const [offDim, setOffDim] = useState("income_band");
  const live = usePolling<Live>(`/fairness/live?dimension=${dim}&days=${days}`, 30000);
  const { data: off } = usePolling<Off>("/fairness/evaluation", 0);
  const L = live.data;
  const maxLive = Math.max(0.0001, ...(L?.groups.map((g) => g.alert_ci[1] ?? g.alert_rate ?? 0) ?? []));
  const ev = off?.decision.intercept;
  const od = ev?.dimensions[offDim];
  const maxOff = Math.max(0.0001, ...(od?.groups.map((g) => g.false_alert_ci[1] ?? 0) ?? []));
  const flaggedOff = ev ? Object.entries(ev.dimensions).flatMap(([, d]) => d.groups.filter((g) => g.flag_false_alerts || g.flag_recall).map((g) => `${d.label} : ${g.group}`)) : [];

  return (
    <>
      <PageHeader eyebrow="Gouvernance" title="Équité du modèle"
        subtitle="Une fausse alerte pèse plus lourd sur un client rural en USSD, loin d'un agent. Les erreurs du modèle touchent-elles certains groupes plus que d'autres ?">
        <LiveDot error={live.error} />
        <Segmented value={days} onChange={setDays} options={[["7", "7 j"], ["30", "30 j"], ["90", "90 j"]]} />
      </PageHeader>

      {flaggedOff.length > 0 && (
        <div className="mb-4 flex items-start gap-3 rounded-2xl border border-risk-moyen/40 bg-risk-moyen/10 p-4 text-sm">
          <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div><div className="font-semibold">{flaggedOff.length} groupe(s) subissent significativement plus de fausses alertes (évaluation sur la vérité complète)</div>
            <p className="mt-1 text-xs text-muted-foreground">{flaggedOff.join(" · ")}</p></div>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <div><CardTitle className="flex items-center gap-2"><Radio className="h-4 w-4 text-primary" />En production</CardTitle>
              <CardDescription>Taux d&apos;alerte par groupe (la fraude étant rare, il suit de près le taux de fausses alertes), avec IC 95 % ; trait noir : taux global.</CardDescription></div>
          </CardHeader>
          <div className="flex flex-wrap gap-1 border-y bg-muted/30 p-2">
            {LIVE_DIMS.map(([k, l]) => (
              <button key={k} onClick={() => setDim(k)} className={cn("rounded-lg px-3 py-1.5 text-xs font-medium",
                dim === k ? "bg-card shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground")}>{l}</button>
            ))}
          </div>
          <CardContent className="space-y-3 pt-4">
            {L && <div className="text-xs text-muted-foreground">{fmtInt(L.n)} transactions · taux global {fmtPct(L.overall_alert_rate, 2)}
              {L.max_min_ratio && <> · écart max/min <b className="text-foreground">{L.max_min_ratio.toFixed(2)}</b></>}</div>}
            {L?.groups.map((g) => (
              <div key={g.group} className={cn(!g.judged && "opacity-50")}>
                <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
                  <span className="font-medium">{g.group} {g.flagged && <Pill tone="critique" dot={false}>× {g.ratio?.toFixed(2)}</Pill>}</span>
                  <span className="tabular text-muted-foreground">{fmtPct(g.alert_rate, 2)} · {fmtInt(g.n)} tx
                    {g.reviewed > 0 && <> · faux positifs confirmés {fmtPct(g.false_positive_share)} ({fmtInt(g.reviewed)} jugées)</>}</span>
                </div>
                <RateBar rate={g.alert_rate} ci={g.alert_ci} overall={L.overall_alert_rate} max={maxLive} flagged={g.flagged} />
              </div>
            ))}
            {L && L.groups.length === 0 && <EmptyState icon={<Scale3d />} title="Aucune transaction">Rien sur la période.</EmptyState>}
            {L && <p className="text-[11px] text-muted-foreground">Groupe signalé : taux ≥ {L.ratio_rule} × le taux global et borne basse de l&apos;IC au-dessus ; groupes de moins de {L.min_n} transactions grisés.</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div><CardTitle className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-primary" />Avec la vérité complète (hors ligne)</CardTitle>
              <CardDescription>{ev ? `${fmtInt(off!.n)} opérations de test · fausses alertes globales ${fmtPct(ev.overall.false_alert_rate, 2)} · rappel ${fmtPct(ev.overall.recall, 2)}` : "Évaluation non disponible."}</CardDescription></div>
          </CardHeader>
          {ev && (
            <>
              <div className="flex flex-wrap gap-1 border-y bg-muted/30 p-2">
                {Object.entries(ev.dimensions).map(([k, d]) => (
                  <button key={k} onClick={() => setOffDim(k)} className={cn("rounded-lg px-3 py-1.5 text-xs font-medium",
                    offDim === k ? "bg-card shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground")}>
                    {d.label}{d.n_flagged > 0 && <span className="ml-1 text-risk-critique">●</span>}</button>
                ))}
              </div>
              <CardContent className="space-y-3 pt-4">
                {od?.groups.map((g) => (
                  <div key={g.group} className={cn(!g.judged && "opacity-50")}>
                    <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
                      <span className="font-medium">{g.group} {g.flag_false_alerts && <Pill tone="critique" dot={false}>× {g.false_alert_ratio?.toFixed(2)}</Pill>}
                        {g.flag_recall && <Pill tone="moyen" dot={false}>rappel plus bas</Pill>}</span>
                      <span className="tabular text-muted-foreground">fausses alertes {fmtPct(g.false_alert_rate, 2)} · rappel {fmtPct(g.recall)} · {fmtInt(g.n)} op.</span>
                    </div>
                    <RateBar rate={g.false_alert_rate} ci={g.false_alert_ci} overall={ev.overall.false_alert_rate} max={maxOff} flagged={g.flag_false_alerts} />
                  </div>
                ))}
                <p className="text-[11px] text-muted-foreground">Données simulées : le générateur ne modélise pas de biais social ; les écarts viennent des
                  comportements simulés (montants, canaux). La mesure doit être refaite sur les données réelles de chaque opérateur avant toute conclusion.</p>
              </CardContent>
            </>
          )}
        </Card>
      </div>
    </>
  );
}
