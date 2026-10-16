"use client";

import { useState } from "react";
import { Building2, Check, Copy, KeyRound, Plus, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/select";
import { api } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { cn, fmtDate, fmtInt } from "@/lib/utils";

const KINDS: [string, string][] = [["OPERATEUR_MM", "Opérateur Mobile Money"], ["BANQUE", "Banque"],
  ["EMETTEUR_CARTE", "Émetteur de cartes"], ["REGULATEUR", "Régulateur (BCC)"]];
const SCOPES: [string, string][] = [["transactions", "Scoring"], ["feedback", "Retour des fraudes"], ["supervision", "Supervision"]];
const PROVIDERS: [string, string][] = [["vodacom", "Vodacom"], ["airtel", "Airtel"], ["orange", "Orange"], ["visa", "Visa"]];
const DEFAULT_SCOPES: Record<string, string[]> = {
  OPERATEUR_MM: ["transactions", "feedback"], BANQUE: ["transactions", "feedback"],
  EMETTEUR_CARTE: ["transactions", "feedback"], REGULATEUR: ["supervision"],
};
const label = (list: [string, string][], v: string) => list.find(([k]) => k === v)?.[1] ?? v;

function Toggle({ options, value, onChange, disabled }: { options: [string, string][]; value: string[]; onChange: (v: string[]) => void; disabled?: boolean }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map(([k, l]) => {
        const on = value.includes(k);
        return (
          <button key={k} type="button" disabled={disabled} onClick={() => onChange(on ? value.filter((x) => x !== k) : [...value, k])}
            className={cn("rounded-md border px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-40",
              on ? "border-primary/40 bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground")}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

/** Clé d'API affichée une seule fois, avec copie. */
function KeyReveal({ data, onClose }: { data: { code: string; name: string; api_key: string; warning: string }; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mb-4 rounded-2xl border border-risk-moyen/40 bg-risk-moyen/10 p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><KeyRound className="h-4 w-4" />Clé d&apos;API de {data.name}</div>
      <p className="mt-1 text-xs text-muted-foreground">{data.warning}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded-lg border bg-card px-3 py-2 font-mono text-xs">{data.api_key}</code>
        <Button size="sm" variant="outline" onClick={() => { navigator.clipboard?.writeText(data.api_key); setCopied(true); }}>
          {copied ? <Check /> : <Copy />}{copied ? "Copiée" : "Copier"}
        </Button>
        <Button size="sm" onClick={onClose}>J&apos;ai transmis la clé</Button>
      </div>
      <p className="mt-3 text-[11px] text-muted-foreground">
        Utilisation : en-tête <code className="font-mono">X-API-Key</code> sur <code className="font-mono">/v1/…</code> · documentation interactive :{" "}
        <a className="text-primary underline-offset-2 hover:underline" href="/v1/docs" target="_blank" rel="noreferrer">/v1/docs</a>
      </p>
    </div>
  );
}

export default function InstitutionsPage() {
  const { data, reload } = usePolling<any[]>("/institutions", 0);
  const [form, setForm] = useState({ code: "", name: "", kind: "BANQUE", scopes: DEFAULT_SCOPES.BANQUE, providers: [] as string[], contact_email: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<any | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      const r = await api<any>("/institutions", { method: "POST", body: JSON.stringify({ ...form, contact_email: form.contact_email || null }) });
      setRevealed(r); setForm({ ...form, code: "", name: "", contact_email: "" }); reload();
    } catch (err: any) { setMsg(err.message); }
  }
  async function rotate(i: any) {
    if (!confirm(`Renouveler la clé de ${i.name} ? L'ancienne clé cessera de fonctionner.`)) return;
    setRevealed(await api<any>(`/institutions/${i.id}/rotate-key`, { method: "POST" })); reload();
  }
  async function toggle(i: any) {
    await api(`/institutions/${i.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !i.is_active }) }); reload();
  }

  return (
    <>
      <PageHeader eyebrow="Gouvernance" title="Institutions partenaires"
        subtitle="Opérateurs, banques, émetteurs de cartes et régulateur qui utilisent le système par l'API." />
      {revealed && <KeyReveal data={revealed} onClose={() => setRevealed(null)} />}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Institution</th><th>Droits</th><th>Clé</th><th className="text-right">Transactions 30 j</th><th>État</th><th /></tr></thead>
              <tbody>
                {(data ?? []).map((i) => (
                  <tr key={i.id} className={cn(!i.is_active && "opacity-60")}>
                    <td>
                      <div className="font-medium">{i.name}</div>
                      <div className="text-xs text-muted-foreground"><code className="font-mono">{i.code}</code> · {label(KINDS, i.kind)}</div>
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {i.scopes.map((s: string) => <Pill key={s} tone={s === "supervision" ? "primary" : "neutral"} dot={false}>{label(SCOPES, s)}</Pill>)}
                        {i.providers.map((p: string) => <Pill key={p} tone="neutral" dot={false}>format {label(PROVIDERS, p)}</Pill>)}
                      </div>
                    </td>
                    <td className="whitespace-nowrap">
                      <code className="font-mono text-xs">{i.key_prefix}…</code>
                      <div className="text-[11px] text-muted-foreground">{i.key_rotated_at ? `renouvelée ${fmtDate(i.key_rotated_at)}` : `créée ${fmtDate(i.created_at)}`}</div>
                    </td>
                    <td className="text-right tabular-nums">
                      {fmtInt(i.volume_30d)}
                      {i.last_transaction_at && <div className="text-[11px] text-muted-foreground">dernière {fmtDate(i.last_transaction_at)}</div>}
                    </td>
                    <td><Pill tone={i.is_active ? "faible" : "neutral"}>{i.is_active ? "Active" : "Révoquée"}</Pill></td>
                    <td className="whitespace-nowrap text-right">
                      <div className="flex justify-end gap-1.5">
                        <Button size="sm" variant="outline" onClick={() => rotate(i)} title="Renouveler la clé"><RefreshCw /></Button>
                        <Button size="sm" variant={i.is_active ? "outline" : "default"} onClick={() => toggle(i)}>{i.is_active ? "Révoquer" : "Réactiver"}</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data && data.length === 0 && (
            <EmptyState icon={<Building2 />} title="Aucune institution">Créez la première institution pour lui délivrer une clé d&apos;API.</EmptyState>
          )}
        </Card>
        <Card className="self-start">
          <CardHeader>
            <div><CardTitle>Nouvelle institution</CardTitle><CardDescription>Une clé d&apos;API est générée et affichée une seule fois.</CardDescription></div>
            <div className="rounded-lg bg-primary/10 p-2 text-primary"><Building2 className="h-4 w-4" /></div>
          </CardHeader>
          <CardContent>
            <form onSubmit={create} className="space-y-3">
              <Input placeholder="Nom (ex. Rawbank)" required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <Input placeholder="Code (ex. rawbank)" required pattern="[a-z0-9][a-z0-9_\-]{1,31}" title="minuscules, chiffres, - et _"
                value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toLowerCase() })} />
              <Select className="w-full" value={form.kind} options={KINDS}
                onChange={(e) => setForm({ ...form, kind: e.target.value, scopes: DEFAULT_SCOPES[e.target.value], providers: e.target.value === "REGULATEUR" ? [] : form.providers })} />
              <div><div className="mb-1.5 text-xs font-medium text-muted-foreground">Droits</div>
                <Toggle options={SCOPES} value={form.scopes} onChange={(scopes) => setForm({ ...form, scopes })} /></div>
              <div><div className="mb-1.5 text-xs font-medium text-muted-foreground">Formats natifs (facultatif : le format commun est toujours disponible)</div>
                <Toggle options={PROVIDERS} value={form.providers} disabled={form.kind === "REGULATEUR"} onChange={(providers) => setForm({ ...form, providers })} /></div>
              <Input placeholder="E-mail du contact technique" type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} />
              <Button type="submit" className="w-full"><Plus /> Créer et générer la clé</Button>
              {msg && <p className="rounded-lg bg-risk-critique/10 px-3 py-2 text-xs text-risk-critique">{msg}</p>}
            </form>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
