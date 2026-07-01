import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Download, Loader2, Search } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { MetadataCard } from "@/components/MetadataCard";
import { FormatPicker, type Selection } from "@/components/FormatPicker";
import { OptionsPanel } from "@/components/OptionsPanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ApiError, api } from "@/lib/api";
import type { DownloadOptions, DownloadRequest, ProbeResponse } from "@/lib/types";

interface Toggles {
  subtitles: boolean;
  embed_thumbnail: boolean;
  sponsorblock: boolean;
}

export function SubmitView() {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [info, setInfo] = useState<ProbeResponse | null>(null);
  const [selection, setSelection] = useState<Selection>({ mode: "preset", preset: "best" });
  const [toggles, setToggles] = useState<Toggles>({
    subtitles: false,
    embed_thumbnail: false,
    sponsorblock: false,
  });
  const [options, setOptions] = useState<DownloadOptions>({});

  const probe = useMutation({
    mutationFn: (u: string) => api.probe(u),
    onSuccess: (data) => {
      setInfo(data);
      setSelection({ mode: "preset", preset: "best" });
      // Default playlist URLs to downloading the whole list (user can change it).
      setOptions(data.is_playlist ? { playlist: true } : {});
    },
    onError: (e: ApiError) => toast.error("Could not read URL", { description: e.message }),
  });

  const create = useMutation({
    mutationFn: (req: DownloadRequest) => api.createDownload(req),
    onSuccess: () => {
      toast.success("Download queued");
      qc.invalidateQueries({ queryKey: ["downloads"] });
      setInfo(null);
      setUrl("");
      setOptions({});
    },
    onError: (e: ApiError) => toast.error("Could not start download", { description: e.message }),
  });

  const onProbe = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) probe.mutate(url.trim());
  };

  const onDownload = () => {
    if (!info) return;
    const req: DownloadRequest = {
      url: info.url,
      subtitles: toggles.subtitles,
      embed_thumbnail: toggles.embed_thumbnail,
      sponsorblock: toggles.sponsorblock,
      options,
    };
    if (selection.mode === "preset") {
      req.quality_preset = selection.preset;
      req.audio_only = selection.preset === "audio";
    } else if (selection.mode === "format") {
      req.format_id = selection.formatId;
      req.audio_only = selection.audioOnly;
    } else {
      // Raw selector wins over format_id/preset in build_ydl_opts.
      req.options = { ...options, format_selector: selection.selector };
    }
    create.mutate(req);
  };

  return (
    <Card>
      <CardContent className="space-y-5 p-5 sm:p-6">
        <form onSubmit={onProbe} className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste a video or playlist URL…"
            type="url"
            autoFocus
            className="h-11 text-base"
          />
          <Button type="submit" size="lg" disabled={probe.isPending || !url.trim()}>
            {probe.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            Fetch
          </Button>
        </form>

        {probe.isError && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{(probe.error as ApiError).message}</span>
          </div>
        )}

        {info && (
          <div className="space-y-5 border-t pt-5">
            <MetadataCard info={info} />

            {info.is_playlist && (
              <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-600 dark:text-amber-400">
                This is a playlist{info.playlist_count ? ` (${info.playlist_count} items)` : ""}.
                Use <span className="font-medium">Advanced options → Playlist</span> to download
                the whole list, a range, or a single item.
              </div>
            )}

            <div className="space-y-3">
              <Label className="text-muted-foreground">Quality &amp; format</Label>
              <FormatPicker
                formats={info.formats}
                value={selection}
                onChange={setSelection}
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <ToggleRow
                id="subtitles"
                label="Subtitles"
                hint="Embed English subs"
                checked={toggles.subtitles}
                onChange={(v) => setToggles((t) => ({ ...t, subtitles: v }))}
              />
              <ToggleRow
                id="thumb"
                label="Embed thumbnail"
                hint="Cover art in file"
                checked={toggles.embed_thumbnail}
                onChange={(v) => setToggles((t) => ({ ...t, embed_thumbnail: v }))}
              />
              <ToggleRow
                id="sponsorblock"
                label="SponsorBlock"
                hint="Remove sponsor segments"
                checked={toggles.sponsorblock}
                onChange={(v) => setToggles((t) => ({ ...t, sponsorblock: v }))}
              />
            </div>

            <div className="space-y-2">
              <Label className="text-muted-foreground">Advanced options</Label>
              <OptionsPanel
                value={options}
                onChange={setOptions}
                isPlaylist={info.is_playlist}
              />
            </div>

            <Button
              onClick={onDownload}
              size="lg"
              className="w-full"
              disabled={create.isPending}
            >
              {create.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              Download
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ToggleRow({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="flex cursor-pointer items-center justify-between gap-3 rounded-lg border p-3"
    >
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        <div className="truncate text-xs text-muted-foreground">{hint}</div>
      </div>
      <Switch id={id} checked={checked} onCheckedChange={onChange} />
    </label>
  );
}
