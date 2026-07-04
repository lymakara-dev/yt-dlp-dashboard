import { useState } from "react";
import { BatchImport } from "@/components/BatchImport";
import { Header, type View } from "@/components/Header";
import { HistoryTable } from "@/components/HistoryTable";
import { QueuePage } from "@/components/QueuePage";
import { SearchPage } from "@/components/SearchPage";
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
            <BatchImport />
          </div>
        )}
        {view === "queue" && (
          <div className="space-y-4">
            <h1 className="text-xl font-semibold">Queue</h1>
            <QueuePage />
          </div>
        )}
        {view === "search" && (
          <div className="space-y-4">
            <h1 className="text-xl font-semibold">Search</h1>
            <SearchPage />
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
