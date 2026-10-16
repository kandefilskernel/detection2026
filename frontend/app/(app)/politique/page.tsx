"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { FlaskConical, History, RotateCcw, Save, Scale, SlidersHorizontal } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Segmented } from "@/components/ui/select";
import { api, getUser } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { cn, fmtDate, fmtInt, fmtPct, fmtUsd } from "@/lib/utils";

type Costs = { friction_usd: number; step_up_catch_rate: number; false_block_usd: number; false_block_amount_share: number };
type Params = { costs: Record<string, Costs>; operator_overrides: Record<string, Costs>; block_floor: number; approve_ceiling: number; version: string };
type Summary = {
  n: number; actions: Record<string, number>; shares: Record<string, number>;
  expected: { fraud_loss: number; friction: number; false_block: number; fraud_stopped_usd: number; total: number };
  realized: { n: number; frauds: number; fraud_missed: number; legit_blocked: number; legit_verified: number; total: number };
};
type Sim = { days: number; n_rows: number; truncated: boolean; current: Summary; candidate: Summary; changed: number; moves: Record<string, number> };
type PolicyState = {
  active: Params; active_id: number | null; defaults: Params; bounds: Record<string, [number, number]>;
  channels: string[]; operators: string[]; published: boolean | null;
  history: { id: number; created_at: string; created_by: string; note: string; is_active: boolean; simulation: any }[];
};
type Days = "1" | "7" | "30";

const CHANNEL_LABEL: Record<string, string> = { MOBILE_MONEY: "Mobile Money", VISA_VIRTUAL: "Carte Visa virtuelle" };
const FIELDS: { key: keyof Costs; label: string; help: string; pct?: boolean; step: number; max: number }[] = [
  { key: "friction_usd", label: "Coût d'une vérification", help: "temps client, abandon, SMS / appel (USD)", step: 0.05, max: 5 },
  { key: "step_up_catch_rate", label: "Fraudes stoppées par la vérification", help: "part des fraudes arrêtées par OTP / PIN", pct: true, step: 0.01, max: 1 },
  { key: "false_block_usd", label: "Coût fixe d'un faux blocage", help: "client honnête bloqué : appel, mécontentement (USD)", step: 0.5, max: 50 },
  { key: "false_block_amount_share", label: "Part du montant perdue", help: "transaction honnête non réalisée", pct: true, step: 0.01, max: 1 },
];
const ACTION_LABEL: Record<string, string> = { APPROVE: "Approuvées", VERIFY: "Vérifiées", BLOCK: "Bloquées" };
const ACTION_COLOR: Record<string, string> = { APPROVE: "bg-risk-faible", VERIFY: "bg-risk-moyen", BLOCK: "bg-risk-critique" };
const POLICY_LABEL: Record<string, string> = {
  seuil_F1_blocage: "Seuil F1 → blocage", seuil_F1_verification: "Seuil F1 → vérification",
  cout_defaut: "Coût, paramètres par défaut", cout_regle: "Coût, paramètres réglés",
};

function NumberField({ label, help, value, onChange, step, pct, bounds, max }:
  { label: string; help: string; value: number; onChange: (v: number) => void; step: number; pct?: boolean; bounds?: [number, number]; max?: number }) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between gap-2 text-xs"><span className="font-medium">{label}</span>
        <span className="tabular text-muted-foreground">{pct ? fmtPct(value) : value.toLocaleString("fr-FR", { maximumFractionDigits: 2 })}</span></div>
      <input type="range" min={bounds?.[0] ?? 0} max={Math.min(bounds?.[1] ?? 1, max ?? (pct ? 1 : 100))} step={step}
        value={value} onChange={(e) => onChange(+e.target.value)} className="mt-1.5 w-full accent-[hsl(var(--primary))]" />
      <div className="text-[10px] text-muted-foreground">{help}</div>
    </label>
  );
}

function Delta({ a, b, money, lowerIsBetter = true }: { a: number; b: number; money?: boolean; lowerIsBetter?: boolean }) {
  const d = b - a;
  if (Math.abs(d) < (money ? 0.5 : 0.5)) return <span className="text-muted-foreground">=</span>;
  const good = lowerIsBetter ? d < 0 : d > 0;
  return <span className={cn("tabular text-[11px] font-semibold", good ? "text-risk-faible" : "text-risk-critique")}>
    {d > 0 ? "+" : "−"}{money ? fmtUsd(Math.abs(d)) : fmtInt(Math.abs(d))}</span>;
}

