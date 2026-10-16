"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, ShieldAlert } from "lucide-react";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export const REVIEW_REASON_LABEL: Record<string, string> = {
  INCERTITUDE: "Le modèle a hésité", NOUVEAUTE: "Comportement nouveau", RESEAU: "Lien avec un réseau à risque",
  TEMOIN: "Échantillon témoin", REVUE: "Revue libre", ALERTE: "Alerte du modèle", PLAINTE: "Plainte client",
};

/** Revue d'analyste d'une transaction non étiquetée (par exemple un comportement nouveau) : le verdict
 *  devient une étiquette pour le prochain réentraînement du modèle. Ouverte depuis la file de revue
 *  (/transactions/ID?reason=TEMOIN), elle conserve le motif pour mesurer l'apport de chaque source. */
export function ReviewPanel({ transactionId, onDone }: { transactionId: string; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("REVUE");
  useEffect(() => {
    const r = new URLSearchParams(window.location.search).get("reason");
    if (r && ["INCERTITUDE", "NOUVEAUTE", "RESEAU", "TEMOIN"].includes(r)) setReason(r);
  }, []);

  async function send(verdict: "FRAUDE" | "LEGITIME") {
    setBusy(true); setError(null);
    try {
      await api(`/cases/review/${encodeURIComponent(transactionId)}`, { method: "POST", body: JSON.stringify({ verdict, note, reason }) });
      onDone();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="mb-4 rounded-2xl border bg-card p-5 shadow-card">
      <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)_auto] lg:items-center">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <span className="h-1.5 w-1.5 rounded-full bg-gradient-to-br from-primary to-accent" />Revue d&apos;analyste
            {reason !== "REVUE" && <Pill tone="primary" dot={false}>{REVIEW_REASON_LABEL[reason]}</Pill>}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Votre verdict est inscrit au dossier et sert à réentraîner le modèle.</p>
        </div>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000}
          placeholder="Justification (5 caractères minimum) : ce que vous avez vérifié, avec qui…"
          className="w-full resize-y rounded-lg border bg-background px-3 py-2 text-sm outline-none focus:border-primary/60 focus:ring-4 focus:ring-primary/15" />
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={busy || note.trim().length < 5} onClick={() => send("LEGITIME")}><CheckCircle2 />Légitime</Button>
          <Button size="sm" disabled={busy || note.trim().length < 5} onClick={() => send("FRAUDE")}
            className="bg-risk-critique text-white hover:bg-risk-critique/90"><ShieldAlert />Fraude</Button>
        </div>
      </div>
      {error && <p className="mt-2 text-xs text-risk-critique">{error}</p>}
    </div>
  );
}
