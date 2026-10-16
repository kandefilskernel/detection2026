import Link from "next/link";
import { ArrowRight, Lock } from "lucide-react";
import { Logo } from "@/components/app-shell";
import { DrcFlag } from "@/components/drc-flag";
import { DrcOutline } from "@/components/drc-outline";

export const metadata = {
  title: "Fraude RDC — Détection de fraude Mobile Money et Visa virtuelle",
  description: "Supervision en temps réel de la fraude Mobile Money et des cartes Visa virtuelles en République démocratique du Congo.",
};

const CHANNELS = ["Vodacom M-Pesa", "Airtel Money", "Orange Money", "Visa virtuelle"];

/** Page d'accueil publique : sobre, identité RDC, un seul appel à l'action (connexion). */
export default function Accueil() {
  return (
    <div className="relative flex min-h-screen flex-col overflow-hidden bg-background">
      {/* Liseré aux couleurs du drapeau */}
      <div aria-hidden className="flex h-1 w-full">
        <span className="flex-[7] bg-[#007FFF]" /><span className="flex-1 bg-[#F7D618]" /><span className="flex-[2] bg-[#CE1021]" />
      </div>
      <div aria-hidden className="pointer-events-none absolute -right-40 top-20 h-[520px] w-[520px] rounded-full bg-primary/10 blur-[120px]" />

      <header className="relative mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-5 sm:px-8">
        <div className="flex items-center gap-3">
          <Logo />
          <span className="text-[15px] font-semibold tracking-tight">Fraude RDC</span>
        </div>
        <Link href="/login"
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border bg-card px-3.5 text-sm font-medium shadow-sm transition-colors hover:border-primary/40 hover:text-primary">
          Se connecter
        </Link>
      </header>

      <main className="relative mx-auto grid w-full max-w-6xl flex-1 items-center gap-10 px-5 py-8 sm:px-8 lg:grid-cols-[1fr_1.05fr] lg:gap-16">
        <div className="max-w-xl animate-fade-up">
          <div className="mb-6 inline-flex items-center gap-2.5 rounded-full border bg-card/70 py-1 pl-1 pr-3.5 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur">
            <DrcFlag className="h-5 w-[27px] rounded-full ring-1 ring-black/5" />
            République démocratique du Congo
          </div>
          <h1 className="text-4xl font-semibold leading-[1.08] tracking-tight sm:text-5xl">
            Stopper la fraude <span className="text-primary">Mobile Money</span> avant qu&apos;elle ne coûte.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-relaxed text-muted-foreground sm:text-lg">
            Chaque transaction est analysée en temps réel, dans les 26 provinces, pour protéger les clients et les opérateurs.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Link href="/login"
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-primary px-5 text-sm font-semibold text-primary-foreground shadow-glow transition-transform hover:-translate-y-px">
              Accéder à la plateforme <ArrowRight className="h-4 w-4" />
            </Link>
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <Lock className="h-3.5 w-3.5" /> Réservé aux équipes anti-fraude
            </span>
          </div>
          <ul className="mt-10 flex flex-wrap gap-2" aria-label="Canaux supervisés">
            {CHANNELS.map((c) => (
              <li key={c} className="rounded-full border bg-card/60 px-3 py-1 text-xs font-medium text-muted-foreground">{c}</li>
            ))}
          </ul>
        </div>

        <div className="relative mx-auto w-full max-w-[560px]">
          <DrcOutline className="h-auto w-full drop-shadow-sm" />
        </div>
      </main>

      <footer className="relative mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-2 px-5 py-6 text-xs text-muted-foreground sm:px-8">
        <span>Prototype de recherche — données et visuels fictifs.</span>
        <span>Contours des provinces : geoBoundaries (ODbL)</span>
      </footer>
    </div>
  );
}
