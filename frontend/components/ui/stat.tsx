import { cn } from "@/lib/utils";

const BARS = {
  default: "from-primary/70", danger: "from-risk-critique/70", warn: "from-risk-moyen/80",
  success: "from-risk-faible/70", accent: "from-accent/70",
};
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
    <div className={cn("group relative min-w-0 overflow-hidden rounded-2xl border bg-card p-4 shadow-card transition-all hover:-translate-y-px hover:shadow-float", className)}>
      <div aria-hidden className={cn("absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r to-transparent", BARS[tone])} />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-xs font-medium text-muted-foreground">{label}</div>
          {value === undefined
            ? <div className="skeleton mt-2 h-7 w-24" />
            : <div className="tabular mt-2 truncate text-[22px] font-semibold leading-none tracking-tight sm:text-[28px]">{value}</div>}
        </div>
        {icon && <div className={cn("shrink-0 rounded-xl p-2.5 ring-1 ring-inset ring-black/5 dark:ring-white/10 [&_svg]:h-4 [&_svg]:w-4", TONES[tone])}>{icon}</div>}
      </div>
      {hint && <div className="mt-2 truncate text-xs text-muted-foreground">{hint}</div>}
      {children}
    </div>
  );
}
