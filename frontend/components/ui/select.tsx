import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const FIELD = "h-9 rounded-lg border bg-card text-sm shadow-sm transition-colors placeholder:text-muted-foreground " +
  "hover:border-foreground/20 focus:border-primary/60 focus:outline-none focus:ring-4 focus:ring-primary/15";

export function Select({ className, options, ...p }:
  React.SelectHTMLAttributes<HTMLSelectElement> & { options: [string, string][] }) {
  return (
    <span className={cn("relative inline-flex", className)}>
      <select className={cn(FIELD, "w-full appearance-none pl-3 pr-8")} {...p}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
    </span>
  );
}
export function Input({ className, ...p }: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(FIELD, "w-full px-3", className)} {...p} />;
}

/** Choix exclusif compact (fenêtre de temps, filtre…). */
export function Segmented<T extends string>({ value, onChange, options, className }:
  { value: T; onChange: (v: T) => void; options: [T, string][]; className?: string }) {
  return (
    <div role="radiogroup" className={cn("inline-flex rounded-lg border bg-muted/60 p-0.5 shadow-sm", className)}>
      {options.map(([v, l]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}
          className={cn("rounded-md px-3 py-1.5 text-xs font-medium transition-all",
            value === v ? "bg-card text-foreground shadow-sm ring-1 ring-border" : "text-muted-foreground hover:text-foreground")}>
          {l}
        </button>
      ))}
    </div>
  );
}
