"use client";

import { useEffect, useState } from "react";
import { FlaskConical, Play, RefreshCw } from "lucide-react";
import { RequireAuth } from "@/lib/auth";
import { api, ApiError, type Profile, type ProjectSummary } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

interface Selected {
  project: ProjectSummary;
  reason: string;
}

interface RunResult {
  run_id: number;
  detected_category: string | null;
  category_source: string;
  selected: Selected[];
  reply: string;
  mode: string;
  created_at: string;
}

interface HistorySelected {
  project_id: number;
  title: string;
  reason: string;
  live_url?: string | null;
}

interface HistoryItem {
  id: number;
  profile_name: string;
  client_message: string;
  category_override: string | null;
  detected_category: string | null;
  category_source: string;
  selected: HistorySelected[];
  reply: string;
  error: string | null;
  mode: string;
  created_at: string;
}

interface PgStatus {
  llm_configured: boolean;
  bot_configured: boolean;
  github_configured: boolean;
  llm_model: string;
}

function botFailureMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) return `Auth / key mismatch with the bot — check BOT_API_KEY on both sides. (${e.message})`;
    if (e.status === 503) return `Bot is not configured — set BOT_API_KEY on the bot. (${e.message})`;
    if (e.status === 502) return `Bot unreachable — it may be down. (${e.message})`;
  }
  return e instanceof Error ? e.message : "Run failed";
}

function excerpt(text: string, n = 80): string {
  return text.length > n ? `${text.slice(0, n)}…` : text;
}

