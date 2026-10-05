import { fmtPct, RISK_LABEL } from "@/lib/utils";

/** Probabilité de fraude + jauge colorée selon le niveau de risque. */
export function ProbabilityBar({ p, level }: { p: number; level: string }) {
  const color = { CRITIQUE: "bg-risk-critique", ELEVE: "bg-risk-eleve", MOYEN: "bg-risk-moyen" }[level] ?? "bg-risk-faible";
  return (
    <div className="flex items-center justify-end gap-2 whitespace-nowrap" title={RISK_LABEL[level]}>
      <span className="tabular">{fmtPct(p)}</span>
      <span className="h-1.5 w-12 rounded-full bg-muted"><span className={`block h-1.5 rounded-full ${color}`} style={{ width: `${Math.max(3, p * 100)}%` }} /></span>
    </div>
  );
}
