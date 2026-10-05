"use client";

import Link from "next/link";
import { ArrowLeft, Atom, BookOpenCheck, BrainCircuit, History, MapPin, Receipt, Scale } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ActionBadge, FraudTypeBadge, Pill, RiskBadge, Tag } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@/components/ui/card";
import { AnalysisResult } from "@/components/message-analyzer";
import { ReviewPanel } from "@/components/review-panel";
import { ProbabilityBar } from "@/components/ui/probability";
import { provinceGeo } from "@/lib/geo";
import { usePolling } from "@/lib/use-polling";
import { cn, FEATURE_LABEL, FRAUD_TYPE_HELP, FRAUD_TYPE_LABEL, fmtDate, fmtPct, fmtUsd } from "@/lib/utils";

const BRANCH_LABEL: Record<string, string> = {
  xgboost: "XGBoost (profil instantané)", lstm_attention: "LSTM + attention (séquence)", autoencoder: "Autoencodeur (anomalie)",
};
const RISK_VAR: Record<string, string> = { CRITIQUE: "--risk-critique", ELEVE: "--risk-eleve", MOYEN: "--risk-moyen", FAIBLE: "--risk-faible" };
const AXIS = { fontSize: 11, fill: "hsl(var(--muted-foreground))" };
const UP = "hsl(var(--risk-critique))", DOWN = "hsl(var(--risk-faible))";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border/70 py-2.5 text-sm last:border-0">
      <span className="text-muted-foreground">{k}</span><span className="text-right font-medium">{v}</span>
    </div>
  );
}

/** Jauge circulaire de la probabilité de fraude. */
function Gauge({ p, level }: { p: number; level: string }) {
  const r = 52, c = 2 * Math.PI * r;
  const color = `hsl(var(${RISK_VAR[level] ?? "--primary"}))`;
  return (
    <div className="relative h-36 w-36 shrink-0">
      <svg viewBox="0 0 128 128" className="h-full w-full -rotate-90">
        <circle cx="64" cy="64" r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth="11" />
        <circle cx="64" cy="64" r={r} fill="none" stroke={color} strokeWidth="11" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.max(0.01, p))} style={{ transition: "stroke-dashoffset .8s cubic-bezier(.2,.7,.2,1)" }} />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div><div className="tabular text-[28px] font-semibold leading-none tracking-tight">{fmtPct(p)}</div>
          <div className="mt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">risque de fraude</div></div>
      </div>
    </div>
  );
}

function Section({ icon, title, desc, children, className }:
  { icon: React.ReactNode; title: string; desc?: string; children: React.ReactNode; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader>
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-primary/10 p-2 text-primary [&_svg]:h-4 [&_svg]:w-4">{icon}</div>
          <div><CardTitle>{title}</CardTitle>{desc && <CardDescription>{desc}</CardDescription>}</div>
        </div>
      </CardHeader>
      {children}
    </Card>
  );
}