function PlaygroundInner() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [config, setConfig] = useState<PgStatus | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [profile, setProfile] = useState("");
  const [message, setMessage] = useState("");
  const [override, setOverride] = useState("");
  const [mode, setMode] = useState<"simulated" | "real_bot">("simulated");
  const [result, setResult] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Profile[]>("/api/profiles").then(setProfiles).catch(() => {});
    api<PgStatus>("/api/playground/status")
      .then((s) => {
        setConfig(s);
        // Real Bot is the live bot: make it the default when configured.
        if (s.bot_configured) setMode("real_bot");
      })
      .catch(() => {});
    refreshHistory();
  }, []);

  async function refreshHistory() {
    try {
      setHistory(await api<HistoryItem[]>("/api/playground/history?limit=50"));
    } catch {
      /* history stays as-is on error */
    }
  }

  async function run() {
    if (!profile || !message.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const data = await api<RunResult>("/api/playground/run", {
        method: "POST",
        body: {
          profile,
          client_message: message,
          category_override: override.trim() || null,
          mode,
        },
      });
      setResult(data);
      await refreshHistory();
    } catch (e) {
      setError(botFailureMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-5 w-5" />
          <h1 className="text-xl font-bold tracking-tight">Test Playground</h1>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Preview what the bot would reply to a client message.
        </p>

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <section className="space-y-4">
            <div className="space-y-2">
              <Label>Profile</Label>
              <Select value={profile} onValueChange={setProfile}>
                <SelectTrigger>
                  <SelectValue placeholder="Pick a profile" />
                </SelectTrigger>
                <SelectContent>
                  {profiles.map((p) => (
                    <SelectItem key={p.id} value={p.name}>
                      {p.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {profiles.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  No profiles yet — add one on the Profiles page or import Excel first.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label>Client job post / message</Label>
              <Textarea
                rows={6}
                placeholder="Paste the client's message here…"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label>Category override (optional)</Label>
              <Input
                placeholder="e.g. web — leave empty to auto-detect"
                value={override}
                onChange={(e) => setOverride(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label>Mode</Label>
              <div className="flex gap-2">
                <Button
                  variant={mode === "simulated" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setMode("simulated")}
                >
                  Simulated (draft only)
                </Button>
                <Button
                  variant={mode === "real_bot" ? "default" : "outline"}
                  size="sm"
                  disabled={!config?.bot_configured}
                  title={
                    config?.bot_configured
                      ? "POST to BOT_URL/generate"
                      : "Set BOT_URL and BOT_API_KEY in env to enable"
                  }
                  onClick={() => setMode("real_bot")}
                >
                  Real Bot
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                {!config
                  ? "Checking backend…"
                  : !config.llm_configured && !config.bot_configured
                    ? "Set OPENAI_API_KEY in env for Simulated mode, BOT_URL + BOT_API_KEY for Real Bot mode."
                    : !config.llm_configured
                      ? "Simulated mode needs OPENAI_API_KEY in env."
                      : !config.bot_configured
                        ? "Real Bot mode is disabled until BOT_URL and BOT_API_KEY are set in env."
                        : "Real Bot is the live bot (default). Simulated is a quick draft only — check it before sending anything."}
              </p>
            </div>

            <div className="flex gap-2">
              <Button onClick={run} disabled={busy || !profile || !message.trim()}>
                <Play className="h-4 w-4" />
                {busy ? "Running…" : "Run"}
              </Button>
              <Button
                variant="outline"
                onClick={run}
                disabled={busy || !result}
                title="Re-run with the same inputs"
              >
                <RefreshCw className="h-4 w-4" />
                Regenerate
              </Button>
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </section>

          <section className="space-y-4">
            <h2 className="text-sm font-semibold">Output</h2>
            {!result ? (
              <p className="text-sm text-muted-foreground">
                Run a test to see the detected category, selected projects, and reply.
              </p>
            ) : (
              <>
                <div className="space-y-2">
                  <Label>1. Detected category</Label>
                  <div className="flex items-center gap-2">
                    {result.detected_category ? (
                      <Badge>{result.detected_category}</Badge>
                    ) : (
                      <Badge variant="outline">none</Badge>
                    )}
                    <span className="text-xs text-muted-foreground">
                      {result.category_source === "override"
                        ? "(your override)"
                        : result.category_source === "detected"
                          ? "(auto-detected)"
                          : "(no match)"}
                    </span>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>2. Selected projects ({result.selected.length})</Label>
                  {result.selected.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No active projects matched this category.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {result.selected.map((s) => (
                        <li
                          key={s.project.id}
                          className="rounded-md border p-3 text-sm"
                        >
                          <div className="font-medium">{s.project.title}</div>
                          <div className="mt-0.5 text-xs text-muted-foreground">
                            {s.reason}
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="space-y-2">
                  <Label>
                    3. Reply the bot would send
                    <span className="ml-2 font-normal text-muted-foreground">
                      ({result.mode === "real_bot" ? "real bot" : "simulated"})
                    </span>
                  </Label>
                  <div className="whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-sm">
                    {result.reply || "—"}
                  </div>
                </div>
              </>
            )}
          </section>
        </div>

        <section className="mt-10 space-y-3">
          <h2 className="text-sm font-semibold">History</h2>
          {history.length === 0 ? (
            <p className="text-sm text-muted-foreground">No test runs yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>Profile</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Message</TableHead>
                  <TableHead>Reply</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.map((h) => (
                  <TableRow key={h.id}>
                    <TableCell className="whitespace-nowrap text-xs">
                      {new Date(h.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell>{h.profile_name}</TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {h.mode === "real_bot" ? "real" : "sim"}
                      </Badge>
                    </TableCell>
                    <TableCell>{h.detected_category || "—"}</TableCell>
                    <TableCell title={h.client_message} className="max-w-56">
                      {excerpt(h.client_message)}
                    </TableCell>
                    <TableCell title={h.error || h.reply} className="max-w-56">
                      {h.error ? <span className="text-destructive">Failed — see History</span> : excerpt(h.reply)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </section>
      </main>
    </div>
  );
}

export default function PlaygroundPage() {
  return (
    <RequireAuth>
      <PlaygroundInner />
    </RequireAuth>
  );
}
