import { Clock, ListVideo, User } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { formatDuration } from "@/lib/format";
import type { ProbeResponse } from "@/lib/types";

export function MetadataCard({ info }: { info: ProbeResponse }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row">
      <div className="relative aspect-video w-full shrink-0 overflow-hidden rounded-lg bg-secondary sm:w-64">
        {info.thumbnail ? (
          <img
            src={info.thumbnail}
            alt={info.title ?? "thumbnail"}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-muted-foreground">
            <ListVideo className="h-8 w-8" />
          </div>
        )}
        {info.duration ? (
          <span className="absolute bottom-1.5 right-1.5 rounded bg-black/80 px-1.5 py-0.5 text-xs font-medium text-white">
            {formatDuration(info.duration)}
          </span>
        ) : null}
      </div>

      <div className="min-w-0 flex-1 space-y-2">
        <h3 className="line-clamp-2 text-lg font-semibold leading-snug">
          {info.title ?? "Untitled"}
        </h3>
        <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
          {info.uploader ? (
            <span className="inline-flex items-center gap-1.5">
              <User className="h-3.5 w-3.5" /> {info.uploader}
            </span>
          ) : null}
          {info.duration ? (
            <span className="inline-flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" /> {formatDuration(info.duration)}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          {info.is_playlist ? (
            <Badge variant="warning">
              <ListVideo className="h-3 w-3" /> Playlist · {info.playlist_count ?? "?"} items
            </Badge>
          ) : (
            <Badge variant="secondary">{info.formats.length} formats available</Badge>
          )}
        </div>
      </div>
    </div>
  );
}
