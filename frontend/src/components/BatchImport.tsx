import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileUp, ListPlus, Loader2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Section } from "@/components/OptionsPanel";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";

/** Paste or import a list of URLs and queue them all at once. */
export function BatchImport() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const batch = useMutation({
    mutationFn: (urls: string[]) => api.createBatch(urls),
    onSuccess: (res) => {
      toast.success(`Queued ${res.count} download${res.count === 1 ? "" : "s"}`);
      qc.invalidateQueries({ queryKey: ["downloads"] });
      setText("");
    },
    onError: (e: ApiError) => toast.error("Batch failed", { description: e.message }),
  });

  const urls = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    file.text().then((content) => setText((t) => (t ? `${t}\n${content}` : content)));
    e.target.value = "";
  };

  return (
    <Section title="Batch import" summary={urls.length ? `${urls.length} URL(s)` : null}>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={"One URL per line\n# lines starting with # are ignored"}
        className="min-h-28 font-mono text-sm"
      />
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          onClick={() => batch.mutate(urls)}
          disabled={batch.isPending || urls.length === 0}
        >
          {batch.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ListPlus className="h-4 w-4" />
          )}
          Queue {urls.length || ""}
        </Button>
        <Button type="button" variant="outline" onClick={() => fileRef.current?.click()}>
          <FileUp className="h-4 w-4" />
          Import .txt
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,text/plain"
          onChange={onFile}
          className="hidden"
        />
      </div>
    </Section>
  );
}