export default function PolitiquePage() {
  const me = getUser();
  const canSave = !!me && me.role !== "ANALYSTE";
  const { data: st, reload } = usePolling<PolicyState>("/policy", 0);
  const { data: evaluation } = usePolling<any>("/policy/evaluation", 0);
  const [params, setParams] = useState<Params | null>(null);
  const [days, setDays] = useState<Days>("7");
  const [sim, setSim] = useState<Sim | null>(null);
  const [simErr, setSimErr] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => { if (st && !params) setParams(structuredClone(st.active)); }, [st, params]);
  useEffect(() => {
    if (!params) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try { setSim(await api<Sim>("/policy/simulate", { method: "POST", body: JSON.stringify({ params, days: +days }) })); setSimErr(null); }
      catch (e: any) { setSimErr(e.message); }
    }, 500);
    return () => clearTimeout(timer.current);
  }, [params, days]);

  const dirty = useMemo(() => !!st && !!params && JSON.stringify({ ...params, version: "" }) !== JSON.stringify({ ...st.active, version: "" }), [st, params]);
  const setCost = (scope: "costs" | "operator_overrides", key: string, field: keyof Costs, v: number) =>
    setParams((p) => p && ({ ...p, [scope]: { ...p[scope], [key]: { ...p[scope][key], [field]: v } } }));
  const toggleOverride = (op: string) => setParams((p) => {
    if (!p) return p;
    const o = { ...p.operator_overrides };
    if (o[op]) delete o[op]; else o[op] = { ...p.costs.MOBILE_MONEY };
    return { ...p, operator_overrides: o };
  });

  async function save() {
    if (!params) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api<any>("/policy", { method: "PUT", body: JSON.stringify({ params, note }) });
      setMsg({ ok: true, text: `Politique ${r.version} active${r.published ? " : le scoring l'applique dans les 10 secondes." : " — publication vers le scoring en échec, réessayer."}` });
      setNote(""); setParams(null); reload();
    } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  }

  const c = sim?.current, n = sim?.candidate;
  return (
    <>
      <PageHeader eyebrow="Gouvernance" title="Politique de décision"
        subtitle="Combien coûte une fraude laissée passer, une vérification, un client honnête bloqué ? Réglez ces coûts et voyez leur effet avant de les appliquer.">
        {st && <Pill tone={st.published === false ? "critique" : "faible"}>Active : {st.active.version}{st.published === false ? " (non publiée)" : ""}</Pill>}
      </PageHeader>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* ------------------------------------------------------------ réglages */}
        <Card>
          <CardHeader>
            <div><CardTitle className="flex items-center gap-2"><SlidersHorizontal className="h-4 w-4 text-primary" />Coûts et seuils</CardTitle>
              <CardDescription>Le scoring choisit l&apos;action dont la perte attendue est la plus faible.</CardDescription></div>
            <div className="flex gap-1">
              <Button size="sm" variant="outline" disabled={!st} onClick={() => st && setParams(structuredClone(st.active))} title="Revenir à la politique active"><RotateCcw /></Button>
              <Button size="sm" variant="outline" disabled={!st} onClick={() => st && setParams({ ...structuredClone(st.defaults), version: st.active.version })}>Défauts</Button>
            </div>
          </CardHeader>
          {params && st && (
            <CardContent className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <NumberField label="Plancher de blocage" help="au-delà de cette probabilité : blocage quel que soit le montant" pct step={0.005}
                  value={params.block_floor} bounds={st.bounds.block_floor} onChange={(v) => setParams({ ...params, block_floor: Math.max(0.5, v) })} />
                <NumberField label="Plafond d'approbation directe" help="en deçà : approbation sans calcul de coût" pct step={0.001}
                  value={params.approve_ceiling} bounds={st.bounds.approve_ceiling} onChange={(v) => setParams({ ...params, approve_ceiling: Math.min(0.2, v) })} />
              </div>
              {st.channels.map((ch) => (
                <div key={ch} className="rounded-xl border p-4">
                  <div className="mb-3 text-sm font-semibold">{CHANNEL_LABEL[ch]}</div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {FIELDS.map((f) => <NumberField key={f.key} label={f.label} help={f.help} step={f.step} pct={f.pct} max={f.max} value={params.costs[ch][f.key]} bounds={st.bounds[f.key]}
                      onChange={(v) => setCost("costs", ch, f.key, v)} />)}
                  </div>
                </div>
              ))}
              <div className="rounded-xl border p-4">
                <div className="mb-1 text-sm font-semibold">Coûts propres à un opérateur (Mobile Money)</div>
                <p className="mb-3 text-xs text-muted-foreground">Par exemple un opérateur dont les clients abandonnent davantage une vérification.</p>
                <div className="mb-3 flex flex-wrap gap-2">
                  {st.operators.map((op) => (
                    <button key={op} type="button" onClick={() => toggleOverride(op)}
                      className={cn("rounded-lg border px-3 py-1.5 text-xs font-medium", params.operator_overrides[op] ? "border-primary bg-primary/10 text-primary" : "text-muted-foreground hover:bg-muted")}>
                      {op}{params.operator_overrides[op] ? " · personnalisé" : ""}
                    </button>
                  ))}
                </div>
                {Object.keys(params.operator_overrides).map((op) => (
                  <div key={op} className="mt-3 border-t pt-3">
                    <div className="mb-2 text-xs font-semibold">{op}</div>
                    <div className="grid gap-4 sm:grid-cols-2">
                      {FIELDS.map((f) => <NumberField key={f.key} label={f.label} help={f.help} step={f.step} pct={f.pct} max={f.max} value={params.operator_overrides[op][f.key]} bounds={st.bounds[f.key]}
                        onChange={(v) => setCost("operator_overrides", op, f.key, v)} />)}
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </Card>

        {/* ------------------------------------------------------------ simulation */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <div><CardTitle className="flex items-center gap-2"><Scale className="h-4 w-4 text-primary" />Effet sur les transactions récentes</CardTitle>
                <CardDescription>{sim ? `${fmtInt(sim.n_rows)} transactions rejouées${sim.truncated ? " (les plus récentes)" : ""} ; les deux politiques jugées avec les coûts réglés ici.` : "Simulation…"}</CardDescription></div>
              <Segmented value={days} onChange={setDays} options={[["1", "24 h"], ["7", "7 j"], ["30", "30 j"]]} />
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              {simErr && <p className="rounded-lg bg-risk-critique/10 px-3 py-2 text-xs text-risk-critique">{simErr}</p>}
              {c && n && (
                <>
                  <div className="rounded-xl bg-muted/60 p-3 text-xs">
                    <b className="tabular text-sm">{fmtInt(sim!.changed)}</b> transaction(s) changeraient de décision
                    {Object.entries(sim!.moves).length > 0 && <span className="text-muted-foreground"> · {Object.entries(sim!.moves).map(([k, v]) =>
                      `${k.split("->").map((a) => ACTION_LABEL[a].toLowerCase().replace(/s$/, "")).join(" → ")} : ${fmtInt(v)}`).join(" · ")}</span>}
                  </div>
                  {(["current", "candidate"] as const).map((k) => {
                    const s = k === "current" ? c : n;
                    return (
                      <div key={k}>
                        <div className="mb-1 flex justify-between text-xs"><span className="font-medium">{k === "current" ? "Politique active" : "Politique réglée"}</span>
                          <span className="text-muted-foreground">{["APPROVE", "VERIFY", "BLOCK"].map((a) => `${ACTION_LABEL[a]} ${fmtInt(s.actions[a])}`).join(" · ")}</span></div>
                        <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
                          {["APPROVE", "VERIFY", "BLOCK"].map((a) => <div key={a} className={ACTION_COLOR[a]} style={{ width: `${Math.max(s.shares[a] * 100, s.actions[a] ? 0.6 : 0)}%` }} />)}
                        </div>
                      </div>
                    );
                  })}
                  <table className="w-full text-xs">
                    <thead><tr className="text-muted-foreground"><th className="py-1 text-left font-normal">Perte attendue (modèle)</th><th className="text-right font-normal">Active</th><th className="text-right font-normal">Réglée</th><th className="w-20 text-right font-normal">Écart</th></tr></thead>
                    <tbody className="tabular">
                      {([["fraud_loss", "Fraude non stoppée"], ["friction", "Vérifications"], ["false_block", "Faux blocages"], ["total", "Total"]] as const).map(([key, label]) => (
                        <tr key={key} className={cn("border-t", key === "total" && "font-semibold")}>
                          <td className="py-1.5">{label}</td><td className="text-right">{fmtUsd(c.expected[key])}</td><td className="text-right">{fmtUsd(n.expected[key])}</td>
                          <td className="text-right"><Delta a={c.expected[key]} b={n.expected[key]} money /></td></tr>
                      ))}
                      <tr className="border-t"><td className="py-1.5 text-muted-foreground" colSpan={4}>Réalisée d&apos;après les verdicts ({fmtInt(n.realized.n)} transactions jugées)</td></tr>
                      <tr><td className="py-1">Perte réalisée</td><td className="text-right">{fmtUsd(c.realized.total)}</td><td className="text-right">{fmtUsd(n.realized.total)}</td><td className="text-right"><Delta a={c.realized.total} b={n.realized.total} money /></td></tr>
                      <tr><td className="py-1">Fraudes laissées passer</td><td className="text-right">{fmtInt(c.realized.fraud_missed)}</td><td className="text-right">{fmtInt(n.realized.fraud_missed)}</td><td className="text-right"><Delta a={c.realized.fraud_missed} b={n.realized.fraud_missed} /></td></tr>
                      <tr><td className="py-1">Clients honnêtes bloqués</td><td className="text-right">{fmtInt(c.realized.legit_blocked)}</td><td className="text-right">{fmtInt(n.realized.legit_blocked)}</td><td className="text-right"><Delta a={c.realized.legit_blocked} b={n.realized.legit_blocked} /></td></tr>
                    </tbody>
                  </table>
                </>
              )}
              {canSave ? (
                <div className="space-y-2 border-t pt-4">
                  <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000}
                    placeholder="Justification (obligatoire, 10 caractères minimum) : coûts communiqués par l'opérateur, décision du comité…"
                    className="w-full rounded-lg border bg-card p-3 text-sm focus:border-primary/60 focus:outline-none focus:ring-4 focus:ring-primary/15" />
                  <Button className="w-full" disabled={busy || !dirty || note.trim().length < 10} onClick={save}><Save /> Appliquer cette politique</Button>
                  {!dirty && <p className="text-center text-[11px] text-muted-foreground">Modifiez un réglage pour pouvoir l&apos;appliquer.</p>}
                </div>
              ) : <p className="border-t pt-3 text-xs text-muted-foreground">Simulation libre ; l&apos;application d&apos;une politique est réservée aux superviseurs.</p>}
              {msg && <p className={cn("rounded-lg px-3 py-2 text-xs", msg.ok ? "bg-risk-faible/10 text-risk-faible" : "bg-risk-critique/10 text-risk-critique")}>{msg.text}</p>}
            </CardContent>
          </Card>

          {evaluation?.policies && (
            <Card>
              <CardHeader><div><CardTitle className="flex items-center gap-2"><FlaskConical className="h-4 w-4 text-primary" />Seuil unique ou coût ? (hors ligne)</CardTitle>
                <CardDescription>{fmtInt(evaluation.n_eval)} transactions de test, mêmes coûts métier pour toutes les politiques.</CardDescription></div></CardHeader>
              <CardContent>
                <table className="w-full text-xs"><thead><tr className="text-muted-foreground"><th className="py-1 text-left font-normal">Politique</th><th className="text-right font-normal">Perte</th><th className="text-right font-normal">Fraudes stoppées</th><th className="text-right font-normal">Clients gênés</th></tr></thead>
                  <tbody className="tabular">{Object.entries(evaluation.policies).map(([k, v]: [string, any]) => (
                    <tr key={k} className="border-t"><td className="py-1.5">{POLICY_LABEL[k] ?? k}</td><td className="text-right font-semibold">{fmtUsd(v.total)}</td>
                      <td className="text-right">{fmtPct(v.fraud_stopped_rate)}</td><td className="text-right">{fmtPct(v.legit_friction_rate, 2)}</td></tr>))}</tbody></table>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader><div><CardTitle className="flex items-center gap-2"><History className="h-4 w-4 text-primary" />Historique</CardTitle>
              <CardDescription>Chaque version garde son auteur, sa justification et l&apos;effet simulé.</CardDescription></div></CardHeader>
            <CardContent>
              <ul className="space-y-2 text-xs">
                {st?.history.map((h) => (
                  <li key={h.id} className="rounded-lg border p-2.5">
                    <div className="flex justify-between gap-2"><span className="font-semibold">v{h.id}{h.is_active && <Pill tone="faible" className="ml-2">active</Pill>}</span>
                      <span className="text-muted-foreground">{h.created_by} · {fmtDate(h.created_at)}</span></div>
                    <div className="mt-1">{h.note}</div>
                    {h.simulation && <div className="mt-1 text-muted-foreground">{fmtInt(h.simulation.changed)} décisions changées sur 7 j · perte attendue {fmtUsd(h.simulation.expected_total[0])} → {fmtUsd(h.simulation.expected_total[1])}</div>}
                  </li>
                ))}
                {st && st.history.length === 0 && <li className="text-muted-foreground">Aucun réglage : coûts par défaut.</li>}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
