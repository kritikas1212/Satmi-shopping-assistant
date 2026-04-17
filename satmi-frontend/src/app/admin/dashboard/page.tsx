"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import {
  DashboardChatMessage,
  DashboardExportRow,
  DashboardSnapshotResponse,
  getAdminChatTranscript,
  getAdminDashboardExport,
  getAdminDashboardSnapshot,
} from "@/lib/satmiApi";

const CategoryPieChart = dynamic(() => import("./components/CategoryPieChart"), {
  ssr: false,
  loading: () => <div className="text-sm text-[#475569]">Loading chart...</div>,
});

type LoadState = "idle" | "loading" | "ready" | "error";
type DashboardSection = "overview" | "conversation_explorer";
const CHAT_LIMIT = 10;

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-US", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function csvEscape(value: unknown): string {
  const stringValue = String(value ?? "");
  return `"${stringValue.replace(/"/g, '""')}"`;
}

function buildExportCsv(rows: DashboardExportRow[]): string {
  const header = [
    "conversation_id",
    "user_id_hash",
    "session_status",
    "dominant_category",
    "dominant_intent",
    "role",
    "intent",
    "message",
    "created_at",
  ].join(",");

  const lines = rows.map((row) =>
    [
      csvEscape(row.conversation_id),
      csvEscape(row.user_id_hash),
      csvEscape(row.session_status),
      csvEscape(row.dominant_category),
      csvEscape(row.dominant_intent),
      csvEscape(row.role),
      csvEscape(row.intent ?? ""),
      csvEscape(row.message),
      csvEscape(row.created_at),
    ].join(",")
  );

  return `${header}\n${lines.join("\n")}`;
}

