"use client";

import { useEffect, useState } from "react";
import { api, type Profile, type ProjectSummary } from "@/lib/api";
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

const EMPTY = {
  name: "",
  intro: "",
  skills: "",
  tone: "",
  portfolio_url: "",
  signature: "",
};

export function ProfileDialog({
  open,
  onOpenChange,
  projects,
  initial,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  projects: ProjectSummary[];
  initial: Profile | null;
  onSaved: () => void;
}) {
  const [form, setForm] = useState(EMPTY);
  const [selected, setSelected] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setError("");
    if (initial) {
      setForm({
        name: initial.name,
        intro: initial.intro || "",
        skills: initial.skills.join(", "),
        tone: initial.tone || "",
        portfolio_url: initial.portfolio_url || "",
        signature: initial.signature || "",
      });
      setSelected(initial.projects.map((p) => p.id));
    } else {
      setForm(EMPTY);
      setSelected([]);
    }
  }, [open, initial]);

  function set<K extends keyof typeof EMPTY>(key: K, value: (typeof EMPTY)[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function save() {
    if (!form.name.trim()) {
      setError("Name is required.");
      return;
    }
    setSaving(true);
    setError("");
    const payload = {
      name: form.name.trim(),
      intro: form.intro.trim() || null,
      skills: form.skills.split(",").map((s) => s.trim()).filter(Boolean),
      tone: form.tone.trim() || null,
      portfolio_url: form.portfolio_url.trim() || null,
      signature: form.signature.trim() || null,
      project_ids: selected,
    };
    try {
      if (initial) {
        await api(`/api/profiles/${initial.id}`, { method: "PUT", body: payload });
      } else {
        await api("/api/profiles", { method: "POST", body: payload });
      }
      onOpenChange(false);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? "Edit profile" : "New profile"}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="space-y-2">
            <Label>Name *</Label>
            <Input value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Web Dev" />
          </div>
          <div className="space-y-2">
            <Label>Intro</Label>
            <Textarea value={form.intro} onChange={(e) => set("intro", e.target.value)} placeholder="Used by the proposal bot" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Skills (comma-separated)</Label>
              <Input value={form.skills} onChange={(e) => set("skills", e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Tone</Label>
              <Input value={form.tone} onChange={(e) => set("tone", e.target.value)} placeholder="professional, direct" />
            </div>
          </div>
          <div className="space-y-2">
            <Label>Portfolio URL</Label>
            <Input value={form.portfolio_url} onChange={(e) => set("portfolio_url", e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Signature</Label>
            <Textarea value={form.signature} onChange={(e) => set("signature", e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Linked projects</Label>
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-2">
              {projects.length === 0 && (
                <span className="text-sm text-muted-foreground">No projects yet.</span>
              )}
              {projects.map((p) => (
                <label key={p.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-accent">
                  <input
                    type="checkbox"
                    checked={selected.includes(p.id)}
                    onChange={() =>
                      setSelected((s) => (s.includes(p.id) ? s.filter((x) => x !== p.id) : [...s, p.id]))
                    }
                  />
                  {p.title}
                  <span className="ml-auto text-xs text-muted-foreground">{p.status}</span>
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
            {saving ? "Saving…" : initial ? "Save changes" : "Create profile"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
