import {
  CalendarClock,
  CheckCircle2,
  CircleSlash,
  Clock,
  Download,
  Loader2,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { JobStatus } from "@/lib/types";

const MAP: Record<
  JobStatus,
  { label: string; variant: "default" | "secondary" | "success" | "warning" | "destructive"; spin?: boolean; icon: typeof Clock }
> = {
  scheduled: { label: "Scheduled", variant: "secondary", icon: CalendarClock },
  queued: { label: "Queued", variant: "secondary", icon: Clock },
  downloading: { label: "Downloading", variant: "default", icon: Download },
  "post-processing": { label: "Processing", variant: "warning", spin: true, icon: Loader2 },
  completed: { label: "Completed", variant: "success", icon: CheckCircle2 },
  error: { label: "Error", variant: "destructive", icon: XCircle },
  cancelled: { label: "Cancelled", variant: "secondary", icon: CircleSlash },
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const cfg = MAP[status] ?? MAP.queued;
  const Icon = cfg.icon;
  return (
    <Badge variant={cfg.variant}>
      <Icon className={cfg.spin ? "h-3 w-3 animate-spin" : "h-3 w-3"} />
      {cfg.label}
    </Badge>
  );
}
