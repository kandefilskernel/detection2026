"use client";

import { useState } from "react";
import { CheckCircle2, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** Revue d'analyste d'une transaction non étiquetée (par exemple un comportement nouveau) : le verdict
 *  devient une étiquette pour le prochain réentraînement du modèle. */
export function ReviewPanel({ transactionId, onDone }: { transactionId: string; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(verdict: "FRAUDE" | "LEGITIME") {
    setBusy(true); setError(null);
    try {
      await api(`/cases/review/${encodeURIComponent(transactionId)}`, { method: "POST", body: JSON.stringify({ verdict, note }) });
      onDone();
    } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  return (
    <div className="mt-3 max-w-2xl rounded-lg border bg-muted/30 px-3.5 py-3">
      <div className="mb-1 text-xs font-semibold">Revue d&apos;analyste</div>
      <p className="mb-2 text-xs text-muted-foreground">Votre verdict est enregistré dans le dossier et sert à réentraîner le modèle.</p>
      <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={2000}
        placeholder="Justification (5 caractères minimum) : ce que vous avez vérifié, avec qui…"
        className="w-full resize-y rounded-md border bg-background px-2.5 py-2 text-xs outline-none focus:border-primary" />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" disabled={busy || note.trim().length < 5} onClick={() => send("LEGITIME")}><CheckCircle2 />Légitime</Button>
        <Button size="sm" variant="outline" disabled={busy || note.trim().length < 5} onClick={() => send("FRAUDE")}><ShieldAlert />Fraude</Button>
        {error && <span className="text-xs text-risk-critique">{error}</span>}
      </div>
    </div>
  );
}
