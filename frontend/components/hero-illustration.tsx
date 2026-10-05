import { BellRing, ShieldAlert, Signal, Wifi } from "lucide-react";

/** Téléphone Mobile Money (alerte de fraude) + carte Visa virtuelle, pour la page de connexion. Données fictives. */
export function HeroIllustration() {
  return (
    <div className="relative h-[460px] w-[330px] select-none" aria-hidden>
      {/* Halo */}
      <div className="absolute left-10 top-16 h-72 w-72 rounded-full bg-[hsl(221_83%_53%)] opacity-40 blur-[90px]" />

      {/* ---------------------------------------------------------------- téléphone */}
      <div className="absolute right-0 top-0 h-[440px] w-[220px] rotate-[4deg] rounded-[2.4rem] bg-gradient-to-b from-slate-700 to-slate-900 p-[7px] shadow-[0_40px_80px_-20px_rgba(0,0,0,.7),inset_0_0_0_1px_rgba(255,255,255,.12)]">
        <div className="relative h-full w-full overflow-hidden rounded-[2rem] bg-[#0b1020]">
          {/* encoche */}
          <div className="absolute left-1/2 top-2 z-10 h-5 w-20 -translate-x-1/2 rounded-full bg-black" />
          {/* barre d'état */}
          <div className="flex items-center justify-between px-5 pt-2.5 text-[9px] font-semibold text-white/80">
            <span>09:41</span>
            <span className="flex items-center gap-1"><Signal className="h-2.5 w-2.5" /><Wifi className="h-2.5 w-2.5" /><span className="h-2 w-4 rounded-[2px] border border-white/70 p-px"><span className="block h-full w-3/4 rounded-[1px] bg-white/80" /></span></span>
          </div>
          {/* en-tête de l'application */}
          <div className="mx-3 mt-5 rounded-2xl bg-gradient-to-br from-[hsl(221_83%_55%)] to-[hsl(262_83%_55%)] p-3.5 text-white">
            <div className="text-[9px] uppercase tracking-wider text-white/70">Mobile Money · Solde</div>
            <div className="mt-0.5 text-xl font-semibold tracking-tight">248,50 $</div>
            <div className="mt-2.5 grid grid-cols-3 gap-1.5 text-center text-[8px] text-white/85">
              {["Envoyer", "Retrait", "Payer"].map((l) => <div key={l} className="rounded-lg bg-white/15 py-1.5">{l}</div>)}
            </div>
          </div>
          {/* dernières opérations */}
          <div className="mx-3 mt-3 space-y-1.5">
            {[["Recharge crédit", "-2,00 $"], ["Reçu de +243 99•••12", "+35,00 $"], ["Paiement marché", "-6,50 $"]].map(([l, a]) => (
              <div key={l} className="flex items-center justify-between rounded-xl bg-white/[.06] px-2.5 py-2 text-[9px] text-white/80">
                <span className="truncate">{l}</span><span className="font-semibold text-white">{a}</span>
              </div>
            ))}
          </div>
          {/* alerte de fraude */}
          <div className="absolute inset-x-2 bottom-2 rounded-2xl bg-white p-3 text-slate-900 shadow-2xl">
            <div className="flex items-center gap-2">
              <div className="grid h-7 w-7 place-items-center rounded-full bg-red-100 text-red-600"><ShieldAlert className="h-4 w-4" /></div>
              <div>
                <div className="text-[10px] font-bold leading-tight">Transaction suspendue</div>
                <div className="text-[8px] text-slate-500">Vérification de sécurité</div>
              </div>
            </div>
            <p className="mt-2 text-[9px] leading-snug text-slate-600">Envoi de <b className="text-slate-900">450,00 $</b> depuis un nouvel appareil, à 03 h 12.</p>
            <div className="mt-2.5 grid grid-cols-2 gap-1.5 text-center text-[9px] font-semibold">
              <div className="rounded-lg bg-slate-100 py-1.5">Ce n&apos;est pas moi</div>
              <div className="rounded-lg bg-[hsl(221_83%_53%)] py-1.5 text-white">Confirmer</div>
            </div>
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------------- carte virtuelle */}
      <div className="absolute left-0 top-[150px] z-10 aspect-[1.586] w-[235px] -rotate-[9deg] overflow-hidden rounded-2xl bg-gradient-to-br from-[#1e3a8a] via-[#4338ca] to-[#7c3aed] p-4 text-white shadow-[0_30px_60px_-15px_rgba(0,0,0,.65),inset_0_0_0_1px_rgba(255,255,255,.18)]">
        <div className="absolute -right-10 -top-12 h-40 w-40 rounded-full bg-white/10" />
        <div className="absolute -bottom-16 -left-8 h-40 w-40 rounded-full bg-white/[.06]" />
        <div className="relative flex items-start justify-between">
          <span className="text-[9px] font-semibold uppercase tracking-[.18em] text-white/80">Carte virtuelle</span>
          <Wifi className="h-4 w-4 rotate-90 text-white/80" />
        </div>
        <div className="relative mt-3 h-6 w-8 rounded-md bg-gradient-to-br from-amber-200 to-amber-400 shadow-inner">
          <div className="absolute inset-x-1 top-1/2 h-px bg-amber-600/50" /><div className="absolute inset-y-1 left-1/2 w-px bg-amber-600/50" />
        </div>
        <div className="relative mt-3 font-mono text-[13px] tracking-[.16em]">•••• •••• •••• 4821</div>
        <div className="relative mt-2 flex items-end justify-between">
          <div>
            <div className="text-[7px] uppercase tracking-wider text-white/60">Titulaire</div>
            <div className="text-[10px] font-semibold tracking-wide">CLIENT DÉMO</div>
          </div>
          <div>
            <div className="text-[7px] uppercase tracking-wider text-white/60">Expire</div>
            <div className="text-[10px] font-semibold">12/28</div>
          </div>
          <div className="text-right text-[10px] font-semibold leading-none">Visa<div className="mt-0.5 text-[7px] font-medium text-white/70">virtuelle</div></div>
        </div>
      </div>

      {/* ---------------------------------------------------------------- pastille de score */}
      <div className="absolute left-0 top-10 z-20 flex items-center gap-2 rounded-xl border border-white/10 bg-slate-900/80 px-3 py-2 text-white shadow-xl backdrop-blur-md">
        <div className="grid h-7 w-7 place-items-center rounded-lg bg-red-500/20 text-red-400"><BellRing className="h-3.5 w-3.5" /></div>
        <div>
          <div className="text-[10px] font-semibold leading-tight">Risque critique · 94 %</div>
          <div className="text-[9px] text-white/60">décision en 21 ms</div>
        </div>
      </div>
    </div>
  );
}
