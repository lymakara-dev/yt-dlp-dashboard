import { ChevronDown } from "lucide-react";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import type { DownloadOptions } from "@/lib/types";

/**
 * Advanced per-download options. Grows one section per feature phase. The panel
 * is a controlled editor over a partial DownloadOptions object; SubmitView owns
 * the state and forwards it to the API as `options`.
 */
export function OptionsPanel({
  value,
  onChange,
  isPlaylist = false,
}: {
  value: DownloadOptions;
  onChange: (o: DownloadOptions) => void;
  isPlaylist?: boolean;
}) {
  const set = <K extends keyof DownloadOptions>(key: K, v: DownloadOptions[K]) =>
    onChange({ ...value, [key]: v });

  return (
    <div className="space-y-2">
      <Section title="Subtitles" summary={subtitleSummary(value)}>
        <OptToggle
          label="Download subtitles"
          hint="Save uploader-provided subtitle tracks"
          checked={!!value.write_subs}
          onChange={(v) => set("write_subs", v)}
        />
        <OptToggle
          label="Auto-generated subtitles"
          hint="Include machine-generated captions"
          checked={!!value.write_auto_subs}
          onChange={(v) => set("write_auto_subs", v)}
        />
        <OptToggle
          label="Embed into video"
          hint="Mux subtitles into the media file"
          checked={!!value.embed_subs}
          onChange={(v) => set("embed_subs", v)}
        />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Languages" hint="Comma-separated, e.g. en, es, en.*">
            <Input
              value={(value.sub_langs ?? []).join(", ")}
              onChange={(e) =>
                set(
                  "sub_langs",
                  e.target.value
                    .split(",")
                    .map((s) => s.trim())
                    .filter(Boolean),
                )
              }
              placeholder="en"
            />
          </Field>
          <Field label="Convert format" hint="Re-encode downloaded subtitles">
            <Select
              value={value.convert_subs ?? "none"}
              onValueChange={(v) => set("convert_subs", v === "none" ? null : v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Keep original</SelectItem>
                <SelectItem value="srt">srt</SelectItem>
                <SelectItem value="ass">ass</SelectItem>
                <SelectItem value="vtt">vtt</SelectItem>
                <SelectItem value="lrc">lrc</SelectItem>
              </SelectContent>
            </Select>
          </Field>
        </div>
      </Section>

      <Section title="Thumbnails" summary={thumbnailSummary(value)}>
        <OptToggle
          label="Save thumbnail"
          hint="Write the cover image as a separate file"
          checked={!!value.write_thumbnail}
          onChange={(v) => set("write_thumbnail", v)}
        />
        <OptToggle
          label="Save all thumbnails"
          hint="Write every available thumbnail size"
          checked={!!value.write_all_thumbnails}
          onChange={(v) => set("write_all_thumbnails", v)}
        />
        <Field label="Convert format" hint="Re-encode saved thumbnails (needs ffmpeg)">
          <Select
            value={value.convert_thumbnail ?? "none"}
            onValueChange={(v) => set("convert_thumbnail", v === "none" ? null : v)}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Keep original</SelectItem>
              <SelectItem value="jpg">jpg</SelectItem>
              <SelectItem value="png">png</SelectItem>
              <SelectItem value="webp">webp</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <p className="text-xs text-muted-foreground">
          Embed the thumbnail into the media file using the “Embed thumbnail” toggle above.
        </p>
      </Section>

      <Section title="Audio" summary={audioSummary(value)}>
        <p className="text-xs text-muted-foreground">
          Applies when downloading audio only (choose the “Audio” preset or an audio-only format).
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Format" hint="Codec to extract to">
            <Select
              value={value.audio_format ?? "mp3"}
              onValueChange={(v) => set("audio_format", v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["mp3", "aac", "opus", "flac", "wav", "vorbis", "m4a"].map((f) => (
                  <SelectItem key={f} value={f}>
                    {f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Quality" hint="0 = best VBR, or kbps like 192/320">
            <Input
              value={value.audio_quality ?? ""}
              onChange={(e) => set("audio_quality", e.target.value || null)}
              placeholder="192"
            />
          </Field>
        </div>
        <OptToggle
          label="Keep original codec"
          hint="Copy the source audio instead of converting"
          checked={!!value.keep_audio_codec}
          onChange={(v) => set("keep_audio_codec", v)}
        />
        <OptToggle
          label="Normalize loudness"
          hint="Apply ffmpeg loudnorm (re-encodes audio)"
          checked={!!value.normalize_audio}
          onChange={(v) => set("normalize_audio", v)}
        />
        <Field label="Custom ffmpeg args" hint="Appended to ffmpeg post-processors">
          <Input
            value={value.ffmpeg_args ?? ""}
            onChange={(e) => set("ffmpeg_args", e.target.value || null)}
            placeholder="-threads 4"
            className="font-mono text-sm"
          />
        </Field>
      </Section>

      <Section title="Metadata" summary={metadataSummary(value)}>
        <OptToggle
          label="Embed metadata"
          hint="Store title, uploader, date & description in the file"
          checked={!!value.embed_metadata}
          onChange={(v) => set("embed_metadata", v)}
        />
        <OptToggle
          label="Embed chapters"
          hint="Write chapter markers into the file"
          checked={!!value.embed_chapters}
          onChange={(v) => set("embed_chapters", v)}
        />
        <OptToggle
          label="Save metadata JSON"
          hint="Write the full .info.json sidecar"
          checked={!!value.write_info_json}
          onChange={(v) => set("write_info_json", v)}
        />
        <OptToggle
          label="Fetch comments"
          hint="Include comments in the .info.json (where supported)"
          checked={!!value.write_comments}
          onChange={(v) => set("write_comments", v)}
        />
        <OptToggle
          label="Preserve upload date"
          hint="Set the file modified time to the upload date"
          checked={value.preserve_mtime !== false}
          onChange={(v) => set("preserve_mtime", v)}
        />
      </Section>

      <Section
        title="Playlist"
        summary={playlistSummary(value)}
        defaultOpen={isPlaylist}
      >
        <OptToggle
          label="Download entire playlist"
          hint="Grab every video instead of just one"
          checked={!!value.playlist}
          onChange={(v) => set("playlist", v)}
        />
        <Field label="Items / range" hint="e.g. 1-10,15,20:30 (implies whole playlist)">
          <Input
            value={value.playlist_items ?? ""}
            onChange={(e) => set("playlist_items", e.target.value || null)}
            placeholder="1-10"
          />
        </Field>
        <OptToggle
          label="Reverse order"
          checked={!!value.playlist_reverse}
          onChange={(v) => set("playlist_reverse", v)}
        />
        <OptToggle
          label="Random order"
          checked={!!value.playlist_random}
          onChange={(v) => set("playlist_random", v)}
        />
        <OptToggle
          label="Skip unavailable videos"
          hint="Continue past errored or removed entries"
          checked={!!value.skip_unavailable}
          onChange={(v) => set("skip_unavailable", v)}
        />
        <OptToggle
          label="Lazy (stream) playlist"
          hint="Start downloading before the full list is parsed"
          checked={!!value.lazy_playlist}
          onChange={(v) => set("lazy_playlist", v)}
        />
        <OptToggle
          label="Ignore duplicates"
          hint="Use a download archive to skip already-downloaded videos"
          checked={!!value.ignore_duplicates}
          onChange={(v) => set("ignore_duplicates", v)}
        />
      </Section>

      <Section title="Download control" summary={downloadControlSummary(value)}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Speed limit" hint="e.g. 2M, 500K (per download)">
            <Input
              value={value.rate_limit ?? ""}
              onChange={(e) => set("rate_limit", e.target.value || null)}
              placeholder="unlimited"
            />
          </Field>
          <Field label="Concurrent fragments" hint="Parallel fragment downloads">
            <Input
              type="number"
              min={1}
              value={value.concurrent_fragments ?? ""}
              onChange={(e) => set("concurrent_fragments", numOrNull(e.target.value))}
              placeholder="1"
            />
          </Field>
          <Field label="Retries">
            <Input
              type="number"
              min={0}
              value={value.retries ?? ""}
              onChange={(e) => set("retries", numOrNull(e.target.value))}
              placeholder="10"
            />
          </Field>
          <Field label="Fragment retries">
            <Input
              type="number"
              min={0}
              value={value.fragment_retries ?? ""}
              onChange={(e) => set("fragment_retries", numOrNull(e.target.value))}
              placeholder="10"
            />
          </Field>
          <Field label="Retry delay (s)">
            <Input
              type="number"
              min={0}
              value={value.retry_delay ?? ""}
              onChange={(e) => set("retry_delay", numOrNull(e.target.value))}
              placeholder="0"
            />
          </Field>
          <Field label="Download sections" hint="e.g. *10:00-15:00 or a chapter regex">
            <Input
              value={value.download_sections ?? ""}
              onChange={(e) => set("download_sections", e.target.value || null)}
              placeholder="*00:30-02:00"
              className="font-mono text-sm"
            />
          </Field>
          <Field label="Max file size" hint="Skip larger, e.g. 500M">
            <Input
              value={value.max_filesize ?? ""}
              onChange={(e) => set("max_filesize", e.target.value || null)}
              placeholder="none"
            />
          </Field>
          <Field label="Min file size" hint="Skip smaller, e.g. 1M">
            <Input
              value={value.min_filesize ?? ""}
              onChange={(e) => set("min_filesize", e.target.value || null)}
              placeholder="none"
            />
          </Field>
        </div>
        <OptToggle
          label="Resume partial downloads"
          hint="Continue from an interrupted .part file"
          checked={value.resume !== false}
          onChange={(v) => set("resume", v)}
        />
      </Section>
    </div>
  );
}

function numOrNull(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function downloadControlSummary(o: DownloadOptions): string | null {
  const parts: string[] = [];
  if (o.rate_limit) parts.push(`≤${o.rate_limit}`);
  if (o.download_sections) parts.push("sections");
  if (o.concurrent_fragments) parts.push(`${o.concurrent_fragments}x frags`);
  return parts.length ? parts.join(" · ") : null;
}

function playlistSummary(o: DownloadOptions): string | null {
  const parts: string[] = [];
  if (o.playlist_items) parts.push(o.playlist_items);
  else if (o.playlist) parts.push("all");
  if (o.playlist_reverse) parts.push("reverse");
  if (o.playlist_random) parts.push("random");
  return parts.length ? parts.join(" · ") : null;
}

function audioSummary(o: DownloadOptions): string | null {
  const parts: string[] = [];
  if (o.keep_audio_codec) parts.push("copy");
  else if (o.audio_format) parts.push(o.audio_format);
  if (o.audio_quality) parts.push(`q${o.audio_quality}`);
  if (o.normalize_audio) parts.push("loudnorm");
  return parts.length ? parts.join(" · ") : null;
}

function metadataSummary(o: DownloadOptions): string | null {
  const parts: string[] = [];
  if (o.embed_metadata) parts.push("embed");
  if (o.embed_chapters) parts.push("chapters");
  if (o.write_info_json) parts.push("json");
  if (o.write_comments) parts.push("comments");
  return parts.length ? parts.join(" · ") : null;
}

function thumbnailSummary(o: DownloadOptions): string | null {
  const parts: string[] = [];
  if (o.write_all_thumbnails) parts.push("all");
  else if (o.write_thumbnail) parts.push("save");
  if (o.convert_thumbnail) parts.push(o.convert_thumbnail);
  return parts.length ? parts.join(" · ") : null;
}

function subtitleSummary(o: DownloadOptions): string | null {
  const on = o.write_subs || o.write_auto_subs || o.embed_subs;
  if (!on) return null;
  const langs = (o.sub_langs ?? []).join(", ") || "en";
  return `${o.embed_subs ? "embed · " : ""}${langs}`;
}

// ---- shared building blocks (reused by every phase's section) ----

export function Section({
  title,
  summary,
  defaultOpen = false,
  children,
}: {
  title: string;
  summary?: string | null;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
      >
        <span className="text-sm font-medium">{title}</span>
        <span className="flex items-center gap-2">
          {summary ? (
            <span className="truncate text-xs text-muted-foreground">{summary}</span>
          ) : null}
          <ChevronDown
            className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-180")}
          />
        </span>
      </button>
      {open ? <div className="space-y-3 border-t px-3 py-3">{children}</div> : null}
    </div>
  );
}

export function OptToggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3">
      <div className="min-w-0">
        <div className="text-sm">{label}</div>
        {hint ? <div className="truncate text-xs text-muted-foreground">{hint}</div> : null}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </label>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
