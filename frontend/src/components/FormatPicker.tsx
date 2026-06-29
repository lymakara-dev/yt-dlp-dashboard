import { Music, Video, Zap } from "lucide-react";
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
  | { mode: "format"; formatId: string; audioOnly: boolean };

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
          Advanced
        </TabsTrigger>
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
    </Tabs>
  );
}
