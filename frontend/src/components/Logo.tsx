import { cn } from "@/lib/utils";

/**
 * Brand mark: a downward "download" arrow whose head is a play-button triangle.
 * Violet→cyan gradient matching the app palette. Original mark for this project.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 48 48"
      className={cn("h-7 w-7", className)}
      role="img"
      aria-label="yt-dlp Dashboard logo"
    >
      <defs>
        <linearGradient id="brandGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#7C5CFF" />
          <stop offset="100%" stopColor="#22D3EE" />
        </linearGradient>
      </defs>
      <rect x="20.5" y="6" width="7" height="19" rx="3.5" fill="url(#brandGrad)" />
      <path d="M11 23 H37 L24 41 Z" fill="url(#brandGrad)" />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoMark />
      <div className="flex flex-col leading-none">
        <span className="text-base font-semibold tracking-tight">
          yt-dlp <span className="text-primary">Dashboard</span>
        </span>
      </div>
    </div>
  );
}