export default function TransactionDetail({ params }: { params: { id: string } }) {
  const { data: t, error, reload } = usePolling<any>(`/transactions/${encodeURIComponent(params.id)}`, 0);
  const evidence = usePolling<any>(t ? `/transactions/${encodeURIComponent(params.id)}/evidence` : null, 0);
  const history = usePolling<any[]>(t ? `/transactions/by-user/${encodeURIComponent(t.user_id)}/history?limit=12` : null, 0);

  if (error) return <EmptyState title="Transaction introuvable">{error}</EmptyState>;
  if (!t) return (
    <div className="space-y-4"><div className="skeleton h-8 w-72" /><div className="skeleton h-44 w-full rounded-xl" />
      <div className="grid gap-4 lg:grid-cols-3"><div className="skeleton h-64 rounded-xl" /><div className="skeleton h-64 rounded-xl" /><div className="skeleton h-64 rounded-xl" /></div></div>
  );

  const shap = (t.explanation?.top_features ?? []).map((f: any) => ({
    name: FEATURE_LABEL[f.feature] ?? f.feature, shap: f.shap, value: f.value,
  }));
  const branches = Object.entries(t.explanation?.branch_contributions ?? {}).map(([k, v]) => ({ name: BRANCH_LABEL[k] ?? k, v: v as number }));
  const attention: number[] = t.explanation?.attention_on_history ?? [];
  const maxAtt = Math.max(0.0001, ...attention);
  const geo = provinceGeo(t.province);

  return (
    <>
      <Link href="/transactions" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Transactions
      </Link>

      {/* En-tête : décision */}
      <Card className="relative mb-4 overflow-hidden">
        <div aria-hidden className="absolute inset-y-0 left-0 w-1" style={{ background: `hsl(var(${RISK_VAR[t.risk_level] ?? "--primary"}))` }} />
        <div className="flex flex-wrap items-center gap-6 p-6 pl-8">
          <Gauge p={t.fraud_probability} level={t.risk_level} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2"><RiskBadge level={t.risk_level} /><ActionBadge action={t.action} />
              <FraudTypeBadge type={t.fraud_type} probability={t.fraud_type_probability} />
              {t.degraded && <Pill tone="moyen">Mode dégradé</Pill>}
              {t.label != null && <Pill tone={t.label === 1 ? "critique" : "neutral"}>{t.label === 1 ? "Fraude confirmée" : "Faux positif"}</Pill>}</div>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight">{fmtUsd(t.amount_usd)} <span className="text-base font-normal text-muted-foreground">· {t.tx_type}</span></h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Client <span className="font-medium text-foreground">{t.user_id}</span> · {fmtDate(t.tx_time)} (heure RDC) · <span className="font-mono text-xs">{t.transaction_id}</span>
            </p>
            <p className="mt-3 max-w-2xl rounded-lg bg-muted/60 px-3 py-2 text-sm">{t.reason}</p>
            {t.label == null && <ReviewPanel transactionId={t.transaction_id} onDone={reload} />}
            {t.explanation?.text_analysis && (
              <div className="mt-2 max-w-2xl rounded-lg border bg-muted/30 px-3 py-2.5">
                <div className="mb-1.5 text-xs font-semibold">Analyse du message du transfert{t.explanation.fraud_type_source === "texte" && " (a déterminé le type de fraude)"}</div>
                <AnalysisResult a={t.explanation.text_analysis} />
              </div>
            )}
            {t.fraud_type && (
              <p className="mt-2 max-w-2xl text-sm">
                <span className="font-medium">Typologie probable : {FRAUD_TYPE_LABEL[t.fraud_type] ?? t.fraud_type}.</span>{" "}
                <span className="text-muted-foreground">{FRAUD_TYPE_HELP[t.fraud_type]}</span>
                {(t.explanation?.fraud_type_candidates ?? []).length > 1 && (
                  <span className="mt-1 block text-xs text-muted-foreground">
                    Autres hypothèses : {(t.explanation.fraud_type_candidates as any[]).slice(1).map((c) =>
                      `${FRAUD_TYPE_LABEL[c.type] ?? c.type} (${Math.round(c.probability * 100)} %)`).join(", ")}
                  </span>
                )}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
            {[["Latence", `${t.latency_ms.toFixed(1)} ms`], ["Modèle", t.model_version],
              ["Règles", t.rules_triggered.length || "aucune"], ["Verdict", t.label == null ? "non traité" : t.label === 1 ? "fraude" : "légitime"]]
              .map(([k, v]) => <div key={k as string}><div className="text-xs text-muted-foreground">{k}</div><div className="tabular max-w-[160px] truncate font-medium">{v}</div></div>)}
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Section icon={<Receipt />} title="Opération">
          <CardContent>
            <Row k="Canal" v={t.channel === "VISA_VIRTUAL" ? "Carte Visa virtuelle" : `Mobile Money · ${t.operator}`} />
            <Row k="Accès" v={<Tag>{t.access_channel}</Tag>} />
            <Row k="Montant" v={`${t.amount.toLocaleString("fr-FR")} ${t.currency}`} />
            <Row k="Localisation" v={
              <Link href={`/carte?province=${encodeURIComponent(t.province)}`} className="inline-flex items-center gap-1 text-primary hover:underline">
                <MapPin className="h-3.5 w-3.5" />{t.province}{geo && ` · ${geo.capital}`}
              </Link>} />
            <Row k="Appareil" v={<span className="font-mono text-xs">{t.device_id}</span>} />
            {t.counterparty_id && <Row k="Destinataire" v={t.counterparty_id} />}
            {t.agent_id && <Row k="Agent" v={t.agent_id} />}
            {t.merchant_id && <Row k="Marchand" v={t.merchant_id} />}
            {t.rules_triggered.length > 0 && <Row k="Règles déclenchées" v={t.rules_triggered.join(", ")} />}
          </CardContent>
        </Section>

        <Section icon={<Scale />} title="Modèle hybride" desc="Contribution de chaque branche (log-odds)">
          <CardContent className="h-60">
            <ResponsiveContainer>
              <BarChart data={branches} layout="vertical" margin={{ left: 0, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="hsl(var(--border))" />
                <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
                <YAxis type="category" dataKey="name" width={140} tick={AXIS} tickLine={false} axisLine={false} />
                <ReferenceLine x={0} stroke="hsl(var(--muted-foreground))" />
                <Tooltip cursor={{ fill: "hsl(var(--muted))" }} formatter={(v: number) => v.toFixed(3)} />
                <Bar dataKey="v" name="Contribution" radius={4} barSize={16}>
                  {branches.map((b, i) => <Cell key={i} fill={b.v > 0 ? UP : DOWN} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Section>

        <Section icon={<History />} title="Attention du LSTM" desc="Poids donnés aux opérations précédentes du client">
          <CardContent>
            {attention.length ? (
              <div className="flex h-44 items-end gap-1.5">
                {attention.map((w, i) => (
                  <div key={i} className="flex h-full flex-1 flex-col items-center gap-1.5">
                    <div className="flex w-full flex-1 items-end">
                      <div className="w-full rounded-md bg-gradient-to-t from-primary to-accent transition-all" title={w.toFixed(3)}
                        style={{ height: `${Math.max(4, (w / maxAtt) * 100)}%`, opacity: 0.35 + 0.65 * (w / maxAtt) }} />
                    </div>
                    <span className="tabular text-[10px] text-muted-foreground">{i === attention.length - 1 ? "act." : `-${attention.length - 1 - i}`}</span>
                  </div>
                ))}
              </div>
            ) : <EmptyState title="Pas d'historique" />}
            <p className="mt-3 text-[11px] text-muted-foreground">-1 = l&apos;opération précédente, act. = celle-ci.</p>
          </CardContent>
        </Section>

        <Section icon={<BrainCircuit />} title="Pourquoi cette décision ?" desc="Variables les plus influentes (SHAP, branche XGBoost) — rouge : vers la fraude, vert : vers la normale" className="lg:col-span-3">
          <CardContent className={cn(shap.length && "h-80")}>
            {shap.length ? (
              <ResponsiveContainer>
                <BarChart data={shap} layout="vertical" margin={{ left: 0, right: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="hsl(var(--border))" />
                  <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
                  <YAxis type="category" dataKey="name" width={260} tick={AXIS} tickLine={false} axisLine={false} />
                  <ReferenceLine x={0} stroke="hsl(var(--muted-foreground))" />
                  <Tooltip cursor={{ fill: "hsl(var(--muted))" }} formatter={(v: number, _n, p: any) => [`${v.toFixed(3)} (valeur : ${p.payload.value})`, "Contribution"]} />
                  <Bar dataKey="shap" radius={4} barSize={14}>
                    {shap.map((s: any, i: number) => <Cell key={i} fill={s.shap > 0 ? UP : DOWN} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : <EmptyState icon={<BrainCircuit />} title="Explication non calculée">L&apos;explication détaillée n&apos;est produite qu&apos;à partir d&apos;un risque moyen.</EmptyState>}
          </CardContent>
        </Section>

        {t.explanation?.physics && (() => {
          const ph = t.explanation.physics;
          const violated: string[] = ph.violated ?? [];
          const effect = ph.mode === "enforce" ? "la décision en tient compte" : ph.mode === "shadow" ? "information seule : sans effet sur la décision" : "";
          return (
            <Section icon={<Atom />} title="Lois physiques" className="lg:col-span-3"
              desc="Ce qui est impossible quel que soit le comportement du client, en complément du modèle de données">
              <CardContent>
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <Pill tone={violated.length ? (ph.severe ? "critique" : "moyen") : "faible"}>
                    {violated.length ? (ph.severe ? "Loi physique nettement violée" : "Loi physique à la limite") : "Lois respectées"}
                  </Pill>
                  {effect && <span className="text-xs text-muted-foreground">{effect}</span>}
                </div>
                <div className="grid gap-x-10 md:grid-cols-2">
                  <Row k="Déplacement depuis la dernière opération" v={ph.travel.km > 0 ? `${ph.travel.km.toLocaleString("fr-FR")} km` : "même province ou inconnu"} />
                  <Row k="Vitesse requise" v={ph.travel.km > 0 ? `${Math.round(ph.travel.required_kmh).toLocaleString("fr-FR")} km/h` : "—"} />
                  <Row k="Dépassement du possible (cinématique)" v={ph.travel.infeasibility > 0 ? `×${(1 + ph.travel.infeasibility).toFixed(1)} la borne physique` : "aucun"} />
                  <Row k="Débit supérieur au solde (conservation)" v={ph.balance.overdraft > 0 ? fmtPct(ph.balance.overdraft) : "aucun"} />
                  <Row k="Temps avant vidage au débit actuel" v={ph.balance.time_to_empty_h >= 1e4 ? "—" : `${ph.balance.time_to_empty_h.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} h`} />
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground">
                  Bornes : route 80 km/h, avion 800 km/h avec 2 h de formalités ; positions au chef-lieu de la province transmise par l&apos;opérateur.
                </p>
              </CardContent>
            </Section>
          );
        })()}

        <Section icon={<BookOpenCheck />} title="Éléments de preuve (RAG)" className="lg:col-span-3"
          desc="Cas passés les plus proches avec leur verdict, et fiche de la typologie : une vérification indépendante de la décision du modèle">
          <CardContent>
            {evidence.error && <p className="text-sm text-muted-foreground">Preuves indisponibles : {evidence.error}</p>}
            {!evidence.data && !evidence.error && <div className="skeleton h-24 w-full" />}
            {evidence.data && (() => {
              const ev = evidence.data;
              const tone = ev.reliability === "ELEVEE" ? "faible" : ev.reliability === "A_VERIFIER" ? "critique" : "moyen";
              const label = ev.reliability === "ELEVEE" ? "Décision confortée" : ev.reliability === "A_VERIFIER" ? "À vérifier manuellement" : "Comparaison peu concluante";
              return (
                <div className="space-y-5">
                  <div>
                    <div className="mb-2 flex flex-wrap items-center gap-2"><Pill tone={tone}>{label}</Pill>
                      <span className="text-xs text-muted-foreground">{ev.index_size.toLocaleString("fr-FR")} cas en mémoire</span></div>
                    <p className="max-w-4xl text-sm leading-relaxed">{ev.summary}</p>
                  </div>
                  <div className="overflow-x-auto rounded-lg border">
                    <table className="tbl">
                      <thead><tr><th>Cas proche</th><th>Opération</th><th>Verdict</th><th className="num">Montant</th><th className="num">Similarité</th><th>Source</th></tr></thead>
                      <tbody>
                        {ev.neighbors.map((n: any) => (
                          <tr key={n.id}>
                            <td className="whitespace-nowrap font-mono text-xs">{n.id}</td>
                            <td className="whitespace-nowrap text-xs">{n.tx_type}</td>
                            <td className="whitespace-nowrap">{n.label === 1 ? <FraudTypeBadge type={n.fraud_type ?? "NON_DETERMINEE"} /> : <Pill tone="faible">Légitime</Pill>}</td>
                            <td className="num whitespace-nowrap text-xs">{fmtUsd(n.amount_usd)}</td>
                            <td className="num whitespace-nowrap text-xs">{(n.similarity * 100).toFixed(0)} %</td>
                            <td className="whitespace-nowrap text-xs text-muted-foreground">{n.source}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="grid gap-3 md:grid-cols-3">
                    {ev.knowledge.map((k: any) => (
                      <div key={k.source + k.section} className="min-w-0 rounded-lg border bg-muted/30 px-4 py-3.5">
                        <div className="mb-2 text-xs font-semibold leading-snug">{k.title}<span className="block font-normal text-muted-foreground">{k.section}</span></div>
                        <div className="space-y-1.5 break-words text-xs leading-relaxed text-muted-foreground">
                          {String(k.text).split("\n").filter(Boolean).map((line: string, i: number) => (
                            <p key={i} className={line.startsWith("- ") ? "pl-3 -indent-3" : ""}>{line.startsWith("- ") ? `• ${line.slice(2)}` : line}</p>
                          ))}
                        </div>
                        <div className="mt-2.5 border-t pt-2 text-[10px] text-muted-foreground/70">Source : {k.source}</div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </CardContent>
        </Section>

        <Card className="overflow-hidden lg:col-span-3">
          <CardHeader><div><CardTitle>Historique récent du client</CardTitle><CardDescription>12 dernières opérations de {t.user_id}</CardDescription></div></CardHeader>
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Heure</th><th>Opération</th><th>Accès</th><th>Province</th><th className="num">Montant</th><th className="num">P(fraude)</th><th>Décision</th></tr></thead>
              <tbody>
                {(history.data ?? []).map((h) => (
                  <tr key={h.transaction_id} className={cn(h.transaction_id === t.transaction_id && "!bg-primary/[.07] shadow-[inset_3px_0_0_hsl(var(--primary))]")}>
                    <td className="whitespace-nowrap text-xs">
                      {h.transaction_id === t.transaction_id ? fmtDate(h.tx_time)
                        : <Link href={`/transactions/${h.transaction_id}`} className="hover:text-primary hover:underline">{fmtDate(h.tx_time)}</Link>}
                    </td>
                    <td className="text-xs">{h.tx_type}</td><td><Tag>{h.access_channel}</Tag></td><td className="text-xs">{h.province}</td>
                    <td className="num font-medium">{fmtUsd(h.amount_usd)}</td>
                    <td><ProbabilityBar p={h.fraud_probability} level={h.risk_level} /></td>
                    <td><ActionBadge action={h.action} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
