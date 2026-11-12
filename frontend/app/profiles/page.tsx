"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { RequireAuth } from "@/lib/auth";
import { api, type Profile, type ProjectSummary } from "@/lib/api";
import { Nav } from "@/components/nav";
import { ProfileDialog } from "@/components/profile-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

function ProfilesInner() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Profile | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [profs, projs] = await Promise.all([
        api<Profile[]>("/api/profiles"),
        api<ProjectSummary[]>("/api/projects?limit=500"),
      ]);
      // Fetch each profile's active projects for display.
      const detailed = await Promise.all(
        profs.map((p) => api<Profile>(`/api/profiles/${encodeURIComponent(p.name)}`))
      );
      setProfiles(detailed);
      setProjects(projs);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function remove(id: number) {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      setTimeout(() => setConfirmDelete((c) => (c === id ? null : c)), 4000);
      return;
    }
    await api(`/api/profiles/${id}`, { method: "DELETE" });
    setConfirmDelete(null);
    load();
  }

  return (
    <div>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">Profiles</h1>
          <span className="text-sm text-muted-foreground">
            Upwork profiles and their active projects
          </span>
          <div className="ml-auto">
            <Button
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <Plus className="h-4 w-4" />
              New profile
            </Button>
          </div>
        </div>

        <div className="mt-6">
          {loading ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Loading…</p>
          ) : profiles.length === 0 ? (
            <p className="rounded-md border py-12 text-center text-sm text-muted-foreground">
              No profiles yet. Create one, or import from Excel.
            </p>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {profiles.map((p) => (
                <div key={p.id} className="rounded-lg border bg-card p-5">
                  <div className="flex items-start gap-2">
                    <div>
                      <h2 className="font-semibold">{p.name}</h2>
                      {p.intro && (
                        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{p.intro}</p>
                      )}
                    </div>
                    <div className="ml-auto flex gap-1">
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => {
                          setEditing(p);
                          setDialogOpen(true);
                        }}
                      >
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button
                        variant={confirmDelete === p.id ? "destructive" : "ghost"}
                        size="xs"
                        onClick={() => remove(p.id)}
                      >
                        {confirmDelete === p.id ? "Confirm?" : <Trash2 className="h-4 w-4" />}
                      </Button>
                    </div>
                  </div>
                  {p.skills.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {p.skills.map((s) => (
                        <Badge key={s} variant="secondary">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  )}
                  <div className="mt-4 border-t pt-3">
                    <p className="text-xs font-semibold text-muted-foreground">
                      ACTIVE PROJECTS ({p.active_projects?.length ?? 0})
                    </p>
                    {(p.active_projects?.length ?? 0) === 0 ? (
                      <p className="mt-1 text-sm text-muted-foreground">None linked.</p>
                    ) : (
                      <ul className="mt-1 space-y-1">
                        {p.active_projects!.map((x) => (
                          <li key={x.id} className="text-sm">
                            {x.title}
                            <span className="ml-2 text-xs text-muted-foreground">{x.category}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  {(p.tone || p.portfolio_url) && (
                    <p className="mt-3 text-xs text-muted-foreground">
                      {[p.tone && `Tone: ${p.tone}`, p.portfolio_url && `Portfolio: ${p.portfolio_url}`]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </main>

      <ProfileDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        projects={projects}
        initial={editing}
        onSaved={load}
      />
    </div>
  );
}

export default function ProfilesPage() {
  return (
    <RequireAuth>
      <ProfilesInner />
    </RequireAuth>
  );
}
