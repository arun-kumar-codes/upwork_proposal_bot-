"use client";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const TOKEN_KEY = "hub_token";

export type Status = "active" | "inactive" | "archived";

export interface ProfileSummary {
  id: number;
  name: string;
}

export interface ProjectSummary {
  id: number;
  title: string;
  category: string;
  status: string;
  github_url: string | null;
  live_url: string | null;
  tech_stack: string[];
}

export interface Project {
  id: number;
  title: string;
  description: string | null;
  category: string;
  status: Status;
  github_url: string | null;
  live_url: string | null;
  tech_stack: string[];
  result: string | null;
  client_type: string | null;
  created_at: string;
  updated_at: string;
  profiles: ProfileSummary[];
}

export interface Profile {
  id: number;
  name: string;
  intro: string | null;
  skills: string[];
  tone: string | null;
  portfolio_url: string | null;
  signature: string | null;
  projects: ProjectSummary[];
  active_projects?: ProjectSummary[];
}

export interface ImportErrorRow {
  sheet: string;
  row: number;
  errors: string[];
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; formData?: FormData } = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  const resp = await fetch(`${API_URL}${path}`, {
    method: options.method || "GET",
    headers,
    body,
  });
  if (resp.status === 204) return undefined as T;
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const detail =
      typeof data?.detail === "string"
        ? data.detail
        : Array.isArray(data?.detail)
          ? data.detail.map((d: { msg?: string }) => d.msg).join("; ")
          : `Request failed (${resp.status})`;
    throw new ApiError(resp.status, detail);
  }
  return data as T;
}
