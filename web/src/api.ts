import type { AppState, BulkAction, Decision, MutationResult, ServiceFields } from "./types";

async function request<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Ошибка сервера (${res.status})`);
  return data as T;
}

export const api = {
  state: () => request<AppState>("/api/state"),
  decide: (domain: string, decision: Decision | null) =>
    request<MutationResult>("/api/decide", { domain, decision }),
  update: (domain: string, fields: ServiceFields) =>
    request<MutationResult>("/api/update", { domain, fields }),
  undo: () => request<MutationResult>("/api/undo", {}),
  bulk: (action: BulkAction) => request<MutationResult>("/api/bulk", { action }),
  add: (domain: string, name: string, decision: Decision | null) =>
    request<MutationResult>("/api/services", { domain, name, decision }),
  importProgress: (data: unknown) => request<{ imported: number }>("/api/progress/import", { data }),
};
