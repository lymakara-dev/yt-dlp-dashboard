import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Music } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { LyricsCandidate, SearchResultItem } from "@/lib/types";

export function LyricsPage() {
  const qc = useQueryClient();
  const [track, setTrack] = useState("");
  const [artist, setArtist] = useState("");
  const [selected, setSelected] = useState(0); // index into lyrics candidates

  const search = useMutation({
    mutationFn: () => api.lyricsSearch(track.trim(), artist.trim()),
    onSuccess: () => setSelected(0),
    onError: (e: ApiError) => toast.error("Search failed", { description: e.message }),
  });

  const create = useMutation({
    mutationFn: (url: string) => {
      const lyric = search.data?.lyrics[selected];
      return api.createDownload({
        url,
        options: {
          audio_only: true,
          audio_format: "mp3",
          lyrics_synced: lyric?.synced_lyrics ?? null,
          lyrics_plain: lyric?.plain_lyrics ?? null,
        },
      });
    },
    onSuccess: () => {
      toast.success("Download queued with lyrics");
      qc.invalidateQueries({ queryKey: ["downloads"] });
    },
    onError: (e: ApiError) =>
      toast.error("Could not start download", { description: e.message }),
  });

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (track.trim() && artist.trim()) search.mutate();
  };

  const data = search.data;
  const lyrics = data?.lyrics ?? [];
  const audio = data?.audio ?? [];
  const current = lyrics[selected];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-5 sm:p-6">
          <form onSubmit={onSearch} className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={track}
              onChange={(e) => setTrack(e.target.value)}
              placeholder="Song title…"
              autoFocus
              className="h-11 text-base"
            />
            <Input
              value={artist}
              onChange={(e) => setArtist(e.target.value)}
              placeholder="Artist…"
              className="h-11 text-base"
            />
            <Button
              type="submit"
              size="lg"
              disabled={search.isPending || !track.trim() || !artist.trim()}
            >
              {search.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Music className="h-4 w-4" />
              )}
              Find
            </Button>
          </form>
        </CardContent>
      </Card>

      {data && !data.lyrics_available && (
        <p className="text-sm text-amber-600">
          Lyrics service was unreachable — you can still download audio without lyrics.
        </p>
      )}

      {lyrics.length > 0 && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap gap-2">
              {lyrics.map((l, i) => (
                <button
                  key={`${l.track}-${i}`}
                  type="button"
                  onClick={() => setSelected(i)}
                  className={
                    "rounded-md border px-2.5 py-1 text-xs " +
                    (i === selected
                      ? "border-primary bg-secondary"
                      : "text-muted-foreground")
                  }
                >
                  {l.track ?? "?"} — {l.artist ?? "?"}
                  {l.duration ? ` · ${formatDuration(l.duration)}` : ""}
                </button>
              ))}
            </div>
            <LyricsPreview candidate={current} />
          </CardContent>
        </Card>
      )}

      {data && lyrics.length === 0 && data.lyrics_available && (
        <p className="text-sm text-muted-foreground">
          No lyrics found. Pick an audio track to download without lyrics.
        </p>
      )}

      {audio.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-medium">Pick the matching track:</p>
          {audio.map((r) => (
            <AudioRow
              key={r.url ?? r.title}
              result={r}
              onDownload={() => r.url && create.mutate(r.url)}
              downloading={create.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function LyricsPreview({ candidate }: { candidate: LyricsCandidate | undefined }) {
  if (!candidate) return null;
  const text = candidate.synced_lyrics ?? candidate.plain_lyrics ?? "";
  return (
    <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-3 text-xs">
      {text || "No preview available."}
    </pre>
  );
}

function AudioRow({
  result,
  onDownload,
  downloading,
}: {
  result: SearchResultItem;
  onDownload: () => void;
  downloading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-3">
        {result.thumbnail ? (
          <img
            src={result.thumbnail}
            alt=""
            className="h-14 w-24 shrink-0 rounded object-cover"
            loading="lazy"
          />
        ) : (
          <div className="h-14 w-24 shrink-0 rounded bg-muted" />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{result.title ?? "Untitled"}</div>
          <div className="truncate text-xs text-muted-foreground">
            {[result.uploader, result.duration ? formatDuration(result.duration) : null]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={onDownload}
          disabled={downloading || !result.url}
        >
          <Download className="h-4 w-4" />
          Queue mp3 + lyrics
        </Button>
      </CardContent>
    </Card>
  );
}
