"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Activity, ArrowLeftRight, Bell, Building2, ChevronRight, LogOut, Map as MapIcon, Menu, Moon, KeyRound, ListChecks, Scale, Scale3d, Search, ShieldAlert, ShieldCheck, Sun, Users, Waypoints, X,
} from "lucide-react";
import { DrcFlag } from "@/components/drc-flag";
import { getToken, getUser, logout, type User } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { usePolling } from "@/lib/use-polling";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: typeof Activity; role: keyof typeof RANK; badge?: "cases" };
const NAV: { section: string; items: NavItem[] }[] = [
  { section: "Supervision", items: [
    { href: "/", label: "Tableau de bord", icon: Activity, role: "ANALYSTE" },
    { href: "/carte", label: "Carte des fraudes", icon: MapIcon, role: "ANALYSTE" },
    { href: "/transactions", label: "Transactions", icon: ArrowLeftRight, role: "ANALYSTE" },
    { href: "/alertes", label: "Alertes & dossiers", icon: ShieldAlert, role: "ANALYSTE", badge: "cases" },
    { href: "/reseaux", label: "Réseaux de fraude", icon: Waypoints, role: "ANALYSTE" },
    { href: "/revue", label: "Revue & qualité", icon: ListChecks, role: "ANALYSTE" },
  ] },
  { section: "Gouvernance", items: [
    { href: "/audit", label: "Journal d'audit", icon: ShieldCheck, role: "SUPERVISEUR" },
    { href: "/utilisateurs", label: "Utilisateurs", icon: Users, role: "ADMIN" },
    { href: "/politique", label: "Politique de décision", icon: Scale, role: "SUPERVISEUR" },
    { href: "/equite", label: "Équité du modèle", icon: Scale3d, role: "SUPERVISEUR" },
    { href: "/institutions", label: "Institutions & API", icon: Building2, role: "ADMIN" },
    { href: "/securite", label: "Sécurité du compte", icon: KeyRound, role: "ANALYSTE" },
  ] },
];
const RANK = { ANALYSTE: 0, SUPERVISEUR: 1, ADMIN: 2 };
/** Rôle minimal par section d'URL (miroir du RBAC du back-office). */
const ROUTE_ROLE: Record<string, keyof typeof RANK> = { "/audit": "SUPERVISEUR", "/utilisateurs": "ADMIN", "/institutions": "ADMIN" };
function allowed(role: keyof typeof RANK, path: string) {
  const need = Object.entries(ROUTE_ROLE).find(([p]) => path === p || path.startsWith(p + "/"))?.[1];
  return !need || RANK[role] >= RANK[need];
}
const ROLE_LABEL = { ANALYSTE: "Analyste", SUPERVISEUR: "Superviseur", ADMIN: "Administrateur" };

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-[hsl(221_83%_58%)] to-[hsl(262_83%_58%)] shadow-glow", className)}>
      <ShieldCheck className="h-5 w-5 text-white" strokeWidth={2.2} />
    </div>
  );
}

