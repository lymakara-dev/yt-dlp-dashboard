import { ChevronDown, ChevronUp, ChevronsUp, GripVertical } from "lucide-react";
import { DownloadCard } from "@/components/DownloadCard";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Job } from "@/lib/types";

interface QueueItemProps {
  job: Job;
  index: number;
  total: number;
  onMove: (from: number, to: number) => void;
  onDragStart: (index: number) => void;
  onDragOver: (index: number) => void;
  onDrop: (index: number) => void;
  selectionMode: boolean;
  selected: boolean;
  onToggleSelect: (id: number) => void;
}

export function QueueItem({
  job,
  index,
  total,
  onMove,
  onDragStart,
  onDragOver,
  onDrop,
  selectionMode,
  selected,
  onToggleSelect,
}: QueueItemProps) {
  const first = index === 0;
  const last = index === total - 1;

  return (
    <div
      draggable={!selectionMode}
      onDragStart={() => onDragStart(index)}
      onDragOver={(e) => {
        e.preventDefault();
        onDragOver(index);
      }}
      onDrop={(e) => {
        e.preventDefault();
        onDrop(index);
      }}
      className={cn(
        "flex items-stretch gap-2 rounded-xl",
        selected && "ring-2 ring-primary",
        !selectionMode && "cursor-grab active:cursor-grabbing",
      )}
    >
      <div className="flex flex-col items-center justify-center gap-1 pl-1 text-muted-foreground">
        {selectionMode ? (
          <input
            type="checkbox"
            checked={selected}
            onChange={() => onToggleSelect(job.id)}
            aria-label={`Select job ${job.id}`}
            className="h-4 w-4 accent-current"
          />
        ) : (
          <>
            <GripVertical className="h-4 w-4" aria-hidden />
            <span className="text-[11px] font-semibold tabular-nums">#{index + 1}</span>
          </>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <DownloadCard job={job} />
      </div>

      {!selectionMode && (
        <div className="flex flex-col items-center justify-center gap-1 pr-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            disabled={first}
            onClick={() => onMove(index, 0)}
            title="Download next"
            aria-label="Move to top"
          >
            <ChevronsUp className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            disabled={first}
            onClick={() => onMove(index, index - 1)}
            title="Move up"
            aria-label="Move up"
          >
            <ChevronUp className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            disabled={last}
            onClick={() => onMove(index, index + 1)}
            title="Move down"
            aria-label="Move down"
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
