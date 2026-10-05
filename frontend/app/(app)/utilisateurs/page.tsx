"use client";

import { useState } from "react";
import { UserPlus } from "lucide-react";
import { PageHeader } from "@/components/app-shell";
import { Pill } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/select";
import { api, getUser } from "@/lib/api";
import { usePolling } from "@/lib/use-polling";
import { cn } from "@/lib/utils";

const ROLES: [string, string][] = [["ANALYSTE", "Analyste"], ["SUPERVISEUR", "Superviseur"], ["ADMIN", "Administrateur"]];
const ROLE_TONE = { ANALYSTE: "neutral", SUPERVISEUR: "primary", ADMIN: "eleve" } as const;
const initials = (n: string) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");

export default function UsersPage() {
  const me = getUser();
  const { data, reload } = usePolling<any[]>("/users", 0);
  const [form, setForm] = useState({ email: "", full_name: "", role: "ANALYSTE", password: "" });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const isAdmin = me?.role === "ADMIN";

  async function create(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try {
      await api("/users", { method: "POST", body: JSON.stringify(form) });
      setForm({ ...form, email: "", full_name: "", password: "" }); reload(); setMsg({ ok: true, text: "Compte créé." });
    } catch (err: any) { setMsg({ ok: false, text: err.message }); }
  }
  async function toggle(u: any) {
    await api(`/users/${u.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !u.is_active }) }); reload();
  }

  return (
    <>
      <PageHeader eyebrow="Gouvernance" title="Utilisateurs" subtitle="Comptes du back-office et rôles (contrôle d'accès par rôle)." />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-2">
          <div className="overflow-x-auto">
            <table className="tbl">
              <thead><tr><th>Utilisateur</th><th>Rôle</th><th>État</th><th /></tr></thead>
              <tbody>
                {(data ?? []).map((u) => (
                  <tr key={u.id} className={cn(!u.is_active && "opacity-60")}>
                    <td>
                      <div className="flex items-center gap-3">
                        <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-primary/80 to-accent/80 text-[11px] font-semibold text-white">{initials(u.full_name)}</div>
                        <div className="min-w-0"><div className="truncate font-medium">{u.full_name}</div><div className="truncate text-xs text-muted-foreground">{u.email}</div></div>
                      </div>
                    </td>
                    <td><Pill tone={ROLE_TONE[u.role as keyof typeof ROLE_TONE]} dot={false}>{ROLES.find(([r]) => r === u.role)?.[1]}</Pill></td>
                    <td><Pill tone={u.is_active ? "faible" : "neutral"}>{u.is_active ? "Actif" : "Désactivé"}</Pill></td>
                    <td className="text-right">
                      {isAdmin && u.id !== me?.id && (
                        <Button size="sm" variant={u.is_active ? "outline" : "default"} onClick={() => toggle(u)}>{u.is_active ? "Désactiver" : "Réactiver"}</Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        {isAdmin && (
          <Card className="self-start">
            <CardHeader>
              <div><CardTitle>Nouveau compte</CardTitle><CardDescription>Le mot de passe doit faire au moins 10 caractères.</CardDescription></div>
              <div className="rounded-lg bg-primary/10 p-2 text-primary"><UserPlus className="h-4 w-4" /></div>
            </CardHeader>
            <CardContent>
              <form onSubmit={create} className="space-y-3">
                <Input placeholder="Nom complet" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
                <Input placeholder="E-mail" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                <Select className="w-full" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} options={ROLES} />
                <Input placeholder="Mot de passe" type="password" minLength={10} required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                <Button type="submit" className="w-full"><UserPlus /> Créer le compte</Button>
                {msg && <p className={cn("rounded-lg px-3 py-2 text-xs", msg.ok ? "bg-risk-faible/10 text-risk-faible" : "bg-risk-critique/10 text-risk-critique")}>{msg.text}</p>}
              </form>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
