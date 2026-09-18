import { authHeaders } from "./telegram";

const BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let currentClubId: number | null = null;
export function setClubId(id: number | null) {
  currentClubId = id;
}
export function getClubId() {
  return currentClubId;
}

interface RequestOpts {
  method?: string;
  body?: unknown;
  clubScoped?: boolean;
  idempotencyKey?: string;
  query?: Record<string, string | number | undefined>;
}

export async function api<T>(path: string, opts: RequestOpts = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeaders(),
  };
  if (opts.clubScoped !== false && currentClubId != null) {
    headers["X-Club-Id"] = String(currentClubId);
  }
  if (opts.idempotencyKey) headers["Idempotency-Key"] = opts.idempotencyKey;

  let url = BASE + path;
  if (opts.query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += "?" + s;
  }

  const res = await fetch(url, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });

  if (!res.ok) {
    let code = "http_error";
    let message = res.statusText;
    try {
      const data = await res.json();
      if (data?.error) {
        code = data.error.code ?? code;
        message = data.error.message ?? message;
      }
    } catch {
      /* non-json error */
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// Simple idempotency key generator for payment submissions.
export function uuid(): string {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : "k-" + Date.now() + "-" + Math.random().toString(36).slice(2);
}