export default function DashboardPage() {
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DashboardSnapshotResponse | null>(null);

  const [activeSection, setActiveSection] = useState<DashboardSection>("overview");
  const [menuOpen, setMenuOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "Resolved" | "Abandoned">("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [intentFilter, setIntentFilter] = useState("all");

  const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
  const [transcriptData, setTranscriptData] = useState<DashboardChatMessage[] | null>(null);
  const [isTranscriptLoading, setIsTranscriptLoading] = useState(false);
  const [transcriptError, setTranscriptError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const safeResolutionRate = Number.isFinite(data?.analytics?.resolution_rate)
    ? Number(data?.analytics?.resolution_rate)
    : 0;

  useEffect(() => {
    async function load() {
      setLoadState("loading");
      setError(null);
      try {
        const res = await getAdminDashboardSnapshot({ limit: CHAT_LIMIT, offset });
        if (res.chats.length > 0) {
          setSelectedChatId(res.chats[0].conversation_id);
        }
        setData(res);
        setLoadState("ready");
      } catch (err: any) {
        console.error("Dashboard load failed:", err);
        setError("Unable to load dashboard data right now. Please try again in a moment.");
        setLoadState("error");
      }
    }
    load();
  }, [offset]);

  useEffect(() => {
    if (!selectedChatId) {
      setTranscriptData(null);
      setTranscriptError(null);
      return;
    }
    const chatId = selectedChatId;

    async function loadTranscript() {
      setIsTranscriptLoading(true);
      setTranscriptData(null);
      setTranscriptError(null);
      try {
        const res = await getAdminChatTranscript(chatId);
        setTranscriptData(res.transcript);
      } catch (err: any) {
        console.error("Failed to load transcript:", err);
        setTranscriptError("Unable to load transcript right now. Please try again.");
      } finally {
        setIsTranscriptLoading(false);
      }
    }

    loadTranscript();
  }, [selectedChatId]);

  const filteredChats = useMemo(() => {
    if (!data) return [];

    const normalizedSearch = searchTerm.trim().toLowerCase();
    return data.chats.filter((chat) => {
      if (statusFilter !== "all" && chat.status !== statusFilter) return false;
      if (categoryFilter !== "all" && chat.dominant_category !== categoryFilter) return false;
      if (intentFilter !== "all" && chat.dominant_intent !== intentFilter) return false;

      if (!normalizedSearch) return true;

      const haystack = [
        chat.conversation_id,
        chat.user_id_hash,
        chat.dominant_category,
        chat.dominant_intent,
      ]
        .join(" ")
        .toLowerCase();

      return haystack.includes(normalizedSearch);
    });
  }, [data, searchTerm, statusFilter, categoryFilter, intentFilter]);

  const categoryOptions = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.chats.map((chat) => chat.dominant_category))).sort();
  }, [data]);

  const intentOptions = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.chats.map((chat) => chat.dominant_intent))).sort();
  }, [data]);

  useEffect(() => {
    if (!data || data.chats.length === 0) return;
    if (!selectedChatId) {
      setSelectedChatId(data.chats[0].conversation_id);
      return;
    }
    const isSelectedVisible = data.chats.some((chat) => chat.conversation_id === selectedChatId);
    if (!isSelectedVisible) {
      setSelectedChatId(data.chats[0].conversation_id);
    }
  }, [data, selectedChatId]);

  useEffect(() => {
    if (activeSection !== "conversation_explorer") return;
    if (filteredChats.length === 0) return;
    const isSelectedInFilter = filteredChats.some((chat) => chat.conversation_id === selectedChatId);
    if (!selectedChatId || !isSelectedInFilter) {
      setSelectedChatId(filteredChats[0].conversation_id);
    }
  }, [activeSection, filteredChats, selectedChatId]);

  const resetFilters = () => {
    setSearchTerm("");
    setStatusFilter("all");
    setCategoryFilter("all");
    setIntentFilter("all");
  };

  const handleSectionChange = (section: DashboardSection) => {
    setActiveSection(section);
    setMenuOpen(false);
    if (section === "conversation_explorer" && !selectedChatId && data?.chats.length) {
      setSelectedChatId(data.chats[0].conversation_id);
    }
  };

  const handleExportCsv = async () => {
    if (!data || data.chats.length === 0 || isExporting) return;

    setIsExporting(true);
    setError(null);
    try {
      // For page-specific export, or you can change to large limit for full export
      const rows = await getAdminDashboardExport({ limit: CHAT_LIMIT, offset });
      const csvContent = buildExportCsv(rows);
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `satmi_chat_export_${new Date().toISOString()}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err: any) {
      console.error("Dashboard export failed:", err);
      setError("Unable to export chat data right now. Please try again.");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F3EBE3] p-6 text-[#2C3E50] md:p-8">
      <header className="mb-8 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-[#1A252F]">SATMI Dashboard</h1>
          <p className="mt-2 text-sm text-[#475569]">
            {activeSection === "overview"
              ? "Analytics and intent quality at a glance."
              : "Conversation Explorer with live transcript workspace."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleExportCsv}
            disabled={!data || data.chats.length === 0 || isExporting}
            className="rounded-lg bg-[#7A1E1E] px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#5F1616] disabled:opacity-50"
          >
            {isExporting ? "Exporting..." : "Export Page CSV"}
          </button>
          <button
            onClick={() => setMenuOpen((prev) => !prev)}
            aria-label="Open dashboard menu"
            className="rounded-lg border border-[#D7C5B5] bg-white px-3 py-2 text-[#1A252F] shadow-sm hover:bg-[#F8F5F2]"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
        </div>
      </header>

      {menuOpen && (
        <div className="fixed inset-0 z-50">
          <button
            aria-label="Close dashboard menu"
            onClick={() => setMenuOpen(false)}
            className="absolute inset-0 bg-black/30"
          />
          <aside className="absolute right-0 top-0 h-full w-72 border-l border-[#D7C5B5] bg-[#FFFDFC] p-5 shadow-xl">
            <p className="mb-4 text-xs font-semibold uppercase tracking-wide text-[#64748B]">Dashboard Menu</p>
            <div className="space-y-2">
              <button
                onClick={() => handleSectionChange("overview")}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm font-semibold ${
                  activeSection === "overview" ? "bg-[#7A1E1E] text-white" : "bg-[#F8F5F2] text-[#334155]"
                }`}
              >
                Overview
              </button>
              <button
                onClick={() => handleSectionChange("conversation_explorer")}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm font-semibold ${
                  activeSection === "conversation_explorer"
                    ? "bg-[#7A1E1E] text-white"
                    : "bg-[#F8F5F2] text-[#334155]"
                }`}
              >
                Conversation Explorer
              </button>
            </div>
          </aside>
        </div>
      )}

      {loadState === "loading" && (
        <div className="rounded-xl border border-[#D7C5B5] bg-white p-8 text-center text-[#475569]">Loading dashboard data...</div>
      )}

      {loadState === "error" && (
        <div className="rounded-xl border border-[#EF4444] bg-[#FEF2F2] p-4 text-[#B91C1C]">{error || "Unable to load dashboard"}</div>
      )}

      {loadState === "ready" && data && (
        <div className="space-y-6">
          {error && <div className="rounded-lg border border-[#EF4444] bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]">{error}</div>}

          {activeSection === "overview" ? (
            <>
              <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div className="rounded-xl border border-[#D7C5B5] bg-white p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase text-[#475569]">Total Conversations</p>
                  <p className="mt-2 text-3xl font-bold text-[#1A252F]">{data.total_sessions}</p>
                </div>
                <div className="rounded-xl border border-[#D7C5B5] bg-white p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase text-[#475569]">Resolution Rate</p>
                  <p className="mt-2 text-3xl font-bold text-[#0F766E]">{safeResolutionRate.toFixed(1)}%</p>
                </div>
                <div className="rounded-xl border border-[#D7C5B5] bg-white p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase text-[#475569]">Filtered Conversations</p>
                  <p className="mt-2 text-3xl font-bold text-[#1A252F]">{filteredChats.length}</p>
                </div>
              </section>

              <section className="grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_1fr]">
                <div className="rounded-xl border border-[#D7C5B5] bg-white p-6 shadow-sm">
                  <h2 className="mb-4 text-lg font-bold text-[#1A252F]">Intent Distribution (All Time)</h2>
                  <div className="h-52">
                    <CategoryPieChart data={data.analytics.intent_breakdown} />
                  </div>
                </div>
                <div className="rounded-xl border border-[#D7C5B5] bg-white p-6 shadow-sm">
                  <h2 className="mb-4 text-lg font-bold text-[#1A252F]">Intent Classification</h2>
                  <div className="space-y-3">
                    {data.analytics.intent_breakdown.map((slice) => (
                      <div key={slice.intent}>
                        <div className="mb-1 flex items-center justify-between text-sm">
                          <span className="font-medium text-[#1F2937]">{slice.intent}</span>
                          <span className="text-[#475569]">{slice.percentage.toFixed(1)}% ({slice.count})</span>
                        </div>
                        <div className="h-2 rounded-full bg-[#E2D8D0]">
                          <div className="h-2 rounded-full bg-[#7A1E1E]" style={{ width: `${Math.max(slice.percentage, 2)}%` }} />
                        </div>
                      </div>
                    ))}
                    <p className="pt-2 text-xs text-[#64748B]">
                      Open the hamburger menu and choose Conversation Explorer to inspect chats and transcripts side by side.
                    </p>
                  </div>
                </div>
              </section>
            </>
          ) : (
            <section className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <div className="rounded-xl border border-[#D7C5B5] bg-white p-5 shadow-sm">
                <h2 className="mb-4 text-lg font-bold text-[#1A252F]">Conversation Explorer (Table)</h2>

                <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                  <input
                    value={searchTerm}
                    onChange={(event) => setSearchTerm(event.target.value)}
                    placeholder="Search conversation, user hash, intent..."
                    className="rounded-lg border border-[#D7C5B5] bg-[#FFFDFC] px-3 py-2 text-sm focus:border-[#7A1E1E] focus:outline-none"
                  />
                  <select
                    value={statusFilter}
                    onChange={(event) => setStatusFilter(event.target.value as "all" | "Resolved" | "Abandoned")}
                    className="rounded-lg border border-[#D7C5B5] bg-[#FFFDFC] px-3 py-2 text-sm"
                  >
                    <option value="all">All Statuses</option>
                    <option value="Resolved">Resolved</option>
                    <option value="Abandoned">Abandoned</option>
                  </select>
                  <select
                    value={categoryFilter}
                    onChange={(event) => setCategoryFilter(event.target.value)}
                    className="rounded-lg border border-[#D7C5B5] bg-[#FFFDFC] px-3 py-2 text-sm"
                  >
                    <option value="all">All Categories</option>
                    {categoryOptions.map((category) => (
                      <option key={category} value={category}>{category}</option>
                    ))}
                  </select>
                  <select
                    value={intentFilter}
                    onChange={(event) => setIntentFilter(event.target.value)}
                    className="rounded-lg border border-[#D7C5B5] bg-[#FFFDFC] px-3 py-2 text-sm"
                  >
                    <option value="all">All Intents</option>
                    {intentOptions.map((intent) => (
                      <option key={intent} value={intent}>{intent}</option>
                    ))}
                  </select>
                </div>

                <div className="mb-3">
                  <button
                    onClick={resetFilters}
                    className="rounded-lg border border-[#D7C5B5] px-3 py-2 text-sm font-semibold text-[#475569] hover:bg-[#F8F5F2]"
                  >
                    Clear Filters
                  </button>
                </div>

                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-[#E2D8D0] text-sm">
                    <thead>
                      <tr className="text-left text-xs uppercase text-[#64748B]">
                        <th className="px-3 py-2">Conversation</th>
                        <th className="px-3 py-2">Last Activity</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2">Category</th>
                        <th className="px-3 py-2">Intent</th>
                        <th className="px-3 py-2">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#F1E9E2]">
                      {filteredChats.map((chat) => (
                        <tr key={chat.conversation_id} className={selectedChatId === chat.conversation_id ? "bg-[#F4F1ED]" : "hover:bg-[#FAF7F4]"}>
                          <td className="px-3 py-3 font-mono text-xs text-[#334155]">{chat.conversation_id.slice(0, 18)}...</td>
                          <td className="px-3 py-3 text-[#475569]">{formatDateTime(chat.last_activity_at)}</td>
                          <td className="px-3 py-3">
                            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${chat.status === "Resolved" ? "bg-[#D1FAE5] text-[#0F766E]" : "bg-[#FEE2E2] text-[#B91C1C]"}`}>
                              {chat.status}
                            </span>
                          </td>
                          <td className="px-3 py-3 text-[#1F2937]">{chat.dominant_category}</td>
                          <td className="px-3 py-3 text-[#1F2937]">{chat.dominant_intent}</td>
                          <td className="px-3 py-3">
                            <button
                              onClick={() => setSelectedChatId(chat.conversation_id)}
                              className="rounded-md bg-[#2C3E50] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#1A252F]"
                            >
                              Open Chat
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="mt-4 flex items-center justify-between border-t border-[#D7C5B5] pt-4">
                  <button
                    disabled={offset === 0}
                    onClick={() => setOffset((prev) => Math.max(0, prev - CHAT_LIMIT))}
                    className="rounded-md border border-[#D7C5B5] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[#475569] hover:bg-[#F8F5F2] disabled:opacity-50"
                  >
                    Prev
                  </button>
                  <span className="text-xs font-medium text-[#475569]">
                    &lt; {Math.floor(offset / CHAT_LIMIT) + 1} / {Math.max(1, Math.ceil((data.total_sessions || 1) / CHAT_LIMIT))} &gt;
                  </span>
                  <button
                    disabled={offset + CHAT_LIMIT >= (data.total_sessions || data.chats.length)}
                    onClick={() => setOffset((prev) => prev + CHAT_LIMIT)}
                    className="rounded-md border border-[#D7C5B5] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-[#7A1E1E] hover:bg-[#F8F5F2] disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>

                {filteredChats.length === 0 && (
                  <div className="mt-6 rounded-lg border border-[#E2D8D0] bg-[#F8F5F2] p-6 text-center text-sm text-[#475569]">
                    No conversations match your current filters.
                  </div>
                )}
              </div>

              <div className="rounded-xl border border-[#D7C5B5] bg-white p-6 shadow-sm">
                <div className="mb-4 flex items-center justify-between border-b border-[#D7C5B5] pb-4">
                  <div>
                    <h2 className="text-lg font-bold text-[#1A252F]">Chat Transcript Viewer</h2>
                    <p className="mt-1 text-xs font-mono text-[#64748B]">
                      {selectedChatId ? `Conversation: ${selectedChatId}` : "No conversation selected"}
                    </p>
                  </div>
                </div>

                <div className="max-h-[70vh] space-y-4 overflow-y-auto pr-2">
                  {!selectedChatId ? (
                    <div className="rounded-lg border border-dashed border-[#D7C5B5] bg-[#FAF7F4] p-10 text-center text-sm text-[#64748B]">
                      Select a conversation to open its transcript.
                    </div>
                  ) : isTranscriptLoading ? (
                    <div className="text-sm text-[#475569]">Loading messages...</div>
                  ) : transcriptError ? (
                    <div className="rounded-lg border border-[#FCA5A5] bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]">{transcriptError}</div>
                  ) : transcriptData && transcriptData.length > 0 ? (
                    transcriptData.map((msg, index) => {
                      const isUser = msg.role === "user";
                      return (
                        <div key={`${msg.created_at}-${index}`} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
                          <div
                            className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                              isUser
                                ? "rounded-br-none bg-[#2C3E50] text-white"
                                : "rounded-bl-none border border-[#E2D8D0] bg-[#F3EBE3] text-[#1A252F]"
                            }`}
                          >
                            <p className="whitespace-pre-wrap leading-relaxed">{msg.message}</p>
                            <div className={`mt-2 flex items-center justify-between text-[10px] ${isUser ? "text-gray-300" : "text-[#64748B]"}`}>
                              <span>{formatDateTime(msg.created_at)}</span>
                              {msg.intent && <span className="ml-2 rounded-full bg-black/10 px-2 py-0.5">{msg.intent}</span>}
                            </div>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-sm text-[#475569]">No messages in this transcript.</div>
                  )}
                </div>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
