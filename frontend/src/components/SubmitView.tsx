import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Braces, ClipboardPaste, Download, Loader2, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
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
  const [scheduleAt, setScheduleAt] = useState("");

  const probe = useMutation({
    mutationFn: (u: string) => api.probe(u),
    onSuccess: (data) => {
      setInfo(data);
      setSelection({ mode: "preset", preset: "best" });
      // Default playlist URLs to downloading the whole list (user can change it).
      setOptions(data.is_playlist ? { playlist: true } : {});
      setRawJson(null);
    },
    onError: (e: ApiError) => toast.error("Could not read URL", { description: e.message }),
  });

  const [rawJson, setRawJson] = useState<string | null>(null);
  const rawProbe = useMutation({
    mutationFn: (u: string) => api.probeRaw(u),
    onSuccess: (data) => setRawJson(JSON.stringify(data, null, 2)),
    onError: (e: ApiError) => toast.error("Could not extract info", { description: e.message }),
  });

  const create = useMutation({
    mutationFn: (req: DownloadRequest) => api.createDownload(req),
    onSuccess: () => {
      toast.success("Download queued");
      qc.invalidateQueries({ queryKey: ["downloads"] });
      setInfo(null);
      setUrl("");
      setOptions({});
      setScheduleAt("");
    },
    onError: (e: ApiError) => toast.error("Could not start download", { description: e.message }),
  });

  const inputRef = useRef<HTMLInputElement>(null);

  const onProbe = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) probe.mutate(url.trim());
  };

  // Keyboard shortcut: "/" focuses the URL field when not already typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement;
      const typing = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
      if (e.key === "/" && !typing) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const pasteFromClipboard = async () => {
    try {
      const text = (await navigator.clipboard.readText()).trim();
      if (!text) return;
      setUrl(text);
      probe.mutate(text);
    } catch {
      toast.error("Clipboard unavailable", { description: "Paste the URL manually (Ctrl/Cmd+V)." });
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const text = (
      e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain")
    ).trim();
    if (text) {
      setUrl(text);
      probe.mutate(text);
    }
  };

  const onDownload = () => {
    if (!info) return;
    const req: DownloadRequest = {
      url: info.url,
      subtitles: toggles.subtitles,
      embed_thumbnail: toggles.embed_thumbnail,
      sponsorblock: toggles.sponsorblock,
      options,
      // datetime-local is local time; send an absolute UTC instant.
      scheduled_at: scheduleAt ? new Date(scheduleAt).toISOString() : null,
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
        <form
          onSubmit={onProbe}
          className="flex flex-col gap-2 sm:flex-row"
          onDrop={onDrop}
          onDragOver={(e) => e.preventDefault()}
        >
          <Input
            ref={inputRef}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste or drop a URL, or press / to focus…"
            type="url"
            autoFocus
            className="h-11 text-base"
          />
          <Button
            type="button"
            variant="outline"
            size="lg"
            onClick={pasteFromClipboard}
            title="Paste from clipboard"
          >
            <ClipboardPaste className="h-4 w-4" />
            <span className="sm:hidden">Paste</span>
          </Button>
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

            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => (rawJson ? setRawJson(null) : rawProbe.mutate(info.url))}
                  disabled={rawProbe.isPending}
                >
                  {rawProbe.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Braces className="h-4 w-4" />
                  )}
                  {rawJson ? "Hide raw JSON" : "View raw JSON"}
                </Button>
                {rawJson && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => downloadText(rawJson, "info.json")}
                  >
                    <Download className="h-4 w-4" />
                    Export
                  </Button>
                )}
              </div>
              {rawJson && (
                <pre className="max-h-80 overflow-auto rounded-md border bg-muted/40 p-3 text-xs">
                  {rawJson}
                </pre>
              )}
            </div>

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

            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="flex-1 space-y-1.5">
                <Label className="text-xs text-muted-foreground">Schedule for later (optional)</Label>
                <Input
                  type="datetime-local"
                  value={scheduleAt}
                  onChange={(e) => setScheduleAt(e.target.value)}
                />
              </div>
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
              {scheduleAt ? "Schedule download" : "Download"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function downloadText(text: string, filename: string) {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
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
