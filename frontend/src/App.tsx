import { useState } from "react";
import { ActiveDownloads } from "@/components/ActiveDownloads";
import { Header, type View } from "@/components/Header";
import { HistoryTable } from "@/components/HistoryTable";
import { SettingsPage } from "@/components/SettingsPage";
import { SubmitView } from "@/components/SubmitView";

export default function App() {
  const [view, setView] = useState<View>("home");

  return (
    <div className="min-h-screen">
      <Header view={view} onChange={setView} />
      <main className="container max-w-5xl space-y-8 px-4 py-8">
        {view === "home" && (
          <div className="space-y-8">
            <SubmitView />
            <ActiveDownloads />
          </div>
        )}
        {view === "history" && (
          <div className="space-y-4">
            <h1 className="text-xl font-semibold">History</h1>
            <HistoryTable />
          </div>
        )}
        {view === "settings" && (
          <div className="space-y-4">
            <h1 className="text-xl font-semibold">Settings</h1>
            <SettingsPage />
          </div>
        )}
      </main>
    </div>
  );
}
