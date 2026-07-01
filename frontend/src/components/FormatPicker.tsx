import { Music, Video, Zap } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatBytes } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FormatInfo, QualityPreset } from "@/lib/types";

export type Selection =
  | { mode: "preset"; preset: QualityPreset }
  | { mode: "format"; formatId: string; audioOnly: boolean }
  | { mode: "selector"; selector: string };

// Copy-paste yt-dlp format selector snippets surfaced as quick-insert chips.
const SELECTOR_EXAMPLES: { label: string; value: string }[] = [
  { label: "best", value: "best" },
  { label: "bv+ba", value: "bestvideo+bestaudio" },
  { label: "worst", value: "worst" },
  { label: "video only", value: "bv" },
  { label: "audio only", value: "ba" },
  { label: "≤1080p", value: "bv*[height<=1080]+ba/b[height<=1080]" },
  { label: "≥60fps", value: "bv*[fps>=60]+ba/b" },
  { label: "avc1 (H.264)", value: "bv*[vcodec^=avc1]+ba/b" },
  { label: "av01", value: "bv*[vcodec^=av01]+ba/b" },
  { label: "HDR", value: "bv*[dynamic_range*=HDR]+ba/b" },
  { label: "≤2 Mbps", value: "bv*[tbr<=2000]+ba/b" },
  { label: "mp4 only", value: "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]" },
];

const PRESETS: { key: QualityPreset; label: string; hint: string; icon: typeof Zap }[] = [
  { key: "best", label: "Best", hint: "Video + audio", icon: Zap },
  { key: "1080p", label: "1080p", hint: "Full HD", icon: Video },
  { key: "720p", label: "720p", hint: "HD", icon: Video },
  { key: "audio", label: "Audio (mp3)", hint: "Audio only", icon: Music },
];

function describeFormat(f: FormatInfo): string {
  const parts: string[] = [f.format_id];
  if (f.ext) parts.push(f.ext);
  if (f.audio_only) parts.push("audio");
  else if (f.resolution) parts.push(f.resolution);
  if (f.fps) parts.push(`${f.fps}fps`);
  const codecs = [f.vcodec, f.acodec].filter(Boolean).join("/");
  if (codecs) parts.push(codecs);
  if (f.filesize) parts.push(formatBytes(f.filesize));
  if (f.format_note) parts.push(f.format_note);
  return parts.join(" · ");
}

export function FormatPicker({
  formats,
  value,
  onChange,
}: {
  formats: FormatInfo[];
  value: Selection;
  onChange: (s: Selection) => void;
}) {
  const hasFormats = formats.length > 0;
  return (
    <Tabs defaultValue="presets" className="w-full">
      <TabsList>
        <TabsTrigger value="presets">Presets</TabsTrigger>
        <TabsTrigger value="advanced" disabled={!hasFormats}>
          Format ID
        </TabsTrigger>
        <TabsTrigger value="selector">Selector</TabsTrigger>
      </TabsList>

      <TabsContent value="presets">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {PRESETS.map(({ key, label, hint, icon: Icon }) => {
            const active = value.mode === "preset" && value.preset === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => onChange({ mode: "preset", preset: key })}
                className={cn(
                  "flex flex-col items-start gap-1 rounded-lg border p-3 text-left transition-colors",
                  active
                    ? "border-primary bg-primary/10 ring-1 ring-primary"
                    : "border-border hover:bg-secondary",
                )}
              >
                <Icon
                  className={cn("h-4 w-4", active ? "text-primary" : "text-muted-foreground")}
                />
                <span className="text-sm font-medium">{label}</span>
                <span className="text-xs text-muted-foreground">{hint}</span>
              </button>
            );
          })}
        </div>
      </TabsContent>

      <TabsContent value="advanced">
        <Select
          value={value.mode === "format" ? value.formatId : undefined}
          onValueChange={(formatId) => {
            const f = formats.find((x) => x.format_id === formatId);
            onChange({ mode: "format", formatId, audioOnly: f?.audio_only ?? false });
          }}
        >
          <SelectTrigger>
            <SelectValue placeholder="Pick a specific format id…" />
          </SelectTrigger>
          <SelectContent>
            {formats.map((f) => (
              <SelectItem key={f.format_id} value={f.format_id}>
                {describeFormat(f)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="mt-2 text-xs text-muted-foreground">
          Video-only formats are automatically merged with the best audio track.
        </p>
      </TabsContent>

      <TabsContent value="selector">
        <Input
          value={value.mode === "selector" ? value.selector : ""}
          onChange={(e) => onChange({ mode: "selector", selector: e.target.value })}
          placeholder="e.g. bv*[height<=1080][fps>=60]+ba/b"
          className="font-mono text-sm"
        />
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SELECTOR_EXAMPLES.map((ex) => (
            <button
              key={ex.label}
              type="button"
              onClick={() => onChange({ mode: "selector", selector: ex.value })}
              className="rounded-full border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            >
              {ex.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          Any yt-dlp{" "}
          <a
            href="https://github.com/yt-dlp/yt-dlp#format-selection"
            target="_blank"
            rel="noreferrer"
            className="underline"
          >
            format selector
          </a>{" "}
          is passed through verbatim.
        </p>
      </TabsContent>
    </Tabs>
  );
}
