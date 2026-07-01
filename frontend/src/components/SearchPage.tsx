import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2, Search } from "lucide-react";
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
import { ApiError, api } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import type { SearchResultItem } from "@/lib/types";

const PROVIDERS = [
  { value: "ytsearch", label: "YouTube (relevance)" },
  { value: "ytsearchdate", label: "YouTube (newest)" },
  { value: "scsearch", label: "SoundCloud" },
];

export function SearchPage() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("ytsearch");
  const [limit, setLimit] = useState(10);

  const search = useMutation({
    mutationFn: () => api.search(query.trim(), provider, limit),
    onError: (e: ApiError) => toast.error("Search failed", { description: e.message }),
  });

  const create = useMutation({
    mutationFn: (url: string) => api.createDownload({ url }),
    onSuccess: () => {
      toast.success("Download queued");
      qc.invalidateQueries({ queryKey: ["downloads"] });
    },
    onError: (e: ApiError) => toast.error("Could not start download", { description: e.message }),
  });

  const onSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) search.mutate();
  };

  const results = search.data?.results ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-5 sm:p-6">
          <form onSubmit={onSearch} className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search for videos…"
              autoFocus
              className="h-11 text-base"
            />
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger className="h-11 sm:w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={String(limit)} onValueChange={(v) => setLimit(Number(v))}>
              <SelectTrigger className="h-11 sm:w-24">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[5, 10, 20, 30, 50].map((n) => (
                  <SelectItem key={n} value={String(n)}>
                    {n}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button type="submit" size="lg" disabled={search.isPending || !query.trim()}>
              {search.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Search
            </Button>
          </form>
        </CardContent>
      </Card>

      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((r) => (
            <ResultRow
              key={r.url ?? r.title}
              result={r}
              onDownload={() => r.url && create.mutate(r.url)}
              downloading={create.isPending}
            />
          ))}
        </div>
      )}

      {search.isSuccess && results.length === 0 && (
        <p className="text-sm text-muted-foreground">No results.</p>
      )}
    </div>
  );
}

function ResultRow({
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
        <Button size="sm" variant="outline" onClick={onDownload} disabled={downloading || !result.url}>
          <Download className="h-4 w-4" />
          Queue
        </Button>
      </CardContent>
    </Card>
  );
}
