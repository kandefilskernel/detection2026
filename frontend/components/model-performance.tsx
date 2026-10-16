"use client";

import { useState } from "react";
import { Grid3x3 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@/components/ui/card";
import { Segmented } from "@/components/ui/select";
import { usePolling } from "@/lib/use-polling";
import { cn, FRAUD_TYPE_LABEL, fmtInt, fmtPct } from "@/lib/utils";

type Scope = "GLOBAL" | "MOBILE_MONEY" | "VISA_VIRTUAL";
type Binary = { tp: number; fn: number; fp: number; tn: number; precision: number; recall: number; f1: number; fpr: number };

/** Intensité de la cellule : bleu pour les bonnes décisions, rouge pour les erreurs. */
function cellStyle(share: number, good: boolean) {
  const a = Math.max(0.06, Math.min(share, 1));
  return { backgroundColor: good ? `rgba(37, 99, 235, ${a * 0.9})` : `rgba(220, 38, 38, ${Math.min(a * 6, 0.85)})` };
}

function Cell({ n, total, label, good }: { n: number; total: number; label: string; good: boolean }) {
  const share = total ? n / total : 0;
  const strong = good ? share > 0.5 : share * 6 > 0.5;
  return (
    <div className="flex flex-col items-center justify-center rounded-xl px-2 py-4 text-center ring-1 ring-black/5"
      style={cellStyle(share, good)}>
      <div className={cn("text-lg font-semibold tabular-nums sm:text-xl", strong ? "text-white" : "text-foreground")}>{fmtInt(n)}</div>
      <div className={cn("text-[11px] tabular-nums", strong ? "text-white/85" : "text-muted-foreground")}>{fmtPct(share)}</div>
      <div className={cn("mt-1 text-[10px] font-medium uppercase tracking-wide", strong ? "text-white/80" : "text-muted-foreground")}>{label}</div>
    </div>
  );
}

function BinaryMatrix({ m }: { m: Binary }) {
  const legit = m.tn + m.fp, fraud = m.tp + m.fn;
  return (
    <div>
      <div className="grid grid-cols-[88px_1fr_1fr] gap-2 text-xs">
        <div />
        <div className="text-center font-medium text-muted-foreground">Prédit légitime</div>
        <div className="text-center font-medium text-muted-foreground">Prédit fraude</div>
        <div className="flex items-center font-medium text-muted-foreground">Réel légitime</div>
        <Cell n={m.tn} total={legit} label="Vrais négatifs" good />
        <Cell n={m.fp} total={legit} label="Fausses alertes" good={false} />
        <div className="flex items-center font-medium text-muted-foreground">Réel fraude</div>
        <Cell n={m.fn} total={fraud} label="Fraudes manquées" good={false} />
        <Cell n={m.tp} total={fraud} label="Fraudes détectées" good />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[["Précision", fmtPct(m.precision)], ["Rappel", fmtPct(m.recall)], ["F1", m.f1.toFixed(3)], ["Taux de FP", fmtPct(m.fpr, 3)]].map(([k, v]) => (
          <div key={k} className="rounded-lg border bg-muted/40 px-3 py-2">
            <div className="text-[11px] text-muted-foreground">{k}</div>
            <div className="text-sm font-semibold tabular-nums">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TypeMatrix({ classes, matrix, norm }: { classes: string[]; matrix: number[][]; norm: number[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-1 text-[11px]">
        <thead>
          <tr>
            <th className="text-left font-medium text-muted-foreground">Réel \ Prédit</th>
            {classes.map((c) => (
              <th key={c} title={FRAUD_TYPE_LABEL[c] ?? c} className="max-w-[64px] truncate px-1 font-medium text-muted-foreground">
                {(FRAUD_TYPE_LABEL[c] ?? c).split(" ")[0]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {classes.map((r, i) => (
            <tr key={r}>
              <td className="whitespace-nowrap pr-2 font-medium">{FRAUD_TYPE_LABEL[r] ?? r}</td>
              {classes.map((c, j) => {
                const v = norm[i][j], diag = i === j;
                return (
                  <td key={c} title={`${FRAUD_TYPE_LABEL[r] ?? r} → ${FRAUD_TYPE_LABEL[c] ?? c} : ${matrix[i][j]}`}
                    className={cn("whitespace-nowrap rounded-md px-1.5 py-1.5 text-center tabular-nums",
                      matrix[i][j] === 0 && "text-muted-foreground/40",
                      diag && v > 0.5 && "text-white", !diag && v >= 0.05 && "font-semibold text-white")}
                    style={matrix[i][j] ? cellStyle(v, diag) : undefined}>
                    {matrix[i][j] ? fmtPct(v, 0) : "·"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Performance du modèle en place sur la période de test : matrices de confusion du détecteur et de la typologie. */
export function ModelPerformance() {
  const { data } = usePolling<any>("/reports/confusion", 60000);
  const [scope, setScope] = useState<Scope>("GLOBAL");

  return (
    <div className="mt-4 grid gap-4 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Matrice de confusion du détecteur</CardTitle>
            <CardDescription>
              Période de test jamais vue à l&apos;entraînement{data?.n_test ? ` · ${fmtInt(data.n_test)} transactions` : ""} · données simulées
            </CardDescription>
          </div>
          <Segmented value={scope} onChange={setScope}
            options={[["GLOBAL", "Global"], ["MOBILE_MONEY", "Mobile Money"], ["VISA_VIRTUAL", "Visa"]]} />
        </CardHeader>
        <CardContent>
          {data?.binary?.[scope]
            ? <BinaryMatrix m={data.binary[scope]} />
            : <EmptyState icon={<Grid3x3 />} title="Matrice indisponible">Lancez python -m ml.training.confusion_report.</EmptyState>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Matrice de confusion par type de fraude</CardTitle>
            <CardDescription>Rappel par type (lignes normalisées) · la diagonale = type correctement identifié</CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          {data?.fraud_type
            ? <TypeMatrix classes={data.fraud_type.classes} matrix={data.fraud_type.matrix} norm={data.fraud_type.row_normalized} />
            : <EmptyState icon={<Grid3x3 />} title="Matrice indisponible">Entraînez le classifieur de type de fraude.</EmptyState>}
        </CardContent>
      </Card>
    </div>
  );
}
