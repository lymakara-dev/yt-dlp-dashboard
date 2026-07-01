// Hand-written mirror of the backend Pydantic schemas (app/schemas.py).
// Keep field names in sync with the API contract.

export type JobStatus =
  | "queued"
  | "downloading"
  | "post-processing"
  | "completed"
  | "error"
  | "cancelled";

export interface FormatInfo {
  format_id: string;
  ext: string | null;
  resolution: string | null;
  fps: number | null;
  vcodec: string | null;
  acodec: string | null;
  filesize: number | null;
  format_note: string | null;
  audio_only: boolean;
  video_only: boolean;
}

export interface ProbeResponse {
  url: string;
  title: string | null;
  uploader: string | null;
  duration: number | null;
  thumbnail: string | null;
  is_playlist: boolean;
  playlist_count: number | null;
  formats: FormatInfo[];
}

export type QualityPreset = "best" | "1080p" | "720p" | "audio";

// Mirror of backend app/options.py DownloadOptions. Every knob optional; the
// backend fills defaults. Grows as new phases add features.
export interface DownloadOptions {
  format_selector?: string | null;
  format_id?: string | null;
  quality_preset?: string | null;
  audio_only?: boolean;
  subtitles?: boolean;
  embed_thumbnail?: boolean;
  sponsorblock?: boolean;

  // Subtitles (granular)
  write_subs?: boolean;
  write_auto_subs?: boolean;
  sub_langs?: string[];
  embed_subs?: boolean;
  convert_subs?: string | null;
}

export interface DownloadRequest {
  url: string;
  format_id?: string | null;
  quality_preset?: QualityPreset | string | null;
  audio_only?: boolean;
  subtitles?: boolean;
  embed_thumbnail?: boolean;
  sponsorblock?: boolean;
  output_template?: string | null;
  options?: DownloadOptions;
}

export interface Job {
  id: number;
  url: string;
  status: JobStatus;
  format_id: string | null;
  quality_preset: string | null;
  audio_only: boolean;
  subtitles: boolean;
  embed_thumbnail: boolean;
  sponsorblock: boolean;
  output_template: string | null;
  options: DownloadOptions;

  title: string | null;
  uploader: string | null;
  duration: number | null;
  thumbnail: string | null;
  ext: string | null;

  progress: number;
  downloaded_bytes: number | null;
  total_bytes: number | null;
  speed: number | null;
  eta: number | null;
  filepath: string | null;
  filesize: number | null;
  error_message: string | null;

  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface JobList {
  items: Job[];
  total: number;
  page: number;
  page_size: number;
}

export interface Settings {
  download_dir: string;
  default_format: string;
  max_concurrency: number;
  default_output_template: string;
  naming: string;
}

export interface HealthResponse {
  status: string;
  ffmpeg: boolean;
  ffmpeg_version: string | null;
}

// WebSocket message: a live progress/state update for one job.
export interface JobEvent {
  id?: number;
  kind: "state" | "progress" | "postprocess" | "ping" | "error";
  status?: JobStatus;
  progress?: number | null;
  downloaded_bytes?: number | null;
  total_bytes?: number | null;
  speed?: number | null;
  eta?: number | null;
  title?: string | null;
  filepath?: string | null;
  filesize?: number | null;
  error_message?: string | null;
  detail?: string;
}
