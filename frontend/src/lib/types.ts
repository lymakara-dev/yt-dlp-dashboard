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

  // Thumbnails
  write_thumbnail?: boolean;
  write_all_thumbnails?: boolean;
  convert_thumbnail?: string | null;

  // Metadata
  write_info_json?: boolean;
  embed_metadata?: boolean;
  embed_chapters?: boolean;
  write_comments?: boolean;
  preserve_mtime?: boolean;

  // Filtering
  date_after?: string | null;
  date_before?: string | null;
  min_duration?: number | null;
  max_duration?: number | null;
  min_views?: number | null;
  max_views?: number | null;
  min_likes?: number | null;
  title_regex?: string | null;
  description_regex?: string | null;
  match_filter?: string | null;

  // Post-processing
  merge_output_format?: string | null;
  remux_to?: string | null;
  recode_to?: string | null;
  split_chapters?: boolean;
  sponsorblock_mark?: string[];
  sponsorblock_remove?: string[];

  // File organization
  output_template?: string | null;
  use_archive?: boolean;

  // Developer
  external_downloader?: string | null;
  external_downloader_args?: string | null;

  // Audio extraction
  audio_format?: string | null;
  audio_quality?: string | null;
  keep_audio_codec?: boolean;
  normalize_audio?: boolean;
  ffmpeg_args?: string | null;

  // Playlist
  playlist?: boolean;
  playlist_items?: string | null;
  playlist_reverse?: boolean;
  playlist_random?: boolean;
  skip_unavailable?: boolean;
  lazy_playlist?: boolean;
  ignore_duplicates?: boolean;

  // Download control
  rate_limit?: string | null;
  retries?: number | null;
  fragment_retries?: number | null;
  retry_delay?: number | null;
  concurrent_fragments?: number | null;
  resume?: boolean;
  download_sections?: string | null;
  max_filesize?: string | null;
  min_filesize?: string | null;

  // Cookies
  cookies_from_browser?: string | null;
  cookies_file?: string | null;

  // Authentication
  username?: string | null;
  password?: string | null;
  video_password?: string | null;
  twofactor?: string | null;
  netrc?: boolean;

  // Network
  proxy?: string | null;
  source_address?: string | null;
  force_ip?: string | null;
  user_agent?: string | null;
  referer?: string | null;
  http_headers?: string | null;
  geo_bypass?: boolean;
  geo_bypass_country?: string | null;
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
