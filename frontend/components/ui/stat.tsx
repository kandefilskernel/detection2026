import { cn } from "@/lib/utils";

const TONES = {
  default: "bg-primary/10 text-primary",
  danger: "bg-risk-critique/10 text-risk-critique",
  warn: "bg-risk-moyen/15 text-warn",
  success: "bg-risk-faible/10 text-risk-faible",
  accent: "bg-accent/10 text-accent",
};

/** Indicateur clé : libellé, valeur, précision, icône. `value === undefined` -> squelette de chargement. */
export function Stat({ label, value, hint, icon, tone = "default", className, children }: {
  label: string; value?: React.ReactNode; hint?: React.ReactNode; icon?: React.ReactNode;
  tone?: keyof typeof TONES; className?: string; children?: React.ReactNode;
}) {
  return (
    <div className={cn("group relative min-w-0 overflow-hidden rounded-xl border bg-card p-4 shadow-card transition-shadow hover:shadow-float", className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-xs font-medium text-muted-foreground">{label}</div>
          {value === undefined
            ? <div className="skeleton mt-2 h-7 w-24" />
            : <div className="tabular mt-1.5 truncate text-[26px] font-semibold leading-none tracking-tight">{value}</div>}
        </div>
        {icon && <div className={cn("shrink-0 rounded-lg p-2 [&_svg]:h-4 [&_svg]:w-4", TONES[tone])}>{icon}</div>}
      </div>
      {hint && <div className="mt-2 truncate text-xs text-muted-foreground">{hint}</div>}
      {children}
    </div>
  );
}
