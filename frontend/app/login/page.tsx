"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Eye, EyeOff, Gauge, Lock, Map as MapIcon, Radar } from "lucide-react";
import { Logo } from "@/components/app-shell";
import { DrcFlag } from "@/components/drc-flag";
import { HeroIllustration } from "@/components/hero-illustration";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/select";
import { login } from "@/lib/api";

const FEATURES = [
  { icon: Gauge, title: "Décision en temps réel", text: "Chaque transaction est scorée en quelques dizaines de millisecondes." },
  { icon: Radar, title: "Modèle hybride explicable", text: "XGBoost, LSTM-attention et autoencodeur, avec l'explication de chaque alerte." },
  { icon: MapIcon, title: "Vue nationale", text: "Vodacom, Airtel, Orange et Visa virtuelle, sur les 26 provinces." },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { await login(email, password); const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/"); }
    catch (err: any) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      {/* Panneau de marque */}
      <section className="relative hidden overflow-hidden bg-sidebar p-12 text-white lg:flex lg:flex-col">
        <div aria-hidden className="absolute inset-0">
          <div className="absolute -left-32 -top-32 h-[520px] w-[520px] rounded-full bg-[hsl(221_83%_53%)] opacity-30 blur-[120px]" />
          <div className="absolute -bottom-40 right-[-80px] h-[480px] w-[480px] rounded-full bg-[hsl(262_83%_58%)] opacity-25 blur-[120px]" />
          <div className="absolute inset-0 opacity-[.07] [background-image:linear-gradient(white_1px,transparent_1px),linear-gradient(90deg,white_1px,transparent_1px)] [background-size:44px_44px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
        </div>
        <div className="relative flex items-center gap-3">
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">Fraude RDC</span>
          <span className="mx-1 h-6 w-px bg-white/15" />
          <DrcFlag className="h-6 w-8 rounded-[4px] shadow-md ring-1 ring-white/20" />
          <span className="text-xs leading-tight text-white/65">République démocratique<br />du Congo</span>
        </div>

        <div className="relative my-auto grid items-center gap-10 py-10 xl:grid-cols-[minmax(0,1fr)_330px]">
          <div className="max-w-lg">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70 backdrop-blur">
              <span className="h-1.5 w-1.5 rounded-full bg-risk-faible" /> Supervision 24 h/24
            </div>
            <h1 className="text-4xl font-semibold leading-[1.1] tracking-tight xl:text-[44px]">
              Détecter la fraude <span className="bg-gradient-to-r from-[hsl(217_91%_70%)] to-[hsl(262_90%_75%)] bg-clip-text text-transparent">avant qu&apos;elle ne coûte.</span>
            </h1>
            <p className="mt-4 text-[15px] leading-relaxed text-white/60">
              Profilage comportemental des clients Mobile Money et des cartes Visa virtuelles en République démocratique du Congo.
            </p>
          </div>
          <div className="hidden xl:block"><HeroIllustration /></div>
        </div>

        <ul className="relative grid gap-5 xl:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title} className="flex gap-3 xl:flex-col">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/5"><Icon className="h-5 w-5 text-[hsl(217_91%_72%)]" /></div>
              <div><div className="text-sm font-medium">{title}</div><div className="mt-0.5 text-xs leading-relaxed text-white/55">{text}</div></div>
            </li>
          ))}
        </ul>
        <p className="relative mt-8 text-xs text-white/40">Prototype de recherche — données et visuels fictifs.</p>
      </section>

      {/* Formulaire */}
      <section className="flex items-center justify-center bg-background p-6">
        <form onSubmit={submit} className="w-full max-w-[380px] animate-fade-up">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <Logo /><span className="font-semibold">Fraude RDC</span>
            <DrcFlag className="ml-auto h-5 w-7 rounded-[3px] shadow ring-1 ring-border" />
          </div>
          <h2 className="text-2xl font-semibold tracking-tight">Connexion</h2>
          <p className="mt-1 text-sm text-muted-foreground">Accès réservé aux équipes anti-fraude.</p>

          <label className="mb-1.5 mt-8 block text-sm font-medium" htmlFor="email">E-mail professionnel</label>
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
          {error && (
            <p role="alert" className="mt-4 rounded-lg border border-risk-critique/20 bg-risk-critique/10 px-3 py-2.5 text-sm text-risk-critique">
              {error === "identifiants invalides" ? "E-mail ou mot de passe incorrect, ou compte désactivé." : error}
            </p>
          )}
          <Button type="submit" size="lg" className="mt-6 w-full" disabled={busy}>
            {busy ? "Connexion…" : <>Se connecter <ArrowRight /></>}
          </Button>
          <p className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <Lock className="h-3.5 w-3.5" /> Chaque connexion est inscrite au journal d&apos;audit.
          </p>
        </form>
      </section>
    </div>
  );
}
