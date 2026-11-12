"use client";

import { useEffect, useState } from "react";
import { History as HistoryIcon, RefreshCw } from "lucide-react";
import { RequireAuth } from "@/lib/auth";
import { api, ApiError } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

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

function excerpt(text: string, n = 80): string {
  if (!text) return "—";
  return text.length > n ? `${text.slice(0, n)}…` : text;
}

function detailError(e: unknown): string {
  if (e instanceof ApiError && e.status === 404) return "That run no longer exists.";
  return e instanceof Error ? e.message : "Could not load that run.";
}

function HistoryInner() {
  const [runs, setRuns] = useState<HistoryItem[]>([]);
  const [detail, setDetail] = useState<HistoryItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailBusy, setDetailBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setRuns(await api<HistoryItem[]>("/api/playground/history?limit=100"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load history.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function openDetail(id: number) {
    setDetailBusy(true);
    setError("");
    try {
      const run = await api<HistoryItem>(`/api/playground/history/${id}`);
      // History rows store title/reason only; resolve live_url from Projects.
      const enriched = await Promise.all(
        run.selected.map(async (s) => {
          if (s.live_url || !s.project_id) return s;
          try {
            const proj = await api<{ live_url: string | null }>(`/api/projects/${s.project_id}`);
            return { ...s, live_url: proj.live_url };
          } catch {
            return s;
          }
        }),
      );
      setDetail({ ...run, selected: enriched });
    } catch (e) {
      setError(detailError(e));
    } finally {
      setDetailBusy(false);
    }
  }

  return (
    <div>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="flex items-center gap-2">
          <HistoryIcon className="h-5 w-5" />
          <h1 className="text-xl font-bold tracking-tight">Playground History</h1>
          <div className="ml-auto">
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          Saved test runs, newest first. Failed runs keep their error. Select a row for detail.
        </p>

        {error && <p className="mt-4 text-sm text-destructive">{error}</p>}

        <div className="mt-6 grid gap-6 lg:grid-cols-2">
          <section>
            {loading ? (
              <p className="py-12 text-center text-sm text-muted-foreground">Loading…</p>
            ) : runs.length === 0 ? (
              <p className="rounded-md border py-12 text-center text-sm text-muted-foreground">
                No test runs yet. Run one in the Playground.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Profile</TableHead>
                    <TableHead>Mode</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((h) => (
                    <TableRow
                      key={h.id}
                      onClick={() => openDetail(h.id)}
                      className={`cursor-pointer ${detail?.id === h.id ? "bg-secondary" : ""}`}
                      title={h.client_message}
                    >
                      <TableCell className="whitespace-nowrap text-xs">
                        {new Date(h.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell>{h.profile_name}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{h.mode === "real_bot" ? "real" : "sim"}</Badge>
                      </TableCell>
                      <TableCell>{h.detected_category || "—"}</TableCell>
                      <TableCell>
                        {h.error ? (
                          <Badge variant="destructive">failed</Badge>
                        ) : (
                          <Badge variant="success">ok</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </section>

          <section className="space-y-4">
            <h2 className="text-sm font-semibold">Run detail</h2>
            {detailBusy ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : !detail ? (
              <p className="text-sm text-muted-foreground">Select a run to see its detail.</p>
            ) : (
              <>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">#{detail.id}</Badge>
                  <Badge variant="outline">{detail.mode === "real_bot" ? "real bot" : "simulated"}</Badge>
                  {detail.detected_category ? (
                    <Badge>{detail.detected_category}</Badge>
                  ) : (
                    <Badge variant="outline">no category</Badge>
                  )}
                  <Badge variant="secondary">source: {detail.category_source}</Badge>
                  {detail.category_override && (
                    <Badge variant="secondary">override: {detail.category_override}</Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {new Date(detail.created_at).toLocaleString()} · {detail.profile_name}
                  </span>
                </div>

                <div className="space-y-2">
                  <Label>Client message</Label>
                  <div className="whitespace-pre-wrap rounded-md border p-3 text-sm">{detail.client_message}</div>
                </div>

                <div className="space-y-2">
                  <Label>Selected projects ({detail.selected.length})</Label>
                  {detail.selected.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No projects were selected.</p>
                  ) : (
                    <ul className="space-y-2">
                      {detail.selected.map((s, i) => (
                        <li key={s.project_id ?? i} className="rounded-md border p-3 text-sm">
                          <div className="font-medium">{s.title}</div>
                          {s.live_url ? (
                            <a className="text-xs underline" href={s.live_url} target="_blank" rel="noreferrer">
                              {s.live_url}
                            </a>
                          ) : (
                            <div className="text-xs text-muted-foreground">No live URL saved for this run.</div>
                          )}
                          <div className="mt-0.5 text-xs text-muted-foreground">{s.reason}</div>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                {detail.error ? (
                  <div className="space-y-2">
                    <Label>Error</Label>
                    <div className="whitespace-pre-wrap rounded-md border p-3 text-sm text-destructive">{detail.error}</div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Label>Reply</Label>
                    <div className="whitespace-pre-wrap rounded-md border bg-muted/40 p-3 text-sm">
                      {detail.reply || "—"}
                    </div>
                  </div>
                )}
                <p className="text-xs text-muted-foreground" title={detail.reply}>
                  Latest message preview: {excerpt(detail.client_message)}
                </p>
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

export default function HistoryPage() {
  return (
    <RequireAuth>
      <HistoryInner />
    </RequireAuth>
  );
}
