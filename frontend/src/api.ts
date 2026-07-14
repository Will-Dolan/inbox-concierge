import type {
  Bucket,
  CreateBucketResult,
  DigestResult,
  JobStatus,
  MarkReadResult,
  RuleCondition,
  SyncResult,
  Thread,
  ThreadDetail,
  UnsubscribeCandidate,
  UpdateBucketResult,
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export { ApiError, API_BASE };

export const api = {
  me: () => request<{ id: string; email: string }>("/auth/me"),
  loginUrl: () => `${API_BASE}/auth/google/login`,
  logout: () => request<void>("/auth/google/logout", { method: "POST" }),

  listThreads: (bucket?: string) =>
    request<Thread[]>(`/threads${bucket ? `?bucket=${encodeURIComponent(bucket)}` : ""}`),
  getThread: (id: string) => request<ThreadDetail>(`/threads/${id}`),
  markThreadsRead: (bucketId?: string, senderDomain?: string) =>
    request<MarkReadResult>(
      `/threads/mark-read?${new URLSearchParams({
        ...(bucketId ? { bucket_id: bucketId } : {}),
        ...(senderDomain ? { sender_domain: senderDomain } : {}),
      })}`,
      { method: "POST" },
    ),

  listBuckets: () => request<Bucket[]>("/buckets"),
  createBucket: (name: string, description: string, classifier: "llm" | "rules") =>
    request<{ bucket_id: string; job_id: string }>("/buckets", {
      method: "POST",
      body: JSON.stringify({ name, description, classifier }),
    }),
  updateBucket: (
    id: string,
    body: { name?: string; description?: string; mode?: "deterministic" | "semantic" },
  ) =>
    request<UpdateBucketResult>(`/buckets/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  updateRule: (bucketId: string, logic: "AND" | "OR" | "NOT", conditions: RuleCondition[]) =>
    request<{ id: string; rule_version: number; matched: number; evaluated: number }>(
      `/buckets/${bucketId}/rule`,
      { method: "PUT", body: JSON.stringify({ logic, conditions }) },
    ),
  deleteBucket: (id: string) => request<void>(`/buckets/${id}`, { method: "DELETE" }),

  getDigest: (bucketId: string, force = false) =>
    request<DigestResult>(`/digest?bucket_id=${bucketId}${force ? "&force=true" : ""}`),

  getUnsubscribeCandidates: (bucketId: string) =>
    request<UnsubscribeCandidate[]>(`/unsubscribe/candidates?bucket_id=${bucketId}`),
  executeUnsubscribe: (url: string) =>
    request<{ ok: boolean }>("/unsubscribe/execute", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  startSync: () => request<{ job_id: string }>("/sync", { method: "POST" }),
  getJob: <T>(jobId: string) => request<JobStatus<T>>(`/jobs/${jobId}`),

  addCorrection: (threadId: string, bucketId: string, action: "add" | "remove") =>
    request<{ applied: boolean }>("/corrections", {
      method: "POST",
      body: JSON.stringify({ thread_id: threadId, bucket_id: bucketId, action }),
    }),
};

export async function pollJob<T>(
  jobId: string,
  { intervalMs = 1500, onTick }: { intervalMs?: number; onTick?: (s: JobStatus<T>) => void } = {},
): Promise<JobStatus<T>> {
  for (;;) {
    const status = await api.getJob<T>(jobId);
    onTick?.(status);
    if (status.status === "done" || status.status === "failed" || status.status === "not_found") {
      return status;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export type { SyncResult, CreateBucketResult };
