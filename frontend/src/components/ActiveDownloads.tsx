import { useQuery } from "@tanstack/react-query";
import { Inbox } from "lucide-react";
import { DownloadCard } from "@/components/DownloadCard";
import { api } from "@/lib/api";
import type { JobStatus } from "@/lib/types";

const ACTIVE: JobStatus[] = ["queued", "downloading", "post-processing"];

export function ActiveDownloads() {
  const { data } = useQuery({
    queryKey: ["downloads"],
    queryFn: () => api.listDownloads(1, 100),
    // Safety-net refresh; live updates come over WebSocket.
    refetchInterval: 5000,
  });

  const active = (data?.items ?? []).filter((j) => ACTIVE.includes(j.status));

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Active downloads
        </h2>
        {active.length > 0 && (
          <span className="text-xs text-muted-foreground">{active.length} running</span>
        )}
      </div>

      {active.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed py-10 text-center text-muted-foreground">
          <Inbox className="h-6 w-6" />
          <p className="text-sm">No active downloads. Paste a URL above to get started.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {active.map((job) => (
            <DownloadCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </section>
  );
}
