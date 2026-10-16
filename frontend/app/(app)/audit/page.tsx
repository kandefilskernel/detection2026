"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, Fingerprint, ShieldCheck, ShieldX } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, EmptyState } from "@/components/ui/card";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { cn, fmtDate, fmtInt } from "@/lib/utils";

const ACTION_TONE = (a: string) =>
  a.includes("ECHEC") || a.includes("FRAUDE") ? "critique" as const
    : a.startsWith("LOGIN") ? "neutral" as const
    : a.startsWith("UTILISATEUR") ? "primary" as const : "moyen" as const;

export default function AuditPage() {
  const [page, setPage] = useState(1);
  const { data } = usePolling<any>(`/audit?page=${page}&size=50`, 5000);
  const [check, setCheck] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <>
      <PageHeader eyebrow="Gouvernance" title="Journal d'audit" subtitle="Ajout seul, chaîné par SHA-256 : toute modification ou suppression est détectable.">
        <Button disabled={busy} onClick={async () => { setBusy(true); try { setCheck(await api("/audit/verify")); } finally { setBusy(false); } }}>
          <Fingerprint /> {busy ? "Vérification…" : "Vérifier l'intégrité"}
        </Button>
      </PageHeader>

      {check && (
        <div className={cn("mb-4 flex items-center gap-4 rounded-xl border p-4 shadow-card animate-fade-up",
          check.valid ? "border-risk-faible/30 bg-risk-faible/[.07]" : "border-risk-critique/30 bg-risk-critique/[.07]")}>
          <div className={cn("grid h-10 w-10 place-items-center rounded-full", check.valid ? "bg-risk-faible/15 text-risk-faible" : "bg-risk-critique/15 text-risk-critique")}>
            {check.valid ? <ShieldCheck className="h-5 w-5" /> : <ShieldX className="h-5 w-5" />}
          </div>
          <div className="text-sm">
            <div className="font-semibold">{check.valid ? "Chaîne intègre" : "Rupture de la chaîne détectée"}</div>
            <div className="text-muted-foreground">
              {check.valid ? `${fmtInt(check.checked)} entrées vérifiées, aucune altération.`
                : `À l'entrée #${check.broken_at_id} — ${fmtInt(check.checked)} entrées valides avant.`}
            </div>
          </div>
        </div>
      )}

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="tbl">
            <thead><tr><th>#</th><th>Date</th><th>Acteur</th><th>Action</th><th>Objet</th><th>Détails</th><th>Empreinte</th></tr></thead>
            <tbody>
              {(data?.items ?? []).map((a: any) => {
                const { event_id, ...details } = a.details ?? {};
                const d = JSON.stringify(details);
                return (
                  <tr key={a.id}>
                    <td className="tabular text-xs text-muted-foreground">{a.id}</td>
                    <td className="whitespace-nowrap text-xs">{fmtDate(a.ts)}</td>
                    <td className="whitespace-nowrap text-xs font-medium">
                      <span className="inline-flex items-center gap-2">
                        <span className={cn("grid h-6 w-6 place-items-center rounded-full text-[10px] font-semibold",
                          a.actor.startsWith("system") ? "bg-muted text-muted-foreground" : "bg-primary/10 text-primary")}>
                          {a.actor.startsWith("system") ? "⚙" : a.actor[0].toUpperCase()}
                        </span>
                        {a.actor}
                      </span>
                    </td>
                    <td><Pill tone={ACTION_TONE(a.action)}>{a.action}</Pill></td>
                    <td className="whitespace-nowrap text-xs">{a.entity}{a.entity_id && <span className="text-muted-foreground"> · {a.entity_id}</span>}</td>
                    <td className="max-w-sm" title={d}>
                      {d === "{}" ? <span className="text-muted-foreground">—</span> : (
                        <div className="flex max-w-md flex-nowrap items-center gap-1 overflow-hidden">
                          {Object.entries(details).slice(0, 2).map(([k, v]) => (
                            <span key={k} className="max-w-[190px] shrink-0 truncate rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                              <span className="font-medium text-foreground/80">{k}</span> {typeof v === "object" ? JSON.stringify(v) : String(v)}
                            </span>
                          ))}
                          {Object.keys(details).length > 2 && <span className="shrink-0 text-[11px] text-muted-foreground">+{Object.keys(details).length - 2}</span>}
                        </div>
                      )}
                    </td>
                    <td><span className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">{a.hash.slice(0, 12)}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {data && data.items.length === 0 && <EmptyState icon={<Fingerprint />} title="Journal vide" />}
        </div>
        <div className="flex items-center justify-between border-t px-5 py-3 text-xs text-muted-foreground">
          <span>{data ? `${fmtInt(data.total)} entrées` : ""}</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft /> Plus récents</Button>
            <Button variant="outline" size="sm" disabled={!data || page * 50 >= data.total} onClick={() => setPage(page + 1)}>Plus anciens <ChevronRight /></Button>
          </div>
        </div>
      </Card>
    </>
  );
}
