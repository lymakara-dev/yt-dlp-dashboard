import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, ListMusic } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ApiError, api } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { SearchResultItem } from "@/lib/types";

const LIMITS = [
  { value: "0", label: "All videos" },
  { value: "25", label: "First 25" },
  { value: "50", label: "First 50" },
  { value: "100", label: "First 100" },
];

/** Paste a channel / uploads playlist URL, review every song it contains, then
 * queue the ones you want as individual download jobs. */
export function ArtistPage() {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [limit, setLimit] = useState("0");
  const [audioOnly, setAudioOnly] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const expand = useMutation({
    mutationFn: () => api.expandArtist(url.trim(), Number(limit) || undefined),
    onSuccess: (res) => {
      setSelected(new Set(res.entries.map((e) => e.url).filter((u): u is string => !!u)));
    },
    onError: (e: ApiError) => toast.error("Could not load videos", { description: e.message }),
  });

  const batch = useMutation({
    mutationFn: (urls: string[]) => api.createBatch(urls, { audio_only: audioOnly }),
    onSuccess: (res) => {
      toast.success(`Queued ${res.count} song${res.count === 1 ? "" : "s"}`);
      qc.invalidateQueries({ queryKey: ["downloads"] });
      setSelected(new Set());
      expand.reset();
      setUrl("");
    },
    onError: (e: ApiError) => toast.error("Could not queue songs", { description: e.message }),
  });

  const onExpand = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) expand.mutate();
  };

  const entries = expand.data?.entries ?? [];
  const validEntries = entries.filter((e): e is SearchResultItem & { url: string } => !!e.url);
  const allSelected = validEntries.length > 0 && selected.size === validEntries.length;

  const toggle = (u: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(u)) next.delete(u);
      else next.add(u);
      return next;
    });
  };

  const toggleAll = () => {
    setSelected(allSelected ? new Set() : new Set(validEntries.map((e) => e.url)));
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-5 sm:p-6">
          <form onSubmit={onExpand} className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Channel, Videos tab, or uploads playlist URL…"
              autoFocus
              className="h-11 text-base"
            />
            <Select value={limit} onValueChange={setLimit}>
              <SelectTrigger className="h-11 sm:w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LIMITS.map((l) => (
                  <SelectItem key={l.value} value={l.value}>
                    {l.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button type="submit" size="lg" disabled={expand.isPending || !url.trim()}>
              {expand.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ListMusic className="h-4 w-4" />
              )}
              Load songs
            </Button>
          </form>
          <p className="text-xs text-muted-foreground">
            Tip: use the artist channel's "Videos" tab URL (or an uploads playlist) to list every
            upload. A bare channel URL usually works too.
          </p>
        </CardContent>
      </Card>

      {validEntries.length > 0 && (
        <Card>
          <CardContent className="space-y-3 p-5 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate font-medium">
                  {expand.data?.title ?? expand.data?.uploader ?? "Songs found"}
                </div>
                <div className="text-xs text-muted-foreground">
                  {validEntries.length} video{validEntries.length === 1 ? "" : "s"} ·{" "}
                  {selected.size} selected
                </div>
              </div>
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <Switch checked={audioOnly} onCheckedChange={setAudioOnly} />
                  Audio only
                </label>
                <Button type="button" variant="outline" size="sm" onClick={toggleAll}>
                  {allSelected ? "Deselect all" : "Select all"}
                </Button>
              </div>
            </div>

            <div className="max-h-[28rem] space-y-2 overflow-y-auto">
              {validEntries.map((entry) => (
                <EntryRow
                  key={entry.url}
                  entry={entry}
                  checked={selected.has(entry.url)}
                  onToggle={() => toggle(entry.url)}
                />
              ))}
            </div>

            <Button
              type="button"
              size="lg"
              onClick={() => batch.mutate([...selected])}
              disabled={batch.isPending || selected.size === 0}
            >
              {batch.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              Queue {selected.size || ""} song{selected.size === 1 ? "" : "s"}
            </Button>
          </CardContent>
        </Card>
      )}

      {expand.isSuccess && validEntries.length === 0 && (
        <p className="text-sm text-muted-foreground">No videos found at this URL.</p>
      )}
    </div>
  );
}

function EntryRow({
  entry,
  checked,
  onToggle,
}: {
  entry: SearchResultItem;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-3 rounded-lg border p-2 hover:bg-accent/50">
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        aria-label={`Select ${entry.title ?? "video"}`}
        className="h-4 w-4 shrink-0 accent-current"
      />
      {entry.thumbnail ? (
        <img
          src={entry.thumbnail}
          alt=""
          className="h-12 w-20 shrink-0 rounded object-cover"
          loading="lazy"
        />
      ) : (
        <div className="h-12 w-20 shrink-0 rounded bg-muted" />
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{entry.title ?? "Untitled"}</div>
        <div className="truncate text-xs text-muted-foreground">
          {[entry.uploader, entry.duration ? formatDuration(entry.duration) : null]
            .filter(Boolean)
            .join(" · ")}
        </div>
      </div>
    </label>
  );
}
