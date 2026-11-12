"use client";

import { useState } from "react";
import { FileSpreadsheet, Upload } from "lucide-react";
import { RequireAuth } from "@/lib/auth";
import { api, type ImportErrorRow } from "@/lib/api";
import { Nav } from "@/components/nav";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface Preview {
  dry_run: boolean;
  has_projects_sheet: boolean;
  has_profiles_sheet: boolean;
  projects: Record<string, unknown>[];
  profiles: Record<string, unknown>[];
  errors: ImportErrorRow[];
  summary: { project_rows: number; profile_rows: number; error_rows: number };
}

interface SaveResult {
  dry_run: boolean;
  summary: {
    projects_created: number;
    projects_updated: number;
    profiles_created: number;
    profiles_updated: number;
  };
  errors: ImportErrorRow[];
}

function ImportInner() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<SaveResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function pick(f: File | null) {
    setFile(f);
    setPreview(null);
    setResult(null);
    setError("");
  }

  async function run(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await api<Preview | SaveResult>(`/api/import/excel?dry_run=${dryRun}`, {
        method: "POST",
        formData: form,
      });
      if (dryRun) setPreview(data as Preview);
      else {
        setResult(data as SaveResult);
        setPreview(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  function cell(v: unknown): string {
    if (v === null || v === undefined) return "—";
    if (Array.isArray(v)) return v.join(", ") || "—";
    return String(v);
  }

  return (
    <div>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="text-2xl font-bold tracking-tight">Import from Excel</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sheets <code className="rounded bg-muted px-1">projects</code> and{" "}
          <code className="rounded bg-muted px-1">profiles</code>. Projects match by
          github_url or title, so re-importing never duplicates. Review the preview
          and validation report before saving.
        </p>

        <div className="mt-6 flex flex-wrap items-center gap-3 rounded-lg border p-4">
          <label className="flex cursor-pointer items-center gap-2 rounded-md border px-4 py-2 text-sm hover:bg-accent">
            <FileSpreadsheet className="h-4 w-4" />
            {file ? file.name : "Choose .xlsx file"}
            <input
              type="file"
              accept=".xlsx,.xlsm"
              className="sr-only"
              onChange={(e) => pick(e.target.files?.[0] ?? null)}
            />
          </label>
          <Button variant="secondary" disabled={!file || busy} onClick={() => run(true)}>
            Preview & validate
          </Button>
          <Button disabled={!file || !preview || busy} onClick={() => run(false)}>
            <Upload className="h-4 w-4" />
            {busy ? "Working…" : "Confirm import"}
          </Button>
        </div>

        {error && <p className="mt-4 text-sm text-destructive">{error}</p>}

        {preview && (
          <div className="mt-6 space-y-6">
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">{preview.summary.project_rows} valid project rows</Badge>
              <Badge variant="secondary">{preview.summary.profile_rows} valid profile rows</Badge>
              <Badge variant={preview.summary.error_rows ? "destructive" : "success"}>
                {preview.summary.error_rows} rows with errors
              </Badge>
              {!preview.has_projects_sheet && <Badge variant="warning">no projects sheet</Badge>}
              {!preview.has_profiles_sheet && <Badge variant="warning">no profiles sheet</Badge>}
            </div>

            {preview.errors.length > 0 && (
              <div>
                <h2 className="mb-2 font-semibold">Validation report</h2>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Sheet</TableHead>
                      <TableHead>Row</TableHead>
                      <TableHead>Problems</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.errors.map((e, i) => (
                      <TableRow key={i}>
                        <TableCell>{e.sheet || "—"}</TableCell>
                        <TableCell>{e.row || "—"}</TableCell>
                        <TableCell>
                          <ul className="list-disc pl-4 text-destructive">
                            {e.errors.map((msg, j) => (
                              <li key={j}>{msg}</li>
                            ))}
                          </ul>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {preview.projects.length > 0 && (
              <div>
                <h2 className="mb-2 font-semibold">Projects preview (first 10 of {preview.projects.length})</h2>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Row</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Category</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Tech</TableHead>
                      <TableHead>Profiles</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.projects.slice(0, 10).map((p, i) => (
                      <TableRow key={i}>
                        <TableCell>{cell(p.row)}</TableCell>
                        <TableCell className="font-medium">{cell(p.title)}</TableCell>
                        <TableCell>{cell(p.category)}</TableCell>
                        <TableCell>{cell(p.status)}</TableCell>
                        <TableCell>{cell(p.tech_stack)}</TableCell>
                        <TableCell>{cell(p.profiles)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {preview.profiles.length > 0 && (
              <div>
                <h2 className="mb-2 font-semibold">Profiles preview (first 10 of {preview.profiles.length})</h2>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Row</TableHead>
                      <TableHead>Name</TableHead>
                      <TableHead>Skills</TableHead>
                      <TableHead>Tone</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.profiles.slice(0, 10).map((p, i) => (
                      <TableRow key={i}>
                        <TableCell>{cell(p.row)}</TableCell>
                        <TableCell className="font-medium">{cell(p.name)}</TableCell>
                        <TableCell>{cell(p.skills)}</TableCell>
                        <TableCell>{cell(p.tone)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        )}

        {result && (
          <div className="mt-6 rounded-lg border p-5">
            <h2 className="font-semibold">Import complete</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              <Badge variant="success">{result.summary.projects_created} projects created</Badge>
              <Badge variant="secondary">{result.summary.projects_updated} projects updated</Badge>
              <Badge variant="success">{result.summary.profiles_created} profiles created</Badge>
              <Badge variant="secondary">{result.summary.profiles_updated} profiles updated</Badge>
              {result.errors.length > 0 && (
                <Badge variant="destructive">{result.errors.length} rows skipped (errors)</Badge>
              )}
            </div>
            {result.errors.length > 0 && (
              <ul className="mt-3 list-disc pl-5 text-sm text-destructive">
                {result.errors.map((e, i) => (
                  <li key={i}>
                    [{e.sheet} row {e.row}] {e.errors.join("; ")}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default function ImportPage() {
  return (
    <RequireAuth>
      <ImportInner />
    </RequireAuth>
  );
}
