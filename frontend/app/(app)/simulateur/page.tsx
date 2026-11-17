"use client";

import { useState } from "react";
import { Play, Radio, Square } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Segmented } from "@/components/ui/select";
import { Stat } from "@/components/ui/stat";
import { api, getUser } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { fmtInt } from "@/lib/utils";

type SimStatus = {
  running: boolean; mode: "trafic" | "fraude" | null; rate: number | null; count: number | null;
  started_at: number | null; ended_at: number | null; exit_code: number | null; alerts: number; log: string[];
};
type Mode = "trafic" | "fraude";

const MODE_HELP: Record<Mode, string> = {
  trafic: "Trafic mixte des 4 opérateurs (Vodacom, Airtel, Orange, Visa), à la cadence choisie.",
  fraude: "Épisodes de fraude (échange de SIM, ingénierie sociale, smurfing…) noyés dans un peu de trafic normal : démo jury.",
};
// retire les codes couleur ANSI du journal du simulateur
const clean = (s: string) => s.replace(/\u001b\[[0-9;]*m/g, "");

function duration(from: number | null, to: number | null) {
  if (!from) return "—";
  const s = Math.max(0, Math.round(((to ?? Date.now() / 1000) - from)));
  return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
}

export default function SimulateurPage() {
  const me = getUser();
  const canControl = !!me && me.role !== "ANALYSTE";
  const { data: st, error, reload } = usePolling<SimStatus>("/simulator/status", 2000);
  const [mode, setMode] = useState<Mode>("trafic");
  const [rate, setRate] = useState(20);
  const [count, setCount] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function act(path: "start" | "stop") {
    setBusy(true); setMsg(null);
    try {
      await api(`/simulator/${path}`, { method: "POST",
        body: JSON.stringify(path === "start" ? { mode, rate, count: count ? +count : null } : {}) });
      reload();
    } catch (e: any) { setMsg(e.message ?? "erreur"); } finally { setBusy(false); }
  }

  const running = !!st?.running;
  return (
    <div>
      <PageHeader eyebrow="Démonstration" title="Simulateur de trafic"
        subtitle="Envoie des transactions réalistes à la plateforme : le tableau de bord, la carte et les alertes se remplissent en direct.">
        <Pill tone={running ? "faible" : "neutral"} dot={false}><Radio className="h-3 w-3" />{running ? "En cours" : "Arrêté"}</Pill>
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="État" value={running ? "En cours" : "Arrêté"} tone={running ? "success" : "default"}
          hint={st?.mode ? `mode ${st.mode}` : "aucune simulation"} />
        <Stat label="Cadence" value={st?.rate ? `${st.rate} / s` : "—"} hint="transactions par seconde" />
        <Stat label="Durée" value={duration(st?.started_at ?? null, running ? null : st?.ended_at ?? null)} hint="depuis le démarrage" />
        <Stat label="Opérations signalées" value={fmtInt(st?.alerts ?? 0)} tone="warn" hint="vérifiées ou bloquées" />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader><CardTitle>Commande</CardTitle><CardDescription>{MODE_HELP[mode]}</CardDescription></CardHeader>
          <CardContent className="space-y-4">
            <Segmented value={mode} onChange={setMode} options={[["trafic", "Trafic normal"], ["fraude", "Épisodes de fraude"]]} />
            <label className="block">
              <div className="flex items-baseline justify-between text-xs"><span className="font-medium">Cadence</span>
                <span className="tabular text-muted-foreground">{rate} transactions / s</span></div>
              <input type="range" min={1} max={100} step={1} value={rate} onChange={(e) => setRate(+e.target.value)}
                className="mt-1.5 w-full accent-[hsl(var(--primary))]" />
            </label>
            <label className="block text-xs">
              <span className="font-medium">Nombre de transactions (facultatif)</span>
              <input type="number" min={1} placeholder="illimité" value={count} onChange={(e) => setCount(e.target.value)}
                className="mt-1.5 h-9 w-full rounded-lg border bg-card px-3 text-sm" />
            </label>
            {canControl ? (
              <div className="flex gap-2">
                <Button onClick={() => act("start")} disabled={busy || running} className="flex-1"><Play />Démarrer</Button>
                <Button onClick={() => act("stop")} disabled={busy || !running} variant="danger" className="flex-1"><Square />Arrêter</Button>
              </div>
            ) : <p className="text-xs text-muted-foreground">Démarrer ou arrêter la simulation demande le rôle superviseur.</p>}
            {(msg || error) && <p className="text-xs text-risk-critique">{msg ?? error}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Journal</CardTitle>
            <CardDescription>Dernières opérations signalées : décision, probabilité, niveau de risque, vérité terrain et latence.</CardDescription></CardHeader>
          <CardContent>
            <pre className="max-h-[420px] min-h-[220px] overflow-auto rounded-lg bg-muted/50 p-3 text-[11px] leading-relaxed">
              {st?.log?.length ? st.log.map(clean).join("\n") : "Aucune sortie pour le moment."}
            </pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
