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
}: {
  value: DownloadOptions;
  onChange: (o: DownloadOptions) => void;
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
    </div>
  );
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
