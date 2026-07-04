import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckSquare, Inbox, Trash2, X } from "lucide-react";
import { type ReactNode, useState } from "react";
import { toast } from "sonner";
import { DownloadCard } from "@/components/DownloadCard";
import { QueueItem } from "@/components/QueueItem";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { Job, JobList, JobStatus } from "@/lib/types";

const RUNNING: JobStatus[] = ["downloading", "post-processing"];

// The Queue owns its own cache slot so it doesn't collide with HistoryTable's
// ["downloads"] query (which fetches a different shape). A ["downloads"] prefix
// invalidation from anywhere still refreshes this — React Query matches by prefix.
const QUEUE_KEY = ["downloads", "active"] as const;

export function QueuePage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: () => api.listActiveDownloads(),
    refetchInterval: 5000,
  });

  const jobs = data?.items ?? [];
  const running = jobs.filter((j) => RUNNING.includes(j.status));
  const scheduled = jobs.filter((j) => j.status === "scheduled");
  const queued = jobs
    .filter((j) => j.status === "queued")
    .sort((a, b) => a.queue_position - b.queue_position);

  const [selectionMode, setSelectionMode] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [dragFrom, setDragFrom] = useState<number | null>(null);

  const reorder = useMutation({
    mutationFn: (ids: number[]) => api.reorderDownloads(ids),
    // Optimistic: reflect the new order immediately so DnD feels instant.
    onMutate: async (ids: number[]) => {
      await qc.cancelQueries({ queryKey: QUEUE_KEY });
      const prev = qc.getQueryData<JobList>(QUEUE_KEY);
      if (prev) {
        const pos = new Map(ids.map((id, i) => [id, i + 1]));
        qc.setQueryData<JobList>(QUEUE_KEY, {
          ...prev,
          items: prev.items.map((j) =>
            pos.has(j.id) ? { ...j, queue_position: pos.get(j.id)! } : j,
          ),
        });
      }
      return { prev };
    },
    onError: (e: ApiError, _ids, ctx) => {
      if (ctx?.prev) qc.setQueryData(QUEUE_KEY, ctx.prev);
      toast.error("Reorder failed", { description: e.message });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["downloads"] }),
  });

  const bulkCancel = useMutation({
    mutationFn: (ids: number[]) => api.cancelDownloads(ids),
    onSuccess: (res) => {
      toast.success(`Cancelled ${res.cancelled} download${res.cancelled === 1 ? "" : "s"}`);
      setSelected(new Set());
      setSelectionMode(false);
      qc.invalidateQueries({ queryKey: ["downloads"] });
    },
    onError: (e: ApiError) => toast.error("Cancel failed", { description: e.message }),
  });

  function applyOrder(next: Job[]) {
    reorder.mutate(next.map((j) => j.id));
  }

  function move(from: number, to: number) {
    if (to < 0 || to >= queued.length || from === to) return;
    const next = [...queued];
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    applyOrder(next);
  }

  function handleDrop(target: number) {
    if (dragFrom === null) return;
    move(dragFrom, target);
    setDragFrom(null);
  }

  function toggleSelect(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const activeCount = running.length + queued.length + scheduled.length;

  if (activeCount === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed py-14 text-center text-muted-foreground">
        <Inbox className="h-6 w-6" />
        <p className="text-sm">The queue is empty. Add a download to get started.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          {activeCount} in queue
          {running.length > 0 && ` · ${running.length} downloading`}
        </span>
        <div className="flex items-center gap-2">
          {queued.length > 0 && !selectionMode && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => bulkCancel.mutate(queued.map((j) => j.id))}
              disabled={bulkCancel.isPending}
            >
              <Trash2 className="h-3.5 w-3.5" /> Cancel all queued
            </Button>
          )}
          {queued.length > 0 && (
            <Button
              variant={selectionMode ? "secondary" : "outline"}
              size="sm"
              onClick={() => {
                setSelectionMode((m) => !m);
                setSelected(new Set());
              }}
            >
              {selectionMode ? <X className="h-3.5 w-3.5" /> : <CheckSquare className="h-3.5 w-3.5" />}
              {selectionMode ? "Done" : "Select"}
            </Button>
          )}
        </div>
      </div>

      {/* Selection action bar */}
      {selectionMode && selected.size > 0 && (
        <div className="flex items-center justify-between rounded-lg border bg-secondary/40 px-3 py-2 text-sm">
          <span>{selected.size} selected</span>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:bg-destructive/10 hover:text-destructive"
            onClick={() => bulkCancel.mutate([...selected])}
            disabled={bulkCancel.isPending}
          >
            <Trash2 className="h-3.5 w-3.5" /> Cancel selected
          </Button>
        </div>
      )}

      {running.length > 0 && (
        <Section title="Downloading now">
          {running.map((job) => (
            <DownloadCard key={job.id} job={job} />
          ))}
        </Section>
      )}

      {queued.length > 0 && (
        <Section title="Up next">
          {queued.map((job, i) => (
            <QueueItem
              key={job.id}
              job={job}
              index={i}
              total={queued.length}
              onMove={move}
              onDragStart={setDragFrom}
              onDragOver={() => {}}
              onDrop={handleDrop}
              selectionMode={selectionMode}
              selected={selected.has(job.id)}
              onToggleSelect={toggleSelect}
            />
          ))}
        </Section>
      )}

      {scheduled.length > 0 && (
        <Section title="Scheduled">
          {scheduled.map((job) => (
            <DownloadCard key={job.id} job={job} />
          ))}
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}
