import { cn, ACTION_LABEL, FRAUD_TYPE_HELP, FRAUD_TYPE_LABEL, RISK_LABEL, STATUS_LABEL } from "@/lib/utils";

const TONE = {
  critique: "bg-risk-critique/10 text-risk-critique ring-risk-critique/25 [--dot:hsl(var(--risk-critique))]",
  eleve: "bg-risk-eleve/10 text-risk-eleve ring-risk-eleve/25 [--dot:hsl(var(--risk-eleve))]",
  moyen: "bg-risk-moyen/12 text-warn ring-risk-moyen/30 [--dot:hsl(var(--risk-moyen))]",
  faible: "bg-risk-faible/10 text-risk-faible ring-risk-faible/25 [--dot:hsl(var(--risk-faible))]",
  primary: "bg-primary/10 text-primary ring-primary/25 [--dot:hsl(var(--primary))]",
  neutral: "bg-muted text-muted-foreground ring-border [--dot:hsl(var(--muted-foreground))]",
};
const RISK_TONE: Record<string, keyof typeof TONE> = { CRITIQUE: "critique", ELEVE: "eleve", MOYEN: "moyen", FAIBLE: "faible" };
const ACTION_TONE: Record<string, keyof typeof TONE> = { BLOCK: "critique", VERIFY: "moyen", APPROVE: "faible" };
const STATUS_TONE: Record<string, keyof typeof TONE> = {
  OUVERT: "primary", EN_COURS: "moyen", FRAUDE_CONFIRMEE: "critique", FAUX_POSITIF: "neutral",
};

export function Pill({ tone = "neutral", dot = true, className, children }:
  { tone?: keyof typeof TONE; dot?: boolean; className?: string; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset",
      TONE[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-[var(--dot)]" />}
      {children}
    </span>
  );
}
export const RiskBadge = ({ level }: { level: string }) => <Pill tone={RISK_TONE[level]}>{RISK_LABEL[level] ?? level}</Pill>;
export const ActionBadge = ({ action }: { action: string }) => <Pill tone={ACTION_TONE[action]}>{ACTION_LABEL[action] ?? action}</Pill>;
export const StatusBadge = ({ status }: { status: string }) => <Pill tone={STATUS_TONE[status]}>{STATUS_LABEL[status] ?? status}</Pill>;
/** Typologie de fraude probable ; rien n'est affiché si la transaction n'est pas signalée. */
export const FraudTypeBadge = ({ type, probability }: { type?: string | null; probability?: number | null }) =>
  type ? (
    <span title={FRAUD_TYPE_HELP[type]}>
      <Pill tone="primary" dot={false}>
        {FRAUD_TYPE_LABEL[type] ?? type}{probability != null && <span className="font-normal opacity-70">{Math.round(probability * 100)} %</span>}
      </Pill>
    </span>
  ) : null;
export const Tag = ({ children }: { children: React.ReactNode }) => <Pill dot={false}>{children}</Pill>;
