import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Ban, Gauge, Timer } from "lucide-react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useJobSocket } from "@/hooks/useJobSocket";
import { ApiError, api } from "@/lib/api";
import { formatBytes, formatEta, formatSpeed } from "@/lib/format";
import type { Job, JobStatus } from "@/lib/types";

const ACTIVE: JobStatus[] = ["queued", "downloading", "post-processing"];

export function DownloadCard({ job }: { job: Job }) {
  const qc = useQueryClient();
  const live = useJobSocket(job.id, ACTIVE.includes(job.status), () =>
    qc.invalidateQueries({ queryKey: ["downloads"] }),
  );

  // Merge the latest WS event over the persisted job row.
  const status = (live?.status ?? job.status) as JobStatus;
  const progress = live?.progress ?? job.progress ?? 0;
  const speed = live?.speed ?? job.speed;
  const eta = live?.eta ?? job.eta;
  const downloaded = live?.downloaded_bytes ?? job.downloaded_bytes;
  const total = live?.total_bytes ?? job.total_bytes;
  const title = job.title ?? live?.title ?? job.url;

  const cancel = useMutation({
    mutationFn: () => api.cancelDownload(job.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["downloads"] }),
    onError: (e: ApiError) => toast.error("Cancel failed", { description: e.message }),
  });

  const indeterminate = status === "queued" || (!total && status === "downloading");

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium" title={title}>
              {title}
            </p>
            <p className="truncate text-xs text-muted-foreground">{job.uploader ?? job.url}</p>
          </div>
          <StatusBadge status={status} />
        </div>

        <Progress value={indeterminate ? 100 : progress} indeterminate={indeterminate} />

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <div className="flex items-center gap-4">
            <span className="font-medium text-foreground">
              {status === "post-processing" ? "Processing…" : `${Math.round(progress)}%`}
            </span>
            {status === "downloading" && (
              <>
                <span className="inline-flex items-center gap-1">
                  <Gauge className="h-3.5 w-3.5" /> {formatSpeed(speed)}
                </span>
                <span className="inline-flex items-center gap-1">
                  <Timer className="h-3.5 w-3.5" /> {formatEta(eta)}
                </span>
                {total ? (
                  <span className="hidden sm:inline">
                    {formatBytes(downloaded)} / {formatBytes(total)}
                  </span>
                ) : null}
              </>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => cancel.mutate()}
            disabled={cancel.isPending}
            className="h-7 text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            <Ban className="h-3.5 w-3.5" /> Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
