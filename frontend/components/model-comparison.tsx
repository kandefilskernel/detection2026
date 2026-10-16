"use client";

import { useState } from "react";
import { Scale, Trophy } from "lucide-react";
import { Pill } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@/components/ui/card";
import { Segmented } from "@/components/ui/select";
import { usePolling } from "@/lib/use-polling";
import { cn, fmtInt, fmtPct } from "@/lib/utils";

type View = "RANKING" | "DECISION";
type Method = {
  key: string; label: string; family: string; pr_auc: number; f1: number; precision: number; recall: number;
  false_positive_rate: number; weighted_score: number; rank1_share: number; notes: Record<string, number>;
};
type Significance = {
  versus: string; diff_pr_auc: number; ci95: [number, number]; significant_95: boolean;
  mcnemar_hybride_seul_juste: number; mcnemar_autre_seul_juste: number; mcnemar_p: number;
};

const num = (v: number, d = 4) => v.toFixed(d).replace(".", ",");
const signed = (v: number) => `${v >= 0 ? "+" : "−"}${num(Math.abs(v))}`;

function Ranking({ methods, chosen, criteria }: { methods: Method[]; chosen: string; criteria: { key: string; label: string; weight: number }[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-2 font-medium">#</th>
            <th className="py-2 pr-3 font-medium">Méthode</th>
            <th className="min-w-[140px] py-2 pr-3 font-medium">PR-AUC</th>
            <th className="py-2 pr-3 text-right font-medium">F1</th>
            <th className="py-2 pr-3 text-right font-medium">Taux de FP</th>
            {criteria.map((c) => (
              <th key={c.key} title={`${c.label} — poids ${fmtPct(c.weight, 0)}`} className="hidden py-2 pr-2 text-center font-medium lg:table-cell">
                {c.label.split(" ")[0]}
              </th>
            ))}
            <th className="py-2 text-right font-medium">Score / 5</th>
          </tr>
        </thead>
        <tbody>
          {methods.map((m, i) => (
            <tr key={m.key} className={cn("border-b last:border-0", m.key === chosen && "bg-primary/5")}>
              <td className="py-2 pr-2 tabular-nums text-muted-foreground">{i + 1}</td>
              <td className="py-2 pr-3">
                <div className="flex items-center gap-1.5 font-medium">
                  {m.label}
                  {m.key === chosen && <Pill tone="primary" dot={false}>retenu</Pill>}
                </div>
                <div className="text-[11px] text-muted-foreground">{m.family}</div>
              </td>
              <td className="py-2 pr-3">
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-muted">
                    <div className={cn("h-1.5 rounded-full", m.key === chosen ? "bg-primary" : "bg-muted-foreground/50")}
                      style={{ width: `${m.pr_auc * 100}%` }} />
                  </div>
                  <span className="w-12 text-right tabular-nums">{num(m.pr_auc)}</span>
                </div>
              </td>
              <td className="py-2 pr-3 text-right tabular-nums">{num(m.f1, 3)}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{fmtPct(m.false_positive_rate, 3)}</td>
              {criteria.map((c) => (
                <td key={c.key} className="hidden py-2 pr-2 text-center tabular-nums text-muted-foreground lg:table-cell">{m.notes[c.key]}</td>
              ))}
              <td className="py-2 text-right font-semibold tabular-nums">{num(m.weighted_score, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-3 text-[11px] text-muted-foreground">
        Score pondéré : {criteria.map((c) => `${c.label} ${fmtPct(c.weight, 0)}`).join(" · ")}. Notes de 1 à 5 ; PR-AUC et F1 notés à partir des mesures.
      </p>
    </div>
  );
}

function Decision({ data }: { data: any }) {
  const d = data.decision;
  const errors = data.errors as Record<string, { fausses_alertes: number; fraudes_manquees: number }>;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div>
        <div className="flex items-center gap-3 rounded-xl border bg-primary/5 p-4">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary/15 text-primary"><Trophy className="h-5 w-5" /></div>
          <div>
            <div className="text-sm font-semibold">Modèle retenu : {d.label}</div>
            <div className="text-xs text-muted-foreground">
              Score {num(d.weighted_score, 2)} / 5 contre {num(d.runner_up_score, 2)} pour {d.runner_up} ·
              premier dans {fmtPct(d.rank1_share, 0)} de {fmtInt(data.sensitivity_draws)} pondérations tirées au hasard
            </div>
          </div>
        </div>
        <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-xs">
          {d.reasons.map((r: string) => <li key={r}>{r}</li>)}
        </ol>
        {data.latency_ms?.p50 != null && (
          <p className="mt-3 text-[11px] text-muted-foreground">
            Latence de bout en bout (rejeu) : médiane {num(data.latency_ms.p50, 0)} ms, 95ᵉ centile {num(data.latency_ms.p95, 0)} ms.
          </p>
        )}
      </div>
      <div className="space-y-4">
        <div>
          <div className="mb-2 text-xs font-medium">Significativité (bootstrap par usager, McNemar)</div>
          <div className="space-y-1.5">
            {(data.significance as Significance[]).map((s) => (
              <div key={s.versus} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs">
                <span className="font-medium">Hybride − {s.versus}</span>
                <span className="tabular-nums text-muted-foreground">
                  {signed(s.diff_pr_auc)} [{signed(s.ci95[0])} ; {signed(s.ci95[1])}] · {s.mcnemar_hybride_seul_juste} contre {s.mcnemar_autre_seul_juste}
                </span>
                <Pill tone={s.significant_95 && s.mcnemar_p < 0.05 ? "faible" : "neutral"}>
                  {s.significant_95 && s.mcnemar_p < 0.05 ? "significatif" : "non significatif"}
                </Pill>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-2 text-xs font-medium">Erreurs au seuil retenu</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {Object.entries(errors).map(([k, v]) => (
              <div key={k} className={cn("rounded-lg border px-3 py-2", k === d.label && "border-primary/40 bg-primary/5")}>
                <div className="text-[11px] text-muted-foreground">{k}</div>
                <div className="text-xs tabular-nums"><span className="font-semibold">{fmtInt(v.fausses_alertes)}</span> fausses alertes</div>
                <div className="text-xs tabular-nums"><span className="font-semibold">{fmtInt(v.fraudes_manquees)}</span> fraudes manquées</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Étude comparative des méthodes d'apprentissage et justification du modèle en place (ml.training.model_selection). */
export function ModelComparison() {
  const { data } = usePolling<any>("/reports/model-comparison", 300000);
  const [view, setView] = useState<View>("RANKING");

  return (
    <Card className="mt-4">
      <CardHeader>
        <div>
          <CardTitle>Comparaison des méthodes d&apos;apprentissage</CardTitle>
          <CardDescription>
            {data ? `${data.methods.length} méthodes sur la même période de test · ${fmtInt(data.n_test)} transactions, ${fmtInt(data.n_fraud_test)} fraudes · données simulées`
              : "Pourquoi ce modèle est en service"}
          </CardDescription>
        </div>
        <Segmented value={view} onChange={setView} options={[["RANKING", "Classement"], ["DECISION", "Décision"]]} />
      </CardHeader>
      <CardContent>
        {!data
          ? <EmptyState icon={<Scale />} title="Comparaison indisponible">Lancez python -m ml.training.model_selection.</EmptyState>
          : view === "RANKING"
            ? <Ranking methods={data.methods} chosen={data.decision.key} criteria={data.criteria} />
            : <Decision data={data} />}
      </CardContent>
    </Card>
  );
}
