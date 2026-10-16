"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, CheckCircle2, FolderOpen, MousePointerClick, ShieldQuestion, UserCheck, XCircle } from "lucide-react";
import { LiveDot, PageHeader } from "@/components/app-shell";
import { ActionBadge, FraudTypeBadge, RiskBadge, StatusBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, EmptyState } from "@/components/ui/card";
import { MessageAnalyzer } from "@/components/message-analyzer";
import { ProbabilityBar } from "@/components/ui/probability";
import { Select } from "@/components/ui/select";
import { api, getUser } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { cn, FRAUD_TYPE_HELP, FRAUD_TYPE_LABEL, fmtDate, fmtInt, fmtPct, fmtUsd, RISK_LABEL } from "@/lib/utils";

const LEVELS = ["", "CRITIQUE", "ELEVE", "MOYEN", "FAIBLE"];
const STATUSES: [string, string][] = [["OUVERT", "Ouverts"], ["EN_COURS", "En cours"], ["FRAUDE_CONFIRMEE", "Fraudes confirmées"],
                                      ["FAUX_POSITIF", "Faux positifs"], ["", "Tous"]];
const LEVEL_DOT: Record<string, string> = { CRITIQUE: "bg-risk-critique", ELEVE: "bg-risk-eleve", MOYEN: "bg-risk-moyen", FAIBLE: "bg-risk-faible" };

