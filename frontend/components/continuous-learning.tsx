"use client";

import Link from "next/link";
import { useState } from "react";
import { BrainCog, RefreshCw } from "lucide-react";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, getUser } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { FRAUD_TYPE_LABEL, fmtDate, fmtInt, fmtUsd } from "@/lib/utils";

const VERDICT: Record<string, { label: string; tone: "faible" | "moyen" | "critique" | "neutral" }> = {
  SAIN: { label: "Sain", tone: "faible" }, SOUS_APPRENTISSAGE: { label: "Peut encore apprendre", tone: "moyen" },
  SURAPPRENTISSAGE_LEGER: { label: "Surapprentissage léger", tone: "moyen" }, SURAPPRENTISSAGE_NET: { label: "Surapprentissage net", tone: "critique" },
  INCONNU: { label: "Inconnu", tone: "neutral" },
};
const BRANCH: Record<string, string> = { xgboost: "XGBoost", lstm_attention: "LSTM + attention", autoencoder: "Autoencodeur" };

/** Courbes de perte d'entraînement (trait plein) et de validation (pointillé) d'une branche. */
function Curve({ train, val }: { train: number[]; val: number[] }) {
  const all = [...train, ...val], lo = Math.min(...all), hi = Math.max(...all), n = Math.max(train.length, 2);
  const pts = (a: number[]) => a.map((v, i) => `${(i / (n - 1)) * 100},${28 - ((v - lo) / Math.max(hi - lo, 1e-9)) * 26}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" className="h-8 w-full" preserveAspectRatio="none" aria-hidden>
      <polyline points={pts(train)} fill="none" stroke="hsl(var(--primary))" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
      <polyline points={pts(val)} fill="none" stroke="hsl(var(--risk-eleve))" strokeWidth="1.6" strokeDasharray="3 2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

const STATUS: Record<string, { label: string; tone: "faible" | "moyen" | "critique" | "neutral" | "primary" }> = {
  DEMANDEE: { label: "Demandé", tone: "primary" }, EN_ATTENTE: { label: "En attente de données", tone: "moyen" },
  CHAMPION: { label: "Nouveau modèle promu", tone: "faible" }, CHALLENGER: { label: "Meilleur, non promu", tone: "faible" },
  REJETE: { label: "Rejeté (pas meilleur)", tone: "neutral" }, IGNORE: { label: "Ignoré", tone: "neutral" },
  ERREUR: { label: "Erreur", tone: "critique" },
};

function Gauge({ label, value, goal, hint }: { label: string; value: number; goal: number; hint?: string }) {
  const pct = Math.min(100, (value / Math.max(goal, 1)) * 100);
  return (
    <div>
      <div className="flex justify-between text-xs"><span className="font-medium">{label}</span>
        <span className="tabular text-muted-foreground">{fmtInt(value)} / {fmtInt(goal)}</span></div>
      <div className="mt-1.5 h-1.5 rounded-full bg-muted">
        <div className={pct >= 100 ? "h-1.5 rounded-full bg-risk-faible" : "h-1.5 rounded-full bg-primary"} style={{ width: `${pct}%` }} />
      </div>
      {hint && <div className="mt-1 text-[10px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

/** Apprentissage continu : pourquoi le modèle va (ou ne va pas) être réentraîné, et ce qu'il faut pour l'aider. */
export function ContinuousLearning() {
  const st = usePolling<any>("/retraining/status", 15000);
  const novel = usePolling<any>("/retraining/novel-behaviors?limit=5", 30000);
  const me = getUser();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const canTrigger = !!me && me.role !== "ANALYSTE";
  const s = st.data?.signals, d = s?.decision;

  async function trigger() {
    if (!confirm("Lancer un réentraînement maintenant ? Le nouveau modèle ne sera promu que s'il est meilleur que l'actuel.")) return;
    setBusy(true); setMsg(null);
    try {
      await api("/retraining/trigger", { method: "POST" });
      setMsg("Demande enregistrée : prise en charge en moins d'une minute.");
      st.reload();
    } catch (e: any) { setMsg(e.message); } finally { setBusy(false); }
  }

  return (
    <Card className="mt-4">
      <CardHeader>
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-primary/10 p-2 text-primary [&_svg]:h-4 [&_svg]:w-4"><BrainCog /></div>
          <div>
            <CardTitle>Apprentissage continu</CardTitle>
            <CardDescription>
              {st.data?.champion ? `Modèle actuel : ${st.data.champion.version}` : "Modèle d'origine (aucun réentraînement promu)"}
            </CardDescription>
          </div>
        </div>
        {canTrigger && (
          <Button size="sm" variant="outline" disabled={busy || st.data?.pending_request} onClick={trigger}>
            <RefreshCw />Réentraîner maintenant
          </Button>
        )}
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4">
          {!s && <p className="text-sm text-muted-foreground">En attente du premier relevé du planificateur…</p>}
          {s && (
            <>
              <div className="flex flex-wrap gap-1.5">
                <Pill tone={s.drift_alarm ? "critique" : "faible"}>{s.drift_alarm ? "Dérive détectée" : "Pas de dérive"}</Pill>
                <Pill tone={s.novelty_alarm ? "critique" : "faible"}>
                  {s.novelty_alarm ? "Nouveaux comportements" : "Comportements connus"}
                  {s.novelty_rate != null && ` · ${(s.novelty_rate * 100).toFixed(1)} %`}
                </Pill>
              </div>
              <Gauge label="Nouvelles étiquettes" value={s.new_labels} goal={s.thresholds.new_labels}
                hint="verdicts d'analystes et plaintes depuis le dernier entraînement" />
              <Gauge label="Données étiquetées" value={Math.min(s.labeled_total + s.matured_unlabeled, s.thresholds.min_labeled)}
                goal={s.thresholds.min_labeled} hint="minimum pour entraîner" />
              <Gauge label="Fraudes confirmées" value={s.frauds_total} goal={s.thresholds.min_frauds}
                hint="minimum pour entraîner : les analystes les apportent" />
              <p className="text-xs text-muted-foreground">
                {d?.reasons?.length ? `Raisons actuelles : ${d.reasons.join(", ")}. ` : "Aucune raison de réentraîner pour l'instant. "}
                {d && !d.ready && "Il manque des données étiquetées pour lancer l'entraînement."}
                {d?.cooldown && " Repos en cours après un entraînement récent."}
              </p>
            </>
          )}
          {msg && <p className="text-xs text-primary">{msg}</p>}
          {st.data?.training_diagnostics && (
            <div className="border-t pt-3">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Courbes d&apos;apprentissage</div>
              <ul className="space-y-2">
                {Object.entries(st.data.training_diagnostics).filter(([, v]: any) => v && v.verdict).map(([k, v]: any) => (
                  <li key={k} title={v.reason}>
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-medium">{BRANCH[k] ?? k}</span>
                      <Pill tone={VERDICT[v.verdict]?.tone ?? "neutral"} dot={false}>{VERDICT[v.verdict]?.label ?? v.verdict}</Pill>
                    </div>
                    {v.curve && <Curve train={v.curve.train} val={v.curve.val} />}
                    <div className="tabular text-[10px] text-muted-foreground">
                      perte entraînement {v.train_loss_at_best} · validation {v.val_loss_at_best} · écart {(v.generalization_gap * 100).toFixed(0)} %
                    </div>
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[10px] text-muted-foreground">Trait plein : entraînement ; pointillé : validation (données jamais vues).</p>
            </div>
          )}
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Journal</div>
          <ul className="space-y-2">
            {(st.data?.events ?? []).slice(0, 5).map((e: any) => (
              <li key={e.id} className="rounded-lg border bg-muted/30 px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <Pill tone={STATUS[e.status]?.tone ?? "neutral"}>{STATUS[e.status]?.label ?? e.status}</Pill>
                  <span className="text-muted-foreground">{fmtDate(e.ts)}</span>
                </div>
                <div className="mt-1 text-muted-foreground">
                  {e.trigger === "MANUEL" ? `Demande de ${e.requested_by}` : (e.reasons ?? []).join(", ")}
                </div>
                {e.detail?.manque && (
                  <div className="mt-0.5 text-[11px]">
                    Manque : {fmtInt(e.detail.manque.etiquettes)} étiquettes, {fmtInt(e.detail.manque.fraudes_confirmees)} fraudes confirmées
                  </div>
                )}
                {e.detail?.diagnostics && (
                  <div className="mt-0.5 text-[11px] text-muted-foreground">Courbes : {e.detail.diagnostics.worst ? (VERDICT[e.detail.diagnostics.worst]?.label ?? e.detail.diagnostics.worst) : "—"}</div>
                )}
                {e.detail?.challenger && (
                  <div className="tabular mt-0.5 text-[11px]">PR-AUC {e.detail.champion?.pr_auc} → {e.detail.challenger.pr_auc}</div>
                )}
              </li>
            ))}
            {st.data && st.data.events.length === 0 && <li className="text-xs text-muted-foreground">Aucun événement pour l&apos;instant.</li>}
          </ul>
        </div>

        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Comportements nouveaux à examiner</div>
          <ul className="space-y-1.5">
            {(novel.data?.items ?? []).map((t: any) => (
              <li key={t.transaction_id}>
                <Link href={`/transactions/${t.transaction_id}`}
                  className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-xs transition-colors hover:border-primary/40">
                  <span className="min-w-0">
                    <span className="block truncate font-mono text-[11px]">{t.transaction_id}</span>
                    <span className="text-muted-foreground">
                      {t.tx_type} · {t.province} · {fmtUsd(t.amount_usd)}
                      {t.fraud_type && ` · ${FRAUD_TYPE_LABEL[t.fraud_type] ?? t.fraud_type}`}
                    </span>
                  </span>
                  <span className="tabular shrink-0 text-muted-foreground">{t.novelty.toFixed(1)}</span>
                </Link>
              </li>
            ))}
            {novel.data && novel.data.items.length === 0 && <li className="text-xs text-muted-foreground">Rien à examiner.</li>}
          </ul>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Score d&apos;étrangeté de l&apos;autoencodeur
            {novel.data?.threshold != null && ` (seuil de nouveauté : ${novel.data.threshold.toFixed(1)})`}.
            Votre verdict sur ces cas apprend au modèle ce qu&apos;il ne connaît pas encore.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
