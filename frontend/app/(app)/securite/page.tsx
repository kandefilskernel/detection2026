"use client";

import { useEffect, useState } from "react";
import { CheckCircle2, Copy, KeyRound, Lock, ShieldCheck, Smartphone } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/select";
import { api, setSession } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { cn } from "@/lib/utils";

type Me = { email: string; role: string; totp_enabled: boolean; two_factor_required: boolean; two_factor_setup_required: boolean };
type Setup = { secret: string; otpauth_uri: string; issuer: string; digits: number; period: number };

function CodeInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <Input inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={value} onChange={(e) => onChange(e.target.value)}
      placeholder="123 456" aria-label="Code à 6 chiffres" className="h-11 max-w-[180px] text-center font-mono text-lg tracking-[.3em]" />
  );
}

export default function SecuritePage() {
  const { data: me, reload } = usePolling<Me>("/auth/me", 0);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [fromLogin, setFromLogin] = useState(false);
  useEffect(() => setFromLogin(new URLSearchParams(window.location.search).get("setup") === "1"), []);

  async function run(fn: () => Promise<void>) {
    setBusy(true); setMsg(null);
    try { await fn(); } catch (e: any) { setMsg({ ok: false, text: e.message }); } finally { setBusy(false); }
  }
  const start = () => run(async () => { setSetup(await api<Setup>("/auth/2fa/setup", { method: "POST" })); setCode(""); });
  const enable = () => run(async () => {
    const session = await api("/auth/2fa/enable", { method: "POST", body: JSON.stringify({ code }) });
    setSession(session); setSetup(null); setCode(""); reload();
    setMsg({ ok: true, text: "Double authentification activée : un code vous sera demandé à chaque connexion." });
    if (fromLogin) setTimeout(() => { window.location.href = "/"; }, 1200);
  });
  const disable = () => run(async () => {
    setSession(await api("/auth/2fa/disable", { method: "POST", body: JSON.stringify({ code }) }));
    setCode(""); reload(); setMsg({ ok: true, text: "Double authentification désactivée." });
  });
  const grouped = setup?.secret.match(/.{1,4}/g)?.join(" ");

  return (
    <>
      <PageHeader eyebrow="Compte" title="Sécurité" subtitle="Double authentification et protection de votre accès au back-office." />

      {me?.two_factor_setup_required && (
        <div className="mb-4 flex items-start gap-3 rounded-2xl border border-risk-moyen/40 bg-risk-moyen/10 p-4 text-sm">
          <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          <div><div className="font-semibold">Activation obligatoire pour le rôle {me.role.toLowerCase()}</div>
            <p className="mt-0.5 text-muted-foreground">Les superviseurs et administrateurs valident des déblocages et gèrent les accès : leur compte
              doit être protégé par un second facteur. Le reste du back-office est accessible une fois la double authentification activée.</p></div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <Card>
          <CardHeader>
            <div><CardTitle className="flex items-center gap-2">Double authentification (TOTP)
              {me && <Pill tone={me.totp_enabled ? "faible" : me.two_factor_required ? "critique" : "neutral"}>{me.totp_enabled ? "Activée" : "Non activée"}</Pill>}</CardTitle>
              <CardDescription>Un code à 6 chiffres, renouvelé toutes les 30 secondes par une application sur votre téléphone.</CardDescription></div>
            <div className="rounded-lg bg-primary/10 p-2 text-primary"><ShieldCheck className="h-4 w-4" /></div>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {me && !me.totp_enabled && !setup && (
              <Button onClick={start} disabled={busy}><KeyRound /> Configurer la double authentification</Button>
            )}

            {setup && (
              <ol className="space-y-4">
                <li className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">1</span>
                  <div>Installez une application d&apos;authentification : Google Authenticator, Microsoft Authenticator ou FreeOTP.</div></li>
                <li className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">2</span>
                  <div className="min-w-0 flex-1">
                    Ajoutez un compte avec cette clé (saisie manuelle, type « basé sur l&apos;heure ») :
                    <div className="mt-2 flex items-center gap-2">
                      <code className="break-all rounded-lg border bg-muted/60 px-3 py-2 font-mono text-sm tracking-wider">{grouped}</code>
                      <button type="button" onClick={() => navigator.clipboard?.writeText(setup.secret)} title="Copier la clé" aria-label="Copier la clé"
                        className="rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground"><Copy className="h-4 w-4" /></button>
                    </div>
                    <a href={setup.otpauth_uri} className="mt-2 inline-flex items-center gap-1.5 text-xs text-primary hover:underline">
                      <Smartphone className="h-3.5 w-3.5" /> Sur téléphone : ouvrir directement dans l&apos;application
                    </a>
                    <p className="mt-1 text-xs text-muted-foreground">Compte : {setup.issuer} ({me?.email}). Ne partagez jamais cette clé.</p>
                  </div></li>
                <li className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">3</span>
                  <div className="flex flex-wrap items-center gap-2">Saisissez le code affiché :
                    <CodeInput value={code} onChange={setCode} />
                    <Button onClick={enable} disabled={busy || code.replace(/\s/g, "").length < 6}><CheckCircle2 /> Activer</Button>
                  </div></li>
              </ol>
            )}

            {me?.totp_enabled && (
              me.two_factor_required
                ? <p className="text-muted-foreground">Obligatoire pour votre rôle. Téléphone perdu ? Un administrateur peut la réinitialiser depuis l&apos;écran Utilisateurs.</p>
                : <div className="flex flex-wrap items-center gap-2 border-t pt-4">
                    <span className="text-muted-foreground">Désactiver (code actuel requis) :</span>
                    <CodeInput value={code} onChange={setCode} />
                    <Button variant="outline" onClick={disable} disabled={busy || code.replace(/\s/g, "").length < 6}>Désactiver</Button>
                  </div>
            )}

            {msg && <p className={cn("rounded-lg px-3 py-2 text-xs", msg.ok ? "bg-risk-faible/10 text-risk-faible" : "bg-risk-critique/10 text-risk-critique")}>{msg.text}</p>}
          </CardContent>
        </Card>

        <Card className="self-start">
          <CardHeader><div><CardTitle>Protections du compte</CardTitle></div></CardHeader>
          <CardContent className="space-y-3 text-xs text-muted-foreground">
            <p><b className="text-foreground">Verrouillage.</b> Après 5 échecs consécutifs (mot de passe ou code), le compte est verrouillé 15 minutes ; un administrateur peut le déverrouiller.</p>
            <p><b className="text-foreground">Codes à usage unique.</b> Un code déjà utilisé est refusé, même dans sa fenêtre de 30 secondes.</p>
            <p><b className="text-foreground">Quatre yeux.</b> Débloquer une transaction bloquée importante exige la validation d&apos;un second superviseur.</p>
            <p><b className="text-foreground">Traçabilité.</b> Connexions, échecs, verrouillages et changements de 2FA sont inscrits au journal d&apos;audit.</p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