export default function AlertesPage() {
  const me = getUser();
  const [level, setLevel] = useState("");
  const [status, setStatus] = useState("OUVERT");
  const [fraudType, setFraudType] = useState("");
  const [selected, setSelected] = useState<any | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const unblock = usePolling<any>("/cases/unblock-requests", 10000);
  const [decisionNote, setDecisionNote] = useState<Record<number, string>>({});
  const qs = new URLSearchParams({ size: "100", ...(level && { risk_level: level }), ...(status && { status }), ...(fraudType && { fraud_type: fraudType }) }).toString();
  const { data, error, reload } = usePolling<any>(`/cases?${qs}`, 4000);
  const counts: Record<string, number> = data?.counts ?? {};
  const all = Object.values(counts).reduce((a, b) => a + b, 0);

  async function act(body: Record<string, unknown>) {
    if (!selected) return;
    setBusy(true); setMsg(null); setInfo(null);
    try {
      const updated = await api(`/cases/${selected.id}`, { method: "PATCH", body: JSON.stringify(body) });
      if (updated?.four_eyes) {   // déblocage important : enregistré comme demande, en attente d'un second superviseur
        setInfo(updated.detail); setSelected(await api(`/cases/${selected.id}`)); unblock.reload();
      } else setSelected(updated);
      setNote(""); reload();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  }

  async function decide(id: number, approve: boolean) {
    setBusy(true); setMsg(null);
    try {
      await api(`/cases/unblock-requests/${id}/decision`, { method: "POST", body: JSON.stringify({ approve, note: decisionNote[id] ?? "" }) });
      unblock.reload(); reload();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  }
  const pending: any[] = unblock.data?.items ?? [];

  return (
    <>
      <PageHeader eyebrow="Investigation" title="Alertes & dossiers"
        subtitle="Chaque alerte « à vérifier » ou « bloquée » ouvre un dossier ; votre verdict entraîne le modèle suivant.">
        <LiveDot error={error} />
      </PageHeader>

      {pending.length > 0 && (
        <Card className="mb-4 border-risk-moyen/40">
          <CardContent className="pt-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold"><ShieldQuestion className="h-4 w-4 text-warn" />
              Déblocages en attente d&apos;un second validateur (quatre yeux)
              <span className="text-xs font-normal text-muted-foreground">· à partir de {fmtUsd(unblock.data?.min_amount_usd)}</span></div>
            <ul className="divide-y rounded-xl border">
              {pending.map((r) => (
                <li key={r.id} className="grid gap-3 p-3 text-sm lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] lg:items-center">
                  <div className="min-w-0">
                    <div><span className="tabular font-semibold">{fmtUsd(r.amount_usd)}</span>
                      <Link href={`/transactions/${r.transaction_id}`} className="ml-2 font-mono text-xs text-primary hover:underline">{r.transaction_id}</Link></div>
                    <div className="truncate text-xs text-muted-foreground">Demandé par {r.requested_by_name} · {fmtDate(r.requested_at)} · « {r.note} »</div>
                  </div>
                  {unblock.data?.can_decide && r.requested_by !== me?.id ? (
                    <>
                      <input value={decisionNote[r.id] ?? ""} onChange={(e) => setDecisionNote({ ...decisionNote, [r.id]: e.target.value })}
                        placeholder="Justification de la décision (obligatoire)"
                        className="w-full rounded-lg border bg-card px-3 py-2 text-xs focus:border-primary/60 focus:outline-none focus:ring-4 focus:ring-primary/15" />
                      <div className="flex gap-2">
                        <Button size="sm" variant="success" disabled={busy || (decisionNote[r.id] ?? "").trim().length < 5} onClick={() => decide(r.id, true)}><CheckCircle2 /> Débloquer</Button>
                        <Button size="sm" variant="outline" disabled={busy || (decisionNote[r.id] ?? "").trim().length < 5} onClick={() => decide(r.id, false)}><XCircle /> Refuser</Button>
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-muted-foreground lg:col-span-2">{r.requested_by === me?.id ? "Votre demande : un autre superviseur doit la valider." : "Validation réservée aux superviseurs."}</p>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Onglets de statut */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 overflow-x-auto rounded-xl border bg-card p-1 shadow-card">
          {STATUSES.map(([v, l]) => {
            const n = v ? counts[v] ?? 0 : all;
            return (
              <button key={v || "all"} onClick={() => setStatus(v)}
                className={cn("flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                  status === v ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
                {l}
                <span className={cn("tabular rounded-full px-1.5 py-px text-[10px]", status === v ? "bg-white/20" : "bg-muted")}>{fmtInt(n)}</span>
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Select value={fraudType} onChange={(e) => setFraudType(e.target.value)}
            options={[["", "Tous types de fraude"], ...Object.entries(FRAUD_TYPE_LABEL).filter(([k]) => k !== "NON_DETERMINEE")]} />
          {LEVELS.map((l) => (
            <button key={l || "all"} onClick={() => setLevel(l)}
              className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                level === l ? "border-foreground/20 bg-foreground text-background" : "bg-card text-muted-foreground hover:text-foreground")}>
              {l && <span className={cn("h-1.5 w-1.5 rounded-full", LEVEL_DOT[l])} />}
              {l ? RISK_LABEL[l] : "Tous niveaux"}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card className="overflow-hidden">
          <div className="max-h-[calc(100vh-260px)] overflow-auto">
            <table className="tbl">
              <thead><tr><th>Dossier</th><th>Opération</th><th className="num">Montant</th><th>Risque</th><th>Type de fraude</th><th>Statut</th></tr></thead>
              <tbody>
                {(data?.items ?? []).map((c: any) => (
                  <tr key={c.id} onClick={() => { setSelected(c); setMsg(null); setInfo(null); }}
                    className={cn("cursor-pointer", selected?.id === c.id && "!bg-primary/[.07] shadow-[inset_3px_0_0_hsl(var(--primary))]")}>
                    <td className="whitespace-nowrap"><div className="font-medium">{c.user_id}</div>
                      <div className="tabular text-[11px] text-muted-foreground">n° {c.id}</div></td>
                    <td className="whitespace-nowrap text-xs">{c.tx_type}<div className="text-muted-foreground">{c.channel === "VISA_VIRTUAL" ? "Visa" : "Mobile Money"}</div></td>
                    <td className="num whitespace-nowrap font-medium">{fmtUsd(c.amount_usd)}</td>
                    <td className="whitespace-nowrap"><RiskBadge level={c.risk_level} />
                      <div className="tabular mt-1 text-[11px] text-muted-foreground">{fmtPct(c.fraud_probability)}</div></td>
                    <td className="max-w-[170px]"><FraudTypeBadge type={c.fraud_type} /></td>
                    <td><StatusBadge status={c.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data && data.items.length === 0 && <EmptyState icon={<FolderOpen />} title="Aucun dossier">Rien à traiter pour ces filtres.</EmptyState>}
          </div>
        </Card>

        <Card className="xl:sticky xl:top-20 xl:self-start">
          {!selected ? (
            <EmptyState icon={<MousePointerClick />} title="Aucun dossier sélectionné">Cliquez sur un dossier de la liste pour l&apos;instruire.</EmptyState>
          ) : (
            <>
              <div className="flex items-start justify-between gap-3 border-b px-5 py-4">
                <div>
                  <div className="text-xs text-muted-foreground">Dossier #{selected.id}</div>
                  <div className="tabular mt-0.5 text-2xl font-semibold tracking-tight">{fmtUsd(selected.amount_usd)}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5"><RiskBadge level={selected.risk_level} /><ActionBadge action={selected.action} /><StatusBadge status={selected.status} /></div>
                  {selected.fraud_type && (
                    <p className="mt-2 max-w-xs text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{FRAUD_TYPE_LABEL[selected.fraud_type] ?? selected.fraud_type}</span>
                      {" : "}{FRAUD_TYPE_HELP[selected.fraud_type]}
                    </p>
                  )}
                </div>
              </div>
              <CardContent className="space-y-4 pt-4 text-sm">
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5">
                  {[["Client", selected.user_id], ["Opération", selected.tx_type],
                    ["Probabilité", <ProbabilityBar key="p" p={selected.fraud_probability} level={selected.risk_level} />],
                    ["Canal", selected.channel === "VISA_VIRTUAL" ? "Visa virtuelle" : "Mobile Money"],
                    ["Heure", fmtDate(selected.tx_time)], ["Ouvert le", fmtDate(selected.created_at)]].map(([k, v]) => (
                    <div key={k as string}><dt className="text-xs text-muted-foreground">{k}</dt><dd className="mt-0.5 font-medium [&>div]:justify-start">{v}</dd></div>
                  ))}
                </dl>
                <Link href={`/transactions/${selected.transaction_id}`}
                  className="flex items-center justify-between rounded-lg border bg-muted/40 px-3 py-2.5 text-xs font-medium transition-colors hover:border-primary/40 hover:text-primary">
                  Explication du modèle et historique du client <ArrowRight className="h-4 w-4" />
                </Link>
                <MessageAnalyzer />
                {selected.resolution_note && (
                  <div className="rounded-lg border-l-2 border-primary bg-muted/50 p-3 text-xs"><div className="mb-1 font-medium">Note de résolution</div>{selected.resolution_note}</div>
                )}
                {["OUVERT", "EN_COURS"].includes(selected.status) && (
                  <div className="space-y-3 border-t pt-4">
                    {selected.status === "OUVERT" && (
                      <Button variant="outline" className="w-full" disabled={busy} onClick={() => act({ status: "EN_COURS", assigned_to: me?.id })}>
                        <UserCheck /> Prendre en charge
                      </Button>
                    )}
                    <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3}
                      placeholder="Note de résolution (obligatoire) : appel client, vérification agent…"
                      className="w-full rounded-lg border bg-card p-3 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none focus:ring-4 focus:ring-primary/15" />
                    <div className="grid grid-cols-2 gap-2">
                      <Button variant="danger" disabled={busy || !note.trim()} onClick={() => act({ status: "FRAUDE_CONFIRMEE", resolution_note: note })}>
                        <XCircle /> Fraude confirmée
                      </Button>
                      <Button variant="success" disabled={busy || !note.trim()} onClick={() => act({ status: "FAUX_POSITIF", resolution_note: note })}>
                        <CheckCircle2 /> Faux positif
                      </Button>
                    </div>
                  </div>
                )}
                {info && <p className="rounded-lg bg-risk-moyen/15 px-3 py-2 text-xs text-warn">{info}</p>}
                {msg && <p className="rounded-lg bg-risk-critique/10 px-3 py-2 text-xs text-risk-critique">{msg}</p>}
              </CardContent>
            </>
          )}
        </Card>
      </div>
    </>
  );
}
