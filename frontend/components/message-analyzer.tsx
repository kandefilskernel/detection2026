"use client";

import { useState } from "react";
import { MessageSquareWarning } from "lucide-react";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const SE_TONE: Record<string, "critique" | "moyen" | "faible"> = { ELEVE: "critique", MOYEN: "moyen", FAIBLE: "faible" };
const SE_LABEL: Record<string, string> = { ELEVE: "Manipulation probable", MOYEN: "Indices de manipulation", FAIBLE: "Pas d'indice net" };
const SENT_TONE: Record<string, "critique" | "neutral" | "faible"> = { NEGATIF: "critique", NEUTRE: "neutral", POSITIF: "faible" };
const SENT_LABEL: Record<string, string> = { NEGATIF: "Ton négatif", NEUTRE: "Ton neutre", POSITIF: "Ton positif" };
const EMOTION_LABEL: Record<string, string> = { PEUR: "Peur", COLERE: "Colère", DETRESSE: "Détresse", CONFUSION: "Confusion" };

/** Résultat de l'analyse d'un message : sentiment, émotions et indices d'ingénierie sociale justifiés par un extrait. */
export function AnalysisResult({ a }: { a: any }) {
  const se = a.social_engineering, s = a.sentiment;
  return (
    <div className="space-y-2.5 text-sm">
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone={SE_TONE[se.level]}>{SE_LABEL[se.level]} · {Math.round(se.score * 100)} %</Pill>
        <Pill tone={SENT_TONE[s.label]} dot={false}>{SENT_LABEL[s.label]}</Pill>
        {s.emotions.map((e: string) => <Pill key={e} tone="moyen" dot={false}>{EMOTION_LABEL[e] ?? e}</Pill>)}
      </div>
      {se.cues.length > 0 && (
        <ul className="space-y-1 text-xs">
          {se.cues.map((c: any) => (
            <li key={c.category} className="rounded-md bg-muted/50 px-2.5 py-1.5">
              <span className="font-medium">{c.label}</span>
              <span className="text-muted-foreground"> · « {c.match} »</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Outil d'analyste : colle un SMS reçu par le client, une plainte ou un message suspect. */
export function MessageAnalyzer() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true); setError(null);
    try { setResult(await api("/nlp/analyze", { method: "POST", body: JSON.stringify({ text }) })); }
    catch (e: any) { setError(e.message); setResult(null); }
    finally { setBusy(false); }
  }

  return (
    <div className="rounded-lg border bg-muted/30 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold"><MessageSquareWarning className="h-4 w-4 text-primary" />Analyser un message</div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000}
        placeholder="Collez le SMS reçu par le client ou sa plainte…"
        className="w-full resize-y rounded-md border bg-background px-2.5 py-2 text-xs outline-none focus:border-primary" />
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground">Analyse locale (français), rien n&apos;est conservé</span>
        <Button size="sm" variant="outline" disabled={busy || text.trim().length < 3} onClick={run}>Analyser</Button>
      </div>
      {error && <p className="mt-2 text-xs text-risk-critique">{error}</p>}
      {result && <div className="mt-3 border-t pt-3"><AnalysisResult a={result} /></div>}
    </div>
  );
}