function Sidebar({ user, openCases, onNavigate }: { user: User; openCases?: number; onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <div className="relative flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div aria-hidden className="flex h-[3px] w-full shrink-0">
        <span className="flex-[7] bg-[#007FFF]" /><span className="flex-1 bg-[#F7D618]" /><span className="flex-[2] bg-[#CE1021]" />
      </div>
      <div aria-hidden className="pointer-events-none absolute -left-24 top-10 h-56 w-56 rounded-full bg-[hsl(221_83%_53%)] opacity-[.12] blur-3xl" />
      <div className="relative flex items-center gap-3 px-5 py-5">
        <Logo />
        <div className="leading-tight">
          <div className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-white">
            Fraude RDC <DrcFlag className="h-3.5 w-[19px] rounded-[2px] ring-1 ring-white/20" />
          </div>
          <div className="text-[11px] text-sidebar-foreground/70">Mobile Money · Visa virtuelle</div>
        </div>
      </div>

      <nav className="relative flex-1 space-y-6 overflow-y-auto px-3 pt-2">
        {NAV.map(({ section, items }) => {
          const visible = items.filter((n) => RANK[user.role] >= RANK[n.role]);
          if (!visible.length) return null;
          return (
            <div key={section}>
              <div className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-[.14em] text-sidebar-foreground/45">{section}</div>
              <div className="space-y-0.5">
                {visible.map(({ href, label, icon: Icon, badge }) => {
                  const active = href === "/" ? path === "/" : path.startsWith(href);
                  return (
                    <Link key={href} href={href} onClick={onNavigate}
                      className={cn("group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors",
                        active ? "bg-white/[.07] text-white" : "hover:bg-white/[.04] hover:text-white")}>
                      {active && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-r-full bg-gradient-to-b from-[hsl(217_91%_65%)] to-[hsl(262_90%_70%)]" />}
                      <Icon className={cn("h-4 w-4 shrink-0", active ? "text-[hsl(217_91%_70%)]" : "text-sidebar-foreground/70 group-hover:text-white")} />
                      <span className="flex-1 truncate">{label}</span>
                      {badge === "cases" && !!openCases && (
                        <span className="tabular rounded-full bg-risk-critique/90 px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white">
                          {openCases > 99 ? "99+" : openCases}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      <LiveStatus />
      <div className="relative mx-3 mb-3 rounded-xl border border-sidebar-border bg-white/[.03] p-3">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-slate-600 to-slate-800 text-xs font-semibold text-white ring-2 ring-white/10">
            {initials(user.full_name)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] font-medium text-white">{user.full_name}</div>
            <div className="truncate text-[11px] text-sidebar-foreground/70">{ROLE_LABEL[user.role]}</div>
          </div>
          <button onClick={logout} title="Se déconnecter" aria-label="Se déconnecter"
            className="rounded-md p-1.5 text-sidebar-foreground/70 transition-colors hover:bg-white/10 hover:text-white">
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

/** Heure de Kinshasa (UTC+1), rafraîchie chaque minute. */
function useKinshasaTime() {
  const [now, setNow] = useState<string>("");
  useEffect(() => {
    const fmt = () => new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: "Africa/Kinshasa" });
    setNow(fmt());
    const id = setInterval(() => setNow(fmt()), 30000);
    return () => clearInterval(id);
  }, []);
  return now;
}

/** Bandeau d'état du système dans la barre latérale. */
function LiveStatus() {
  const time = useKinshasaTime();
  return (
    <div className="relative mx-3 mb-2 flex items-center justify-between gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-[11px] text-sidebar-foreground/70">
      <span className="flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-risk-faible opacity-60" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-risk-faible" />
        </span>
        Temps réel
      </span>
      <span className="tabular whitespace-nowrap">{time && `Kinshasa · ${time}`}</span>
    </div>
  );
}

/** Fil d'Ariane : rubrique › page, déduit de la navigation. */
function Breadcrumb() {
  const path = usePathname();
  let found: { section: string; label: string; href: string } | null = null;
  for (const { section, items } of NAV) for (const it of items) {
    const match = it.href === "/" ? path === "/" : path.startsWith(it.href);
    if (match && (!found || it.href.length > found.href.length)) found = { section, label: it.label, href: it.href };
  }
  if (!found) return null;
  const detail = path !== found.href && found.href !== "/";
  return (
    <nav aria-label="Fil d'Ariane" className="hidden min-w-0 items-center gap-1.5 text-[13px] lg:flex">
      <span className="text-muted-foreground">{found.section}</span>
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" />
      {detail ? (
        <>
          <Link href={found.href} className="text-muted-foreground transition-colors hover:text-foreground">{found.label}</Link>
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/60" />
          <span className="truncate font-medium">Détail</span>
        </>
      ) : <span className="truncate font-medium">{found.label}</span>}
    </nav>
  );
}

function TopBar({ onMenu, openCases }: { onMenu: () => void; openCases?: number }) {
  const router = useRouter();
  const { theme, toggle } = useTheme();
  const [q, setQ] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  // Ctrl+K (ou ⌘K) : aller directement à la recherche
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); searchRef.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background/75 px-4 backdrop-blur-xl md:px-6">
      <button onClick={onMenu} className="rounded-md p-1.5 hover:bg-muted md:hidden" aria-label="Menu"><Menu className="h-5 w-5" /></button>
      <Breadcrumb />
      <form className="relative w-full max-w-md lg:ml-auto" onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) router.push(`/transactions?search=${encodeURIComponent(q.trim())}`);
      }}>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher une transaction ou un client…"
          className="h-9 w-full rounded-lg border bg-card pl-9 pr-14 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none focus:ring-4 focus:ring-primary/15" />
        <kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:block">Ctrl K</kbd>
      </form>
      <div className="ml-auto flex items-center gap-1 lg:ml-0">
        <Link href="/alertes" aria-label="Alertes à traiter" title="Alertes à traiter"
          className="relative grid h-9 w-9 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
          <Bell className="h-[18px] w-[18px]" />
          {!!openCases && <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-risk-critique ring-2 ring-background" />}
        </Link>
        <button onClick={toggle} aria-label={theme === "dark" ? "Passer en mode clair" : "Passer en mode sombre"}
          title={theme === "dark" ? "Mode clair" : "Mode sombre"}
          className="grid h-9 w-9 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground">
          {theme === "dark" ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
        </button>
      </div>
    </header>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [drawer, setDrawer] = useState(false);
  const cases = usePolling<{ total: number }>(user ? "/cases?status=OUVERT&size=1" : null, 15000);

  useEffect(() => {
    if (!getToken()) logout(); // efface aussi le témoin, évite une boucle avec le middleware
    else setUser(getUser());
  }, [router]);
  useEffect(() => setDrawer(false), [path]);
  useEffect(() => {
    if (user && !allowed(user.role, path)) router.replace("/");
  }, [user, path, router]);

  if (!user || !allowed(user.role, path)) return null;

  return (
    <div className="app-backdrop flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 md:block">
        <Sidebar user={user} openCases={cases.data?.total} />
      </aside>
      {drawer && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setDrawer(false)} />
          <div className="absolute inset-y-0 left-0 w-72 animate-fade-up shadow-float">
            <button onClick={() => setDrawer(false)} className="absolute right-3 top-5 z-10 rounded-md p-1 text-white/70 hover:text-white" aria-label="Fermer">
              <X className="h-5 w-5" />
            </button>
            <Sidebar user={user} openCases={cases.data?.total} onNavigate={() => setDrawer(false)} />
          </div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onMenu={() => setDrawer(true)} openCases={cases.data?.total} />
        <main key={path} className="relative mx-auto w-full max-w-[1500px] flex-1 animate-fade-up p-4 md:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, eyebrow, children }:
  { title: string; subtitle?: string; eyebrow?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {eyebrow && (
            <div className="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[.14em] text-primary">
              <span className="h-1.5 w-1.5 rounded-full bg-gradient-to-br from-primary to-accent" />{eyebrow}
            </div>
          )}
          <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{title}</h1>
          {subtitle && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">{children}</div>
      </div>
      <div aria-hidden className="mt-5 h-px w-full bg-gradient-to-r from-primary/40 via-border to-transparent" />
    </div>
  );
}

export function LiveDot({ error }: { error?: string | null }) {
  return (
    <span className={cn("inline-flex h-9 items-center gap-2 rounded-lg border bg-card px-3 text-xs font-medium shadow-sm",
      error ? "text-risk-critique" : "text-muted-foreground")}>
      <span className="relative flex h-2 w-2">
        {!error && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-risk-faible opacity-60" />}
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", error ? "bg-risk-critique" : "bg-risk-faible")} />
      </span>
      {error ? `Hors ligne : ${error}` : "En direct"}
    </span>
  );
}
