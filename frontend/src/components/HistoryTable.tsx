import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, History, MoreHorizontal, RotateCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, api } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";
import type { DownloadRequest, Job } from "@/lib/types";

function formatLabel(job: Job): string {
  if (job.audio_only) return "Audio (mp3)";
  if (job.quality_preset) return job.quality_preset;
  if (job.format_id) return `id ${job.format_id}`;
  return "best";
}

export function HistoryTable() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["downloads"],
    queryFn: () => api.listDownloads(1, 100),
    refetchInterval: 5000,
  });

  const redownload = useMutation({
    mutationFn: (job: Job) => {
      const req: DownloadRequest = {
        url: job.url,
        format_id: job.format_id,
        quality_preset: job.quality_preset,
        audio_only: job.audio_only,
        subtitles: job.subtitles,
        embed_thumbnail: job.embed_thumbnail,
        sponsorblock: job.sponsorblock,
        output_template: job.output_template,
      };
      return api.createDownload(req);
    },
    onSuccess: () => {
      toast.success("Re-queued download");
      qc.invalidateQueries({ queryKey: ["downloads"] });
    },
    onError: (e: ApiError) => toast.error("Re-download failed", { description: e.message }),
  });

  const remove = useMutation({
    mutationFn: ({ id, deleteFile }: { id: number; deleteFile: boolean }) =>
      api.deleteDownload(id, deleteFile),
    onSuccess: () => {
      toast.success("Removed from history");
      qc.invalidateQueries({ queryKey: ["downloads"] });
    },
    onError: (e: ApiError) => toast.error("Delete failed", { description: e.message }),
  });

  const items = data?.items ?? [];

  return (
    <Card className="overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className="w-[34%]">Title</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Format</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Date</TableHead>
            <TableHead className="w-10 text-right" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {isLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell colSpan={6}>
                  <Skeleton className="h-5 w-full" />
                </TableCell>
              </TableRow>
            ))
          ) : items.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={6}>
                <div className="flex flex-col items-center gap-2 py-10 text-muted-foreground">
                  <History className="h-6 w-6" />
                  <p className="text-sm">No downloads yet.</p>
                </div>
              </TableCell>
            </TableRow>
          ) : (
            items.map((job) => (
              <TableRow key={job.id}>
                <TableCell className="max-w-0">
                  <p className="truncate font-medium" title={job.title ?? job.url}>
                    {job.title ?? job.url}
                  </p>
                  <p className="truncate text-xs text-muted-foreground">
                    {job.uploader ?? job.url}
                  </p>
                  {job.status === "error" && job.error_message ? (
                    <p className="truncate text-xs text-destructive" title={job.error_message}>
                      {job.error_message}
                    </p>
                  ) : null}
                </TableCell>
                <TableCell>
                  <StatusBadge status={job.status} />
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                  {formatLabel(job)}
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                  {formatBytes(job.filesize)}
                </TableCell>
                <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                  {formatDate(job.created_at)}
                </TableCell>
                <TableCell className="text-right">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      {job.status === "completed" && job.filepath ? (
                        <DropdownMenuItem asChild>
                          <a href={api.fileUrl(job.id)} download>
                            <Download className="h-4 w-4" /> Download file
                          </a>
                        </DropdownMenuItem>
                      ) : null}
                      <DropdownMenuItem onClick={() => redownload.mutate(job)}>
                        <RotateCw className="h-4 w-4" /> Re-download
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      {job.status === "completed" && job.filepath ? (
                        <DropdownMenuItem
                          className="text-destructive focus:bg-destructive/10"
                          onClick={() => remove.mutate({ id: job.id, deleteFile: true })}
                        >
                          <Trash2 className="h-4 w-4" /> Delete + file
                        </DropdownMenuItem>
                      ) : null}
                      <DropdownMenuItem
                        className="text-destructive focus:bg-destructive/10"
                        onClick={() => remove.mutate({ id: job.id, deleteFile: false })}
                      >
                        <Trash2 className="h-4 w-4" /> Remove from history
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </Card>
  );
}
