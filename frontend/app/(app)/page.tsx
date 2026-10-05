"use client";

import Link from "next/link";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ArrowRight, Ban, Banknote, FolderOpen, Gauge, Inbox, ShieldAlert, Zap } from "lucide-react";
import { LiveDot, PageHeader } from "@/components/app-shell";
import { ActionBadge, RiskBadge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@/components/ui/card";
import { ContinuousLearning } from "@/components/continuous-learning";
import { Segmented } from "@/components/ui/select";
import { Stat } from "@/components/ui/stat";
import { usePolling } from "@/lib/use-polling";
import { FRAUD_TYPE_LABEL, fmtDate, fmtInt, fmtPct, fmtUsd } from "@/lib/utils";

type Window = "15" | "60" | "1440" | "10080";
const WINDOWS: [Window, string][] = [["15", "15 min"], ["60", "1 h"], ["1440", "24 h"], ["10080", "7 j"]];
const BUCKET: Record<Window, number> = { "15": 15, "60": 60, "1440": 900, "10080": 3600 };
const AXIS = { fontSize: 11, fill: "hsl(var(--muted-foreground))" };

export default function Dashboard() {
  const [minutes, setMinutes] = useState<Window>("60");
  const kpis = usePolling<any>(`/reports/kpis?minutes=${minutes}`);
  const series = usePolling<any[]>(`/reports/timeseries?minutes=${minutes}&bucket_seconds=${BUCKET[minutes]}`, 5000);
  const byOperator = usePolling<any[]>(`/reports/breakdown?dimension=operator&minutes=${minutes}`, 10000);
  const byType = usePolling<any[]>(`/reports/breakdown?dimension=tx_type&minutes=${minutes}`, 10000);
  const byProvince = usePolling<any[]>(`/reports/breakdown?dimension=province&minutes=${minutes}`, 10000);
  const byFraudType = usePolling<any[]>(`/reports/fraud-types?minutes=${minutes}`, 10000);
  const alerts = usePolling<any>(`/transactions?alerts_only=true&size=8`);
  const k = kpis.data;
  const chart = (series.data ?? []).map((r) => ({
    t: new Date(r.bucket).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: minutes === "15" ? "2-digit" : undefined }),
    Approuvées: r.volume - r.verified - r.blocked, "À vérifier": r.verified, Bloquées: r.blocked,
  }));
  const types = (byType.data ?? []).map((r) => ({ ...r, rate: r.volume ? r.alerts / r.volume : 0 }));
  const maxRate = Math.max(0.0001, ...types.map((r) => r.rate));
  const provinces = [...(byProvince.data ?? [])].filter((r) => r.alerts > 0).sort((a, b) => b.alerts - a.alerts).slice(0, 5);
  const maxProv = Math.max(1, ...provinces.map((r) => r.alerts));

  return (
    <>
      <PageHeader eyebrow="Supervision" title="Tableau de bord" subtitle="Transactions scorées par le modèle hybride, décisions et alertes en temps réel.">
        <LiveDot error={kpis.error} />
        <Segmented value={minutes} onChange={setMinutes} options={WINDOWS} />
      </PageHeader>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
        <Stat label="Transactions scorées" icon={<Zap />} value={k ? fmtInt(k.volume) : undefined} hint={k && `${fmtUsd(k.amount_usd)} traités`} />
        <Stat label="Taux d'alerte" icon={<ShieldAlert />} tone="warn" value={k ? fmtPct(k.alert_rate, 2) : undefined}
          hint={k && `${fmtInt(k.verified)} à vérifier · ${fmtInt(k.blocked)} bloquées`} />
        <Stat label="Montant bloqué" icon={<Ban />} tone="danger" value={k ? fmtUsd(k.amount_blocked_usd) : undefined}
          hint={k && `${fmtInt(k.blocked)} transaction(s)`} />
        <Stat label="En vérification" icon={<Banknote />} tone="accent" value={k ? fmtUsd(k.amount_verified_usd) : undefined}
          hint={k && `${fmtInt(k.verified)} transaction(s)`} />
        <Stat label="Latence du scoring" icon={<Gauge />} tone="success" value={k ? `${k.latency_avg_ms.toFixed(1)} ms` : undefined}
          hint={k && `p95 : ${k.latency_p95_ms.toFixed(1)} ms`} />
        <Stat label="Dossiers à traiter" icon={<FolderOpen />} value={k ? fmtInt((k.cases?.OUVERT ?? 0) + (k.cases?.EN_COURS ?? 0)) : undefined}
          hint={k && `${fmtInt(k.cases?.FRAUDE_CONFIRMEE ?? 0)} fraudes confirmées`} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <div><CardTitle>Flux de transactions et décisions</CardTitle><CardDescription>Volume par intervalle, empilé par décision du modèle</CardDescription></div>
          </CardHeader>
          <CardContent className="h-72">
            {chart.length ? (
              <ResponsiveContainer>
                <AreaChart data={chart} margin={{ left: -14, right: 8, top: 4 }}>
                  <defs>
                    {[["ok", "--risk-faible"], ["verify", "--risk-moyen"], ["block", "--risk-critique"]].map(([id, v]) => (
                      <linearGradient key={id} id={`g-${id}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={`hsl(var(${v}))`} stopOpacity={0.45} />
                        <stop offset="100%" stopColor={`hsl(var(${v}))`} stopOpacity={0.03} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                  <XAxis dataKey="t" tick={AXIS} tickLine={false} axisLine={false} minTickGap={28} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip cursor={{ stroke: "hsl(var(--muted-foreground))", strokeDasharray: "3 3" }} />
                  <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                  <Area type="monotone" dataKey="Approuvées" stackId="1" stroke="hsl(var(--risk-faible))" strokeWidth={2} fill="url(#g-ok)" />
                  <Area type="monotone" dataKey="À vérifier" stackId="1" stroke="hsl(var(--risk-moyen))" strokeWidth={2} fill="url(#g-verify)" />
                  <Area type="monotone" dataKey="Bloquées" stackId="1" stroke="hsl(var(--risk-critique))" strokeWidth={2} fill="url(#g-block)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <EmptyState icon={<Inbox />} title="Pas encore de trafic">Lancez le simulateur pour voir le flux en direct.</EmptyState>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><div><CardTitle>Alertes par opérateur</CardTitle><CardDescription>Alertes et blocages sur la période</CardDescription></div></CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer>
              <BarChart data={byOperator.data ?? []} layout="vertical" margin={{ left: 4, right: 12 }} barGap={3}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="hsl(var(--border))" />
                <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
                <YAxis type="category" dataKey="key" tick={AXIS} tickLine={false} axisLine={false} width={70} />
                <Tooltip cursor={{ fill: "hsl(var(--muted))" }} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="alerts" name="Alertes" fill="hsl(var(--risk-eleve))" radius={[0, 6, 6, 0]} barSize={10} />
                <Bar dataKey="blocked" name="Bloquées" fill="hsl(var(--risk-critique))" radius={[0, 6, 6, 0]} barSize={10} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="overflow-hidden xl:col-span-2">
          <CardHeader>
            <div><CardTitle>Dernières alertes</CardTitle><CardDescription>Transactions à vérifier ou bloquées, les plus récentes d&apos;abord</CardDescription></div>
            <Link href="/alertes" className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">Dossiers <ArrowRight className="h-3.5 w-3.5" /></Link>
          </CardHeader>
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Scorée à</th><th>Client</th><th>Opération</th><th className="num">Montant</th><th className="num">Probabilité</th><th>Risque</th><th>Décision</th></tr></thead>
              <tbody>
                {(alerts.data?.items ?? []).map((t: any) => (
                  <tr key={t.transaction_id}>
                    <td className="whitespace-nowrap text-xs text-muted-foreground">{fmtDate(t.scored_at)}</td>
                    <td><Link className="font-medium text-primary hover:underline" href={`/transactions/${t.transaction_id}`}>{t.user_id}</Link></td>
                    <td className="text-xs">{t.tx_type}<div className="text-muted-foreground">{t.operator ?? "Visa"} · {t.province}</div></td>
                    <td className="num font-medium">{fmtUsd(t.amount_usd)}</td>
                    <td className="num">{fmtPct(t.fraud_probability)}</td>
                    <td><RiskBadge level={t.risk_level} /></td>
                    <td><ActionBadge action={t.action} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {alerts.data && alerts.data.items.length === 0 && <EmptyState icon={<ShieldAlert />} title="Aucune alerte">Lancez le simulateur pour générer du trafic.</EmptyState>}
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <div><CardTitle>Provinces les plus touchées</CardTitle><CardDescription>Nombre d&apos;alertes</CardDescription></div>
              <Link href="/carte" className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">Carte <ArrowRight className="h-3.5 w-3.5" /></Link>
            </CardHeader>
            <CardContent className="space-y-3">
              {provinces.map((r, i) => (
                <Link key={r.key} href={`/carte?province=${encodeURIComponent(r.key)}`} className="group block">
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2"><span className="tabular w-3 text-muted-foreground">{i + 1}</span><span className="font-medium group-hover:text-primary">{r.key}</span></span>
                    <span className="tabular text-muted-foreground">{fmtInt(r.alerts)}</span>
                  </div>
                  <div className="ml-5 mt-1.5 h-1.5 rounded-full bg-muted">
                    <div className="h-1.5 rounded-full bg-gradient-to-r from-primary to-accent" style={{ width: `${(r.alerts / maxProv) * 100}%` }} />
                  </div>
                </Link>
              ))}
              {byProvince.data && provinces.length === 0 && <p className="py-4 text-center text-xs text-muted-foreground">Aucune alerte sur la période.</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><div><CardTitle>Fraudes par typologie</CardTitle><CardDescription>Type de fraude le plus probable, alertes de la période</CardDescription></div></CardHeader>
            <CardContent className="space-y-3">
              {(byFraudType.data ?? []).map((r) => (
                <Link key={r.fraud_type} href={r.fraud_type === "NON_DETERMINEE" ? "/alertes" : `/transactions?fraud_type=${r.fraud_type}`} className="group block">
                  <div className="flex justify-between text-xs"><span className="font-medium group-hover:text-primary">{FRAUD_TYPE_LABEL[r.fraud_type] ?? r.fraud_type}</span><span className="tabular text-muted-foreground">{fmtInt(r.frauds)} · {fmtUsd(r.amount_usd)}</span></div>
                  <div className="mt-1.5 h-1.5 rounded-full bg-muted"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${(r.frauds / Math.max(...(byFraudType.data ?? []).map((x) => x.frauds), 1)) * 100}%` }} /></div>
                </Link>
              ))}
              {byFraudType.data && byFraudType.data.length === 0 && <p className="py-4 text-center text-xs text-muted-foreground">Aucune fraude sur la période.</p>}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><div><CardTitle>Taux d&apos;alerte par opération</CardTitle><CardDescription>Barres relatives au taux le plus élevé</CardDescription></div></CardHeader>
            <CardContent className="space-y-3">
              {types.map((r) => (
                <div key={r.key}>
                  <div className="flex justify-between text-xs"><span className="font-medium">{r.key}</span><span className="tabular text-muted-foreground">{fmtPct(r.rate, 2)} · {fmtInt(r.volume)}</span></div>
                  <div className="mt-1.5 h-1.5 rounded-full bg-muted"><div className="h-1.5 rounded-full bg-risk-eleve" style={{ width: `${(r.rate / maxRate) * 100}%` }} /></div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
      <ContinuousLearning />
    </>
  );
}
