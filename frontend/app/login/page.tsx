"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ArrowRight, Eye, EyeOff, Lock } from "lucide-react";
import { Logo } from "@/components/app-shell";
import { DrcFlag } from "@/components/drc-flag";
import { MobileMoneyPhone, VirtualCard } from "@/components/hero-illustration";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/select";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [otp, setOtp] = useState("");
  const [needOtp, setNeedOtp] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const { setupRequired } = await login(email, password, needOtp ? otp : undefined);
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(setupRequired ? "/securite?setup=1" : next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err: any) {
      if (err.message === "TOTP_REQUIRED") { setNeedOtp(true); setOtp(""); }
      else setError(err.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-background">
      {/* Liseré aux couleurs du drapeau, comme la page d'accueil */}
      <div aria-hidden className="flex h-1 w-full">
        <span className="flex-[7] bg-[#007FFF]" /><span className="flex-1 bg-[#F7D618]" /><span className="flex-[2] bg-[#CE1021]" />
      </div>
      {/* Halo discret derrière le formulaire */}
      <div aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 h-[560px] w-[560px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-[120px]" />

      <header className="relative mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <Link href="/accueil" className="flex items-center gap-3">
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">Fraude RDC</span>
        </Link>
        <Link href="/accueil" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Accueil
        </Link>
      </header>

      {/* Trois colonnes sur grand écran : téléphone Mobile Money | formulaire (centré) | carte Visa virtuelle */}
      <main className="relative mx-auto grid w-full max-w-7xl flex-1 items-center justify-items-center gap-10 px-5 py-8
                       lg:grid-cols-[1fr_400px_1fr] xl:gap-16">
        {/* l'animation est sur l'enveloppe : sur le même élément, elle écraserait la rotation */}
        <div className="hidden animate-fade-up lg:flex lg:justify-end">
          <MobileMoneyPhone className="-rotate-6 drop-shadow-2xl" />
        </div>
        <form onSubmit={submit}
          className="w-full max-w-[400px] animate-fade-up rounded-2xl border bg-card/90 p-7 shadow-float backdrop-blur-md sm:p-8">
          <div className="mb-6 flex flex-col items-center text-center">
            <DrcFlag className="mb-4 h-8 w-11 rounded-md shadow ring-1 ring-black/5" />
            <h1 className="text-2xl font-semibold tracking-tight">Connexion</h1>
            <p className="mt-1 text-sm text-muted-foreground">Accès réservé aux équipes anti-fraude.</p>
          </div>

          <label className="mb-1.5 block text-sm font-medium" htmlFor="email">E-mail professionnel</label>
          <Input id="email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)}
            placeholder="prenom.nom@operateur.cd" className="h-11" />
          <label className="mb-1.5 mt-4 block text-sm font-medium" htmlFor="password">Mot de passe</label>
          <div className="relative">
            <Input id="password" type={show ? "text" : "password"} autoComplete="current-password" required value={password}
              onChange={(e) => setPassword(e.target.value)} className="h-11 pr-11" />
            <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Masquer le mot de passe" : "Afficher le mot de passe"}
              className="absolute right-1.5 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
              {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {needOtp && (
            <div className="mt-4 animate-fade-up">
              <label className="mb-1.5 block text-sm font-medium" htmlFor="otp">Code de double authentification</label>
              <Input id="otp" inputMode="numeric" autoComplete="one-time-code" autoFocus required pattern="[0-9 ]{6,8}" maxLength={8}
                value={otp} onChange={(e) => setOtp(e.target.value)} placeholder="123 456" className="h-11 text-center font-mono text-lg tracking-[.3em]" />
              <p className="mt-1.5 text-xs text-muted-foreground">Code à 6 chiffres de votre application d&apos;authentification.</p>
            </div>
          )}
          {error && (
            <p role="alert" className="mt-4 rounded-lg border border-risk-critique/20 bg-risk-critique/10 px-3 py-2.5 text-sm text-risk-critique">
              {error === "identifiants invalides" ? "E-mail ou mot de passe incorrect, ou compte désactivé."
                : error === "code de double authentification invalide" ? "Code incorrect ou déjà utilisé : attendez le suivant." : error}
            </p>
          )}
          <Button type="submit" size="lg" className="mt-6 w-full" disabled={busy}>
            {busy ? "Connexion…" : <>{needOtp ? "Valider le code" : "Se connecter"} <ArrowRight /></>}
          </Button>
          <p className="mt-5 flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
            <Lock className="h-3.5 w-3.5 shrink-0" /> Chaque connexion est inscrite au journal d&apos;audit.
          </p>
        </form>
        <div className="hidden animate-fade-up lg:flex lg:justify-start">
          <VirtualCard className="rotate-[8deg]" />
        </div>
      </main>

      <footer className="relative py-5 text-center text-xs text-muted-foreground">
        Prototype de recherche — données et visuels fictifs.
      </footer>
    </div>
  );
}
