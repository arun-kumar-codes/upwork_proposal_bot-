"use client";

import { useEffect, useState } from "react";
import { Github } from "lucide-react";
import { api, type Profile, type Project, type Status } from "@/lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

interface Prefill {
  title: string;
  description: string;
  github_url: string;
  live_url: string | null;
  tech_stack: string[];
  readme_excerpt: string;
}

const EMPTY = {
  title: "",
  description: "",
  category: "",
  status: "active" as Status,
  github_url: "",
  live_url: "",
  tech_stack: "",
  result: "",
  client_type: "",
};

export function ProjectDialog({
  open,
  onOpenChange,
  profiles,
  initial,
  fromGithub,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  profiles: Profile[];
  initial: Project | null;
  fromGithub: boolean;
  onSaved: () => void;
}) {
  const [form, setForm] = useState(EMPTY);
  const [selected, setSelected] = useState<number[]>([]);
  const [githubUrl, setGithubUrl] = useState("");
  const [fetching, setFetching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    if (initial) {
      setForm({
        title: initial.title,
        description: initial.description || "",
        category: initial.category || "",
        status: initial.status,
        github_url: initial.github_url || "",
        live_url: initial.live_url || "",
        tech_stack: initial.tech_stack.join(", "),
        result: initial.result || "",
        client_type: initial.client_type || "",
      });
      setSelected(initial.profiles.map((p) => p.id));
      setGithubUrl("");
    } else {
      setForm(EMPTY);
      setSelected([]);
      setGithubUrl("");
    }
  }, [open, initial]);

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function fetchGithub() {
    if (!githubUrl.trim()) return;
    setFetching(true);
    setError("");
    try {
      const data = await api<Prefill>(
        `/api/github/prefill?url=${encodeURIComponent(githubUrl.trim())}`
      );
      setForm((f) => ({
        ...f,
        title: f.title || data.title,
        description: f.description || data.description || data.readme_excerpt,
        github_url: data.github_url,
        live_url: f.live_url || data.live_url || "",
        tech_stack: f.tech_stack || data.tech_stack.join(", "),
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "GitHub fetch failed");
    } finally {
      setFetching(false);
    }
  }

  async function save() {
    if (!form.title.trim()) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    setError("");
    const payload = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      category: form.category.trim(),
      status: form.status,
      github_url: form.github_url.trim() || null,
      live_url: form.live_url.trim() || null,
      tech_stack: form.tech_stack.split(",").map((s) => s.trim()).filter(Boolean),
      result: form.result.trim() || null,
      client_type: form.client_type.trim() || null,
      profile_ids: selected,
    };
    try {
      if (initial) {
        await api(`/api/projects/${initial.id}`, { method: "PUT", body: payload });
      } else {
        await api("/api/projects", { method: "POST", body: payload });
      }
      onOpenChange(false);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  function toggleProfile(id: number) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {initial ? "Edit project" : fromGithub ? "Add from GitHub URL" : "New project"}
          </DialogTitle>
        </DialogHeader>

        {!initial && (
          <div className="rounded-md border bg-muted/40 p-3">
            <Label htmlFor="gh-url">GitHub URL (fetch name, description, README)</Label>
            <div className="mt-2 flex gap-2">
              <Input
                id="gh-url"
                placeholder="https://github.com/owner/repo"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), fetchGithub())}
              />
              <Button variant="secondary" onClick={fetchGithub} disabled={fetching || !githubUrl.trim()}>
                <Github className="h-4 w-4" />
                {fetching ? "Fetching…" : "Fetch"}
              </Button>
            </div>
            <p className="mt-1.5 text-xs text-muted-foreground">
              Review the prefilled fields below, then save.
            </p>
          </div>
        )}

        <div className="grid gap-4">
          <div className="space-y-2">
            <Label>Title *</Label>
            <Input value={form.title} onChange={(e) => set("title", e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Description</Label>
            <Textarea value={form.description} onChange={(e) => set("description", e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Category</Label>
              <Input value={form.category} onChange={(e) => set("category", e.target.value)} placeholder="web" />
            </div>
            <div className="space-y-2">
              <Label>Status</Label>
              <Select value={form.status} onValueChange={(v) => set("status", v as Status)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">active</SelectItem>
                  <SelectItem value="inactive">inactive</SelectItem>
                  <SelectItem value="archived">archived</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>GitHub URL</Label>
              <Input value={form.github_url} onChange={(e) => set("github_url", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Live URL</Label>
              <Input value={form.live_url} onChange={(e) => set("live_url", e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Tech stack (comma-separated)</Label>
              <Input value={form.tech_stack} onChange={(e) => set("tech_stack", e.target.value)} placeholder="nextjs, tailwind" />
            </div>
            <div className="space-y-2">
              <Label>Client type</Label>
              <Input value={form.client_type} onChange={(e) => set("client_type", e.target.value)} />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Result</Label>
            <Input value={form.result} onChange={(e) => set("result", e.target.value)} placeholder="+20% conversion" />
          </div>
          <div className="space-y-2">
            <Label>Profiles</Label>
            <div className="flex flex-wrap gap-2">
              {profiles.length === 0 && (
                <span className="text-sm text-muted-foreground">No profiles yet.</span>
              )}
              {profiles.map((p) => (
                <label
                  key={p.id}
                  className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1 text-sm ${
                    selected.includes(p.id) ? "bg-primary text-primary-foreground" : "bg-background"
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={selected.includes(p.id)}
                    onChange={() => toggleProfile(p.id)}
                  />
                  {p.name}
                </label>
              ))}
            </div>
          </div>
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving ? "Saving…" : initial ? "Save changes" : "Create project"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
