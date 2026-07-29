import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import type { Settings } from "@/lib/types";

const FORMAT_OPTIONS = [
  { value: "best", label: "Best (video + audio)" },
  { value: "1080p", label: "1080p" },
  { value: "720p", label: "720p" },
  { value: "audio", label: "Audio only (mp3)" },
];

export function SettingsPage() {
  const qc = useQueryClient();
  const { data: settings, isLoading } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.getSettings(),
  });
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: () => api.health() });
  const { data: telegramStatus } = useQuery({
    queryKey: ["telegram-status"],
    queryFn: () => api.getTelegramStatus(),
  });

  const [form, setForm] = useState<Settings | null>(null);
  useEffect(() => {
    if (settings) setForm(settings);
  }, [settings]);

  const save = useMutation({
    mutationFn: (patch: Partial<Settings>) => api.updateSettings(patch),
    onSuccess: (data) => {
      setForm(data);
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success("Settings saved");
    },
    onError: (e: ApiError) => toast.error("Could not save settings", { description: e.message }),
  });

  if (isLoading || !form) {
    return (
      <Card>
        <CardContent className="space-y-4 p-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  const update = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Environment</CardTitle>
          <CardDescription>Runtime dependencies detected by the backend.</CardDescription>
        </CardHeader>
        <CardContent>
          {health?.ffmpeg ? (
            <div className="flex items-center gap-2 text-sm text-emerald-500">
              <CheckCircle2 className="h-4 w-4" />
              ffmpeg detected
              {health.ffmpeg_version ? (
                <span className="text-muted-foreground">
                  · {health.ffmpeg_version.replace("ffmpeg version ", "").split(" ")[0]}
                </span>
              ) : null}
            </div>
          ) : (
            <div className="flex items-center gap-2 text-sm text-amber-500">
              <AlertTriangle className="h-4 w-4" />
              ffmpeg not found — merging, audio extraction, thumbnails and SponsorBlock will fail.
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Download settings</CardTitle>
          <CardDescription>These apply to new downloads.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Field label="Download directory" hint="Absolute path on the server.">
            <Input
              value={form.download_dir}
              onChange={(e) => update("download_dir", e.target.value)}
              placeholder="/downloads"
            />
          </Field>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Default format" hint="Preset for new downloads.">
              <Select
                value={form.default_format}
                onValueChange={(v) => update("default_format", v)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FORMAT_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>

            <Field label="Max concurrency" hint="Simultaneous downloads (1–16).">
              <Input
                type="number"
                min={1}
                max={16}
                value={form.max_concurrency}
                onChange={(e) => update("max_concurrency", Number(e.target.value))}
              />
            </Field>
          </div>

          <Field
            label="Output template"
            hint="yt-dlp output template, e.g. %(title)s [%(id)s].%(ext)s"
          >
            <Input
              value={form.default_output_template}
              onChange={(e) => update("default_output_template", e.target.value)}
              className="font-mono text-sm"
            />
          </Field>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field
              label="Watch folder"
              hint="Auto-queue URLs from *.txt files dropped here. Blank = disabled."
            >
              <Input
                value={form.watch_folder}
                onChange={(e) => update("watch_folder", e.target.value)}
                placeholder="/watch"
                className="font-mono text-sm"
              />
            </Field>
            <Field label="Watch interval (s)" hint="How often to scan (5–3600).">
              <Input
                type="number"
                min={5}
                max={3600}
                value={form.watch_interval}
                onChange={(e) => update("watch_interval", Number(e.target.value))}
              />
            </Field>
          </div>

          <div className="flex justify-end">
            <Button onClick={() => save.mutate(form)} disabled={save.isPending}>
              {save.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save changes
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Telegram Bot</CardTitle>
          <CardDescription>
            Send links and track downloads from a Telegram chat.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {telegramStatus?.configured ? (
            telegramStatus.connected ? (
              <div className="flex items-center gap-2 text-sm text-emerald-500">
                <CheckCircle2 className="h-4 w-4" />
                Connected as @{telegramStatus.bot_username ?? "unknown"}
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-amber-500">
                <AlertTriangle className="h-4 w-4" />
                Token configured, but the bot isn't polling yet.
              </div>
            )
          ) : (
            <div className="flex items-center gap-2 text-sm text-amber-500">
              <AlertTriangle className="h-4 w-4" />
              Not configured — set YTDLP_TELEGRAM_BOT_TOKEN on the backend.
            </div>
          )}

          <Field label="Enabled" hint="Turn the bot's polling loop on or off.">
            <Switch
              checked={form.telegram_enabled}
              onCheckedChange={(v) => update("telegram_enabled", v)}
            />
          </Field>

          <Field
            label="Allowed chat IDs"
            hint="Comma-separated numeric chat IDs. Empty = the bot ignores everyone. Message the bot once to see your chat ID in its reply."
          >
            <Textarea
              value={form.telegram_allowed_chat_ids}
              onChange={(e) => update("telegram_allowed_chat_ids", e.target.value)}
              placeholder="12345678, 98765432"
              className="font-mono text-sm"
              rows={2}
            />
          </Field>

          <div className="flex justify-end">
            <Button onClick={() => save.mutate(form)} disabled={save.isPending}>
              {save.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              Save changes
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
