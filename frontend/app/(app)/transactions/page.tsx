"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, SearchX, X } from "lucide-react";
import { LiveDot, PageHeader } from "@/components/app-shell";
import { ActionBadge, FraudTypeBadge, RiskBadge, Tag } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, EmptyState } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { usePolling } from "@/lib/use-polling";
import { ProbabilityBar } from "@/components/ui/probability";
import { FRAUD_TYPE_LABEL, fmtDate, fmtInt, fmtUsd } from "@/lib/utils";

const SIZE = 50;
const EMPTY = { channel: "", operator: "", action: "", risk_level: "", fraud_type: "", search: "" };

export default function TransactionsPage() {
  const [f, setF] = useState(EMPTY);
  const [page, setPage] = useState(1);
  // Recherche lancée depuis la barre du haut : /transactions?search=U001234
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const s = q.get("search"), ft = q.get("fraud_type");
    if (s || ft) setF((prev) => ({ ...prev, search: s ?? "", fraud_type: ft ?? "" }));
  }, []);
  const qs = new URLSearchParams({ page: String(page), size: String(SIZE),
    ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) }).toString();
  const { data, error } = usePolling<any>(`/transactions?${qs}`, 4000);
  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLSelectElement>) => { setPage(1); setF({ ...f, [k]: e.target.value }); };
  const pages = data ? Math.max(1, Math.ceil(data.total / SIZE)) : 1;
  const filtered = Object.values(f).some(Boolean);

  return (
    <>
      <PageHeader eyebrow="Supervision" title="Transactions" subtitle={data ? `${fmtInt(data.total)} transactions scorées` : "Chargement…"}>
        <LiveDot error={error} />
      </PageHeader>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-5 py-3">
          <Select value={f.channel} onChange={set("channel")} options={[["", "Tous canaux"], ["MOBILE_MONEY", "Mobile Money"], ["VISA_VIRTUAL", "Visa virtuelle"]]} />
          <Select value={f.operator} onChange={set("operator")} options={[["", "Tous opérateurs"], ["VODACOM", "Vodacom"], ["AIRTEL", "Airtel"], ["ORANGE", "Orange"]]} />
          <Select value={f.action} onChange={set("action")} options={[["", "Toutes décisions"], ["APPROVE", "Approuvées"], ["VERIFY", "À vérifier"], ["BLOCK", "Bloquées"]]} />
          <Select value={f.risk_level} onChange={set("risk_level")} options={[["", "Tous risques"], ["CRITIQUE", "Critique"], ["ELEVE", "Élevé"], ["MOYEN", "Moyen"], ["FAIBLE", "Faible"]]} />
          <Select value={f.fraud_type} onChange={set("fraud_type")} options={[["", "Tous types de fraude"], ...Object.entries(FRAUD_TYPE_LABEL).filter(([k]) => k !== "NON_DETERMINEE")]} />
          {f.search && (
            <span className="inline-flex h-9 items-center gap-2 rounded-lg border border-primary/30 bg-primary/10 pl-3 pr-1.5 text-xs font-medium text-primary">
              Recherche : <span className="font-mono">{f.search}</span>
              <button onClick={() => { setPage(1); setF({ ...f, search: "" }); }} aria-label="Retirer la recherche" className="rounded p-0.5 hover:bg-primary/15"><X className="h-3.5 w-3.5" /></button>
            </span>
          )}
          {filtered && <Button variant="ghost" size="sm" className="ml-auto" onClick={() => { setPage(1); setF(EMPTY); }}>Réinitialiser</Button>}
        </div>
        <div className="overflow-x-auto">
          <table className="tbl">
            <thead>
              <tr><th>Heure</th><th>Client</th><th>Opération</th><th>Province</th><th className="num">Montant</th>
                <th className="num">P(fraude)</th><th>Risque</th><th>Décision</th><th>Type de fraude</th></tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((t: any) => (
                <tr key={t.transaction_id}>
                  <td className="whitespace-nowrap text-xs text-muted-foreground">{fmtDate(t.tx_time)}</td>
                  <td className="whitespace-nowrap">
                    <Link href={`/transactions/${t.transaction_id}`} className="font-medium text-primary hover:underline">{t.user_id}</Link>
                    <div className="font-mono text-[10px] text-muted-foreground">{t.transaction_id.slice(0, 12)}…</div>
                  </td>
                  <td className="whitespace-nowrap text-xs">
                    {t.tx_type}
                    <div className="mt-0.5 flex items-center gap-1.5 text-muted-foreground">
                      <span>{t.channel === "VISA_VIRTUAL" ? "Visa" : t.operator}</span><Tag>{t.access_channel}</Tag>
                    </div>
                  </td>
                  <td className="whitespace-nowrap text-xs">{t.province}</td>
                  <td className="num whitespace-nowrap font-medium">{fmtUsd(t.amount_usd)}</td>
                  <td><ProbabilityBar p={t.fraud_probability} level={t.risk_level} /></td>
                  <td><RiskBadge level={t.risk_level} /></td>
                  <td><ActionBadge action={t.action} /></td>
                  <td><FraudTypeBadge type={t.fraud_type} probability={t.fraud_type_probability} /></td>
                </tr>
              ))}
              {!data && Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}><td colSpan={9}><div className="skeleton h-5 w-full" /></td></tr>
              ))}
            </tbody>
          </table>
          {data && data.items.length === 0 && <EmptyState icon={<SearchX />} title="Aucune transaction">Aucun résultat pour ces filtres.</EmptyState>}
        </div>
        <div className="flex items-center justify-between gap-2 border-t px-5 py-3 text-xs text-muted-foreground">
          <span>{data ? `${fmtInt((page - 1) * SIZE + Math.min(1, data.items.length))}–${fmtInt((page - 1) * SIZE + data.items.length)} sur ${fmtInt(data.total)}` : ""}</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft /> Précédent</Button>
            <span className="tabular px-1">Page {page} / {pages}</span>
            <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Suivant <ChevronRight /></Button>
          </div>
        </div>
      </Card>
    </>
  );
}
