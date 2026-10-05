"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Activity, ArrowLeftRight, LogOut, Map as MapIcon, Menu, Moon, Search, ShieldAlert, ShieldCheck, Sun, Users, X,
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
  ] },
  { section: "Gouvernance", items: [
    { href: "/audit", label: "Journal d'audit", icon: ShieldCheck, role: "SUPERVISEUR" },
    { href: "/utilisateurs", label: "Utilisateurs", icon: Users, role: "ADMIN" },
  ] },
];
const RANK = { ANALYSTE: 0, SUPERVISEUR: 1, ADMIN: 2 };
/** Rôle minimal par section d'URL (miroir du RBAC du back-office). */
const ROUTE_ROLE: Record<string, keyof typeof RANK> = { "/audit": "SUPERVISEUR", "/utilisateurs": "ADMIN" };
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
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-3 px-5 py-5">
        <Logo />
        <div className="leading-tight">
          <div className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-white">
            Fraude RDC <DrcFlag className="h-3.5 w-[19px] rounded-[2px] ring-1 ring-white/20" />
          </div>
          <div className="text-[11px] text-sidebar-foreground/70">Mobile Money · Visa virtuelle</div>
        </div>
      </div>

      <nav className="flex-1 space-y-6 overflow-y-auto px-3 pt-2">
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

      <div className="m-3 rounded-xl border border-sidebar-border bg-white/[.03] p-3">
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

function TopBar({ onMenu }: { onMenu: () => void }) {
  const router = useRouter();
  const { theme, toggle } = useTheme();
  const [q, setQ] = useState("");
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur-xl md:px-6">
      <button onClick={onMenu} className="rounded-md p-1.5 hover:bg-muted md:hidden" aria-label="Menu"><Menu className="h-5 w-5" /></button>
      <form className="relative w-full max-w-md" onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) router.push(`/transactions?search=${encodeURIComponent(q.trim())}`);
      }}>
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher une transaction ou un client…"
          className="h-9 w-full rounded-lg border bg-card pl-9 pr-3 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none focus:ring-4 focus:ring-primary/15" />
      </form>
      <div className="ml-auto flex items-center gap-1">
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
    <div className="flex min-h-screen">
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
        <TopBar onMenu={() => setDrawer(true)} />
        <main key={path} className="mx-auto w-full max-w-[1500px] flex-1 animate-fade-up p-4 md:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, eyebrow, children }:
  { title: string; subtitle?: string; eyebrow?: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-[11px] font-semibold uppercase tracking-[.14em] text-primary">{eyebrow}</div>}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
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
