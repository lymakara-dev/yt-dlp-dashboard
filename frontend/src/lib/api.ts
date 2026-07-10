import type {
  DownloadRequest,
  HealthResponse,
  Job,
  JobList,
  LyricsSearchResponse,
  ProbeResponse,
  SearchResponse,
  Settings,
} from "./types";

// Readable error thrown by the API client; carries the backend `detail` message.
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?", 0);
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = body.detail[0]?.msg ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),

  probe: (url: string) =>
    request<ProbeResponse>("/api/probe", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  probeRaw: (url: string) =>
    request<Record<string, unknown>>("/api/probe/raw", {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  search: (query: string, provider: string, limit: number) =>
    request<SearchResponse>("/api/search", {
      method: "POST",
      body: JSON.stringify({ query, provider, limit }),
    }),

  lyricsSearch: (track: string, artist: string, limit = 5) =>
    request<LyricsSearchResponse>("/api/lyrics/search", {
      method: "POST",
      body: JSON.stringify({ track, artist, limit }),
    }),

  createDownload: (req: DownloadRequest) =>
    request<{ id: number }>("/api/downloads", {
      method: "POST",
      body: JSON.stringify(req),
    }),

  createBatch: (urls: string[], options?: DownloadRequest["options"]) =>
    request<{ ids: number[]; count: number }>("/api/downloads/batch", {
      method: "POST",
      body: JSON.stringify({ urls, options }),
    }),

  listDownloads: (page = 1, pageSize = 50) =>
    request<JobList>(`/api/downloads?page=${page}&page_size=${pageSize}`),

  listActiveDownloads: () => request<JobList>("/api/downloads/active"),

  getDownload: (id: number) => request<Job>(`/api/downloads/${id}`),

  cancelDownload: (id: number) =>
    request<Job>(`/api/downloads/${id}/cancel`, { method: "POST" }),

  reorderDownloads: (orderedIds: number[]) =>
    request<JobList>("/api/downloads/reorder", {
      method: "POST",
      body: JSON.stringify({ ordered_ids: orderedIds }),
    }),

  cancelDownloads: (ids: number[]) =>
    request<{ cancelled: number }>("/api/downloads/cancel", {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),

  deleteDownload: (id: number, deleteFile = false) =>
    request<void>(`/api/downloads/${id}`, {
      method: "DELETE",
      body: JSON.stringify({ delete_file: deleteFile }),
    }),

  getSettings: () => request<Settings>("/api/settings"),

  updateSettings: (patch: Partial<Settings>) =>
    request<Settings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    }),

  fileUrl: (id: number) => `/api/files/${id}`,

  lyricsFileUrl: (id: number) => `/api/files/${id}/lyrics`,

  attachLyrics: (id: number, lyrics: string) =>
    request<Job>(`/api/downloads/${id}/lyrics`, {
      method: "POST",
      body: JSON.stringify({ lyrics }),
    }),
};

// Build the absolute WebSocket URL for a job's progress stream.
export function wsUrl(jobId: number): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/downloads/${jobId}`;
}
