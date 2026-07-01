import { formatSpeed } from "@/lib/format";

/** Tiny SVG sparkline of recent download speed samples. */
export function SpeedGraph({ data, height = 32 }: { data: number[]; height?: number }) {
  const width = 100; // viewBox units; scales to container width
  const max = Math.max(...data, 1);
  const step = data.length > 1 ? width / (data.length - 1) : width;
  const points = data
    .map((v, i) => `${(i * step).toFixed(2)},${(height - (v / max) * height).toFixed(2)}`)
    .join(" ");
  const area = `0,${height} ${points} ${((data.length - 1) * step).toFixed(2)},${height}`;

  return (
    <div className="flex items-center gap-2">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-8 w-full"
        role="img"
        aria-label="Download speed over time"
      >
        <polygon points={area} className="fill-primary/10" />
        <polyline
          points={points}
          fill="none"
          className="stroke-primary"
          strokeWidth={1.5}
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
      <span className="shrink-0 tabular-nums text-xs text-muted-foreground">
        {formatSpeed(data[data.length - 1])}
      </span>
    </div>
  );
}
