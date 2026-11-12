"use client";

import { useCallback, useEffect, useState } from "react";
import { Github, Pencil, Plus, Power, Search, Trash2 } from "lucide-react";
import { RequireAuth } from "@/lib/auth";
import { api, type Profile, type Project } from "@/lib/api";
import { Nav } from "@/components/nav";
import { ProjectDialog } from "@/components/project-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

function statusVariant(s: string) {
  if (s === "active") return "success" as const;
  if (s === "inactive") return "warning" as const;
  return "muted" as const;
}

function ProjectsInner() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [category, setCategory] = useState("all");
  const [profile, setProfile] = useState("all");
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [fromGithub, setFromGithub] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: "500" });
      if (q.trim()) params.set("q", q.trim());
      if (status !== "all") params.set("status", status);
      if (category !== "all") params.set("category", category);
      if (profile !== "all") params.set("profile", profile);
      const [projs, profs, all] = await Promise.all([
        api<Project[]>(`/api/projects?${params}`),
        api<Profile[]>("/api/profiles"),
        api<Project[]>("/api/projects?limit=500"),
      ]);
      setProjects(projs);
      setProfiles(profs);
      setCategories([...new Set(all.map((p) => p.category).filter(Boolean))].sort());
    } finally {
      setLoading(false);
    }
  }, [q, status, category, profile]);

  useEffect(() => {
    const t = setTimeout(load, q ? 300 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  async function toggle(id: number) {
    const updated = await api<Project>(`/api/projects/${id}/toggle-status`, { method: "POST" });
    setProjects((ps) => ps.map((p) => (p.id === id ? updated : p)));
  }

  async function remove(id: number) {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      setTimeout(() => setConfirmDelete((c) => (c === id ? null : c)), 4000);
      return;
    }
    await api(`/api/projects/${id}`, { method: "DELETE" });
    setConfirmDelete(null);
    load();
  }

  function openNew(github: boolean) {
    setEditing(null);
    setFromGithub(github);
    setDialogOpen(true);
  }

  return (
    <div>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">Projects</h1>
          <span className="text-sm text-muted-foreground">{projects.length} shown</span>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" onClick={() => openNew(true)}>
              <Github className="h-4 w-4" />
              Add from GitHub URL
            </Button>
            <Button onClick={() => openNew(false)}>
              <Plus className="h-4 w-4" />
              New project
            </Button>
          </div>
        </div>

        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search title or description…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <Select value={status} onValueChange={setStatus}>
            <SelectTrigger>
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="active">active</SelectItem>
              <SelectItem value="inactive">inactive</SelectItem>
              <SelectItem value="archived">archived</SelectItem>
            </SelectContent>
          </Select>
          <Select value={category} onValueChange={setCategory}>
            <SelectTrigger>
              <SelectValue placeholder="Category" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All categories</SelectItem>
              {categories.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={profile} onValueChange={setProfile}>
            <SelectTrigger>
              <SelectValue placeholder="Profile" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All profiles</SelectItem>
              {profiles.map((p) => (
                <SelectItem key={p.id} value={p.name}>
                  {p.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="mt-6">
          {loading ? (
            <p className="py-12 text-center text-sm text-muted-foreground">Loading…</p>
          ) : projects.length === 0 ? (
            <p className="rounded-md border py-12 text-center text-sm text-muted-foreground">
              No projects match. Add one, or import from Excel.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Tech</TableHead>
                  <TableHead>Profiles</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {projects.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>
                      <div className="font-medium">{p.title}</div>
                      <div className="mt-0.5 flex gap-2 text-xs">
                        {p.github_url && (
                          <a className="text-muted-foreground underline" href={p.github_url} target="_blank" rel="noreferrer">
                            GitHub
                          </a>
                        )}
                        {p.live_url && (
                          <a className="text-muted-foreground underline" href={p.live_url} target="_blank" rel="noreferrer">
                            Live
                          </a>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{p.category || "—"}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant(p.status)}>{p.status}</Badge>
                    </TableCell>
                    <TableCell className="max-w-48 truncate text-muted-foreground">
                      {p.tech_stack.join(", ") || "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {p.profiles.map((x) => x.name).join(", ") || "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="xs"
                          title={p.status === "active" ? "Set inactive" : "Set active"}
                          onClick={() => toggle(p.id)}
                        >
                          <Power className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="xs"
                          onClick={() => {
                            setEditing(p);
                            setFromGithub(false);
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
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </main>

      <ProjectDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        profiles={profiles}
        initial={editing}
        fromGithub={fromGithub}
        onSaved={load}
      />
    </div>
  );
}

export default function ProjectsPage() {
  return (
    <RequireAuth>
      <ProjectsInner />
    </RequireAuth>
  );
}
