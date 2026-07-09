import { Download, History, ListOrdered, Music, Search, Settings } from "lucide-react";
import { Logo } from "@/components/Logo";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";

export type View = "home" | "queue" | "search" | "lyrics" | "history" | "settings";

const NAV: { key: View; label: string; icon: typeof Download }[] = [
  { key: "home", label: "Download", icon: Download },
  { key: "queue", label: "Queue", icon: ListOrdered },
  { key: "search", label: "Search", icon: Search },
  { key: "lyrics", label: "Lyrics", icon: Music },
  { key: "history", label: "History", icon: History },
  { key: "settings", label: "Settings", icon: Settings },
];

export function Header({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 max-w-5xl items-center justify-between gap-4 px-4">
        <Logo />
        <nav className="flex items-center gap-1">
          {NAV.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => onChange(key)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                view === key
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
          <div className="ml-1">
            <ThemeToggle />
          </div>
        </nav>
      </div>
    </header>
  );
}
