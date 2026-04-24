"use client";

export const dynamic = "force-dynamic";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { MoreVertical, User } from "lucide-react";
import {
  DashboardChatMessage,
  DashboardExportRow,
  DashboardSnapshotResponse,
  getAdminChatTranscript,
  getAdminDashboardExport,
  getAdminDashboardSnapshot,
  addConversationComment,
  deleteConversation,
} from "@/lib/satmiApi";
import { CategoryManager } from "./components/CategoryManager";
import { onAuthStateChanged, signOut } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useRouter } from "next/navigation";

const CategoryPieChart = dynamic(() => import("./components/CategoryPieChart"), {
  ssr: false,
  loading: () => <div className="text-sm text-[#475569]">Loading chart...</div>,
});

const UserActivityChart = dynamic(() => import("./components/UserActivityChart"), {
  ssr: false,
  loading: () => <div className="text-sm text-[#475569]">Loading graph...</div>,
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

const parseIntentLabel = (label: string | null | undefined) => {
  if (!label) return "";
  try {
    if (label.trim().startsWith('{')) {
      const parsed = JSON.parse(label);
      return parsed.intent || parsed.dynamic_intent_label || parsed.step_2_dynamic_intent_label || label;
    }
  } catch (e) {
    return label;
  }
  return label;
};

const generateSparklinePoints = (intentName: string, chats: any[]) => {
  if (!chats || chats.length === 0) return "0,16 60,16";
  const counts = new Array(7).fill(0);
  const now = new Date();
  now.setHours(0,0,0,0);
  
  chats.forEach(chat => {
    if (chat.dominant_intent === intentName) {
      const chatDate = new Date(chat.started_at);
      chatDate.setHours(0,0,0,0);
      const diffDays = Math.floor((now.getTime() - chatDate.getTime()) / (1000 * 3600 * 24));
      if (diffDays >= 0 && diffDays < 7) {
        counts[6 - diffDays]++;
      }
    }
  });
  
  const max = Math.max(...counts, 1);
  const width = 60;
  const height = 16;
  const dx = width / 6;
  
  return counts.map((c, i) => `${i * dx},${height - (c / max) * height}`).join(" ");
};

export default function DashboardPage() {
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<DashboardSnapshotResponse | null>(null);
  
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);

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

  const [tableWidth, setTableWidth] = useState(70);
  const [isDragging, setIsDragging] = useState(false);
  const [openKebabMenuId, setOpenKebabMenuId] = useState<string | null>(null);
  const [intentSortOrder, setIntentSortOrder] = useState<"count_desc" | "count_asc" | "alpha_asc" | "alpha_desc">("count_desc");
  const [intentTimeFilter, setIntentTimeFilter] = useState("all_time");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [isAutoRefreshEnabled, setIsAutoRefreshEnabled] = useState(false);
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);

  const [isOverrideFormOpen, setIsOverrideFormOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [adminComment, setAdminComment] = useState("");
  const [isSubmittingComment, setIsSubmittingComment] = useState(false);
  const [overrideIntentValue, setOverrideIntentValue] = useState("");
  const [overrideCategoryValue, setOverrideCategoryValue] = useState("");
  const [dynamicCategories, setDynamicCategories] = useState<string[]>([]);
  const [isSubmittingOverride, setIsSubmittingOverride] = useState(false);
  const [isCategoryManagerOpen, setIsCategoryManagerOpen] = useState(false);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (user) {
        setIsAuthenticated(true);
      } else {
        router.push("/admin/login");
      }
    });
    return () => unsubscribe();
  }, [router]);

  useEffect(() => {
    fetch("http://localhost:8000/admin/categories")
      .then(r => r.json())
      .then(data => setDynamicCategories(data))
      .catch(console.error);
  }, []);

  const safeResolutionRate = Number.isFinite(data?.analytics?.resolution_rate)
    ? Number(data?.analytics?.resolution_rate)
    : 0;

  useEffect(() => {
    if (!isAuthenticated) return;
    let interval: NodeJS.Timeout | null = null;
    
    async function load(isBackground = false) {
      if (!isBackground) setLoadState("loading");
      if (!isBackground) setError(null);
      try {
        const res = await getAdminDashboardSnapshot({ 
          limit: CHAT_LIMIT, 
          offset,
          startDate: startDate || null,
          endDate: endDate || null
        });
        if (res.chats.length > 0) {
          setSelectedChatId(prev => prev || res.chats[0].conversation_id);
        }
        setData(res);
        if (!isBackground) setLoadState("ready");
      } catch (err: any) {
        console.error("Dashboard load failed:", err);
        if (!isBackground) {
          setError("Unable to load dashboard data right now. Please try again in a moment.");
          setLoadState("error");
        }
      }
    }
    
    load();

    if (isAutoRefreshEnabled) {
      interval = setInterval(() => {
        load(true);
      }, 30000);
    }
    
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [offset, activeSection, isAuthenticated, refreshKey]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const newWidth = (e.clientX / window.innerWidth) * 100;
      if (newWidth >= 30 && newWidth <= 70) {
        setTableWidth(newWidth);
      }
    };

    const handleMouseUp = () => {
      setIsDragging(false);
    };

    if (isDragging) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
    }

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isDragging]);

  useEffect(() => {
    const handleGlobalClick = () => setOpenKebabMenuId(null);
    if (openKebabMenuId) {
      document.addEventListener("click", handleGlobalClick);
    }
    return () => {
      document.removeEventListener("click", handleGlobalClick);
    };
  }, [openKebabMenuId]);

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

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#F8F5F2]">
        <div className="text-center">
          <div className="mx-auto flex h-16 w-16 animate-pulse items-center justify-center rounded-full bg-[#7A1E1E]">
            <span className="text-xl font-bold text-white">S</span>
          </div>
          <p className="mt-4 text-sm text-[#475569]">Authenticating...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen md:h-screen flex-col md:overflow-hidden bg-[#F3EBE3] text-[#2C3E50]">
      <header className="relative flex flex-shrink-0 items-center justify-between border-b border-[#5F1616] bg-[#7A1E1E] px-4 py-4 shadow-sm md:px-6">
        <div className="flex items-center">
          <button
            onClick={() => setMenuOpen((prev) => !prev)}
            aria-label="Open dashboard menu"
            className="rounded-lg px-2 py-2 text-white hover:bg-[#8A2424]"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M3 12h18M3 18h18" />
            </svg>
          </button>
        </div>
        
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center">
          <a href="https://satmi.in/" target="_blank" rel="noopener noreferrer">
            <img src="/logo.png" className="object-contain filter brightness-0 invert" alt="SATMI Logo" width={120} height={120} />
          </a>
        </div>

        <div className="flex items-center gap-4">
          <div className="hidden lg:flex items-center gap-2 text-white">
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="bg-[#5F1616] border border-[#D7C5B5] rounded px-2 py-1 text-xs" />
            <span className="text-xs">to</span>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="bg-[#5F1616] border border-[#D7C5B5] rounded px-2 py-1 text-xs" />
            {(startDate || endDate) && (
              <button 
                onClick={() => { setStartDate(""); setEndDate(""); }}
                className="ml-2 text-xs hover:text-gray-300 underline"
              >
                Clear Dates
              </button>
            )}
          </div>
          <div className="hidden lg:flex items-center gap-2">
            <label className="text-white text-xs font-semibold cursor-pointer flex items-center gap-1">
              <input type="checkbox" checked={isAutoRefreshEnabled} onChange={e => setIsAutoRefreshEnabled(e.target.checked)} className="accent-white" />
              Live Sync
            </label>
          </div>
          <div className="flex items-center relative">
          <button
            onClick={() => setIsAccountMenuOpen(!isAccountMenuOpen)}
            className="flex items-center justify-center rounded-full p-2 text-[#F8F5F2] hover:bg-[#8A2424] transition-colors focus:outline-none"
            aria-label="Account Menu"
          >
            <User size={20} />
          </button>
          {isAccountMenuOpen && (
            <div className="absolute right-0 top-full mt-2 w-48 rounded-md bg-white py-1 shadow-lg ring-1 ring-black ring-opacity-5 z-50">
              <button
                onClick={async () => {
                  try {
                    await signOut(auth);
                  } catch (err) {
                    console.error("Failed to log out", err);
                  }
                }}
                className="block w-full px-4 py-2 text-left text-sm text-red-600 font-medium hover:bg-red-50"
              >
                Log Out
              </button>
            </div>
          )}
        </div>
        </div>
      </header>

      <main className={`flex flex-1 flex-col p-6 md:p-8 min-h-0 bg-[#F8F5F2] ${activeSection === "conversation_explorer" ? "lg:overflow-hidden md:overflow-y-auto" : "md:overflow-y-auto"}`}>

      {menuOpen && (
        <div className="fixed inset-0 z-50 pointer-events-none">
          <aside className="absolute left-0 top-0 h-full w-72 border-r border-[#D7C5B5] bg-[#FFFDFC] p-5 shadow-xl pointer-events-auto flex flex-col justify-between">
            <div>
              <div className="flex justify-between items-center mb-6">
                <p className="text-xs font-semibold uppercase tracking-wide text-[#64748B]">Dashboard Menu</p>
                <button onClick={() => setMenuOpen(false)} className="text-[#64748B] hover:text-[#1A252F]">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
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
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    setIsCategoryManagerOpen(true);
                  }}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm font-semibold bg-[#F8F5F2] text-[#334155] mt-4`}
                >
                  Manage Categories
                </button>
                <button
                  onClick={handleExportCsv}
                  disabled={!data || data.chats.length === 0 || isExporting}
                  className="w-full rounded-lg px-3 py-2 text-left text-sm font-semibold bg-[#F8F5F2] text-[#7A1E1E] mt-4 disabled:opacity-50 border border-[#7A1E1E]"
                >
                  {isExporting ? "Exporting..." : "Export Page CSV"}
                </button>
              </div>
            </div>
          </aside>
        </div>
      )}

      {isCategoryManagerOpen && (
        <CategoryManager onClose={() => setIsCategoryManagerOpen(false)} />
      )}

      {loadState === "loading" && (
        <div className="rounded-xl border border-[#D7C5B5] bg-white p-8 text-center text-[#475569]">Loading dashboard data...</div>
      )}

      {loadState === "error" && (
        <div className="rounded-xl border border-[#EF4444] bg-[#FEF2F2] p-4 text-[#B91C1C]">{error || "Unable to load dashboard"}</div>
      )}

      {loadState === "ready" && data && (
        <div className="flex flex-1 flex-col space-y-6 min-h-0">
          {error && <div className="rounded-lg border border-[#EF4444] bg-[#FEF2F2] p-3 text-sm text-[#B91C1C]">{error}</div>}

          {activeSection === "overview" ? (
            <>
              <section className="grid grid-cols-1 gap-4 md:grid-cols-4">
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
                <div className="rounded-xl border border-[#D7C5B5] bg-[#FAF7F4] p-5 shadow-sm">
                  <p className="text-xs font-semibold uppercase text-[#475569]">Recommendation Conversions</p>
                  <p className="mt-2 text-3xl font-bold text-[#B45309]">{(data.analytics as any).recommendation_conversions || 0}</p>
                </div>
              </section>

              <section className="rounded-xl border border-[#D7C5B5] bg-white p-6 shadow-sm">
                <h2 className="mb-4 text-lg font-bold text-[#1A252F]">Conversation Activity (Last 30 Days)</h2>
                <div className="h-64">
                  <UserActivityChart data={data.analytics.daily_activity || []} />
                </div>
              </section>

              <section className="grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_1fr]">
                <div className="rounded-xl border border-[#D7C5B5] bg-white p-6 shadow-sm">
                  <h2 className="mb-4 text-lg font-bold text-[#1A252F]">Intent Distribution (Top 8)</h2>
                  <div className="h-52">
                    <CategoryPieChart data={data.analytics.intent_breakdown.slice(0, 8).map(d => ({ ...d, category: d.intent }))} />
                  </div>
                </div>
                <div className="rounded-xl border border-[#D7C5B5] bg-white p-6 shadow-sm">
                  <h2 className="mb-4 text-lg font-bold text-[#1A252F]">Intent Classification</h2>
                  <div className="mb-4 flex flex-col sm:flex-row gap-2">
                    <div className="flex-1">
                      <label className="text-xs font-semibold uppercase text-[#475569] mb-1 block">
                        Sort Intents
                      </label>
                      <select
                        value={intentSortOrder}
                        onChange={(e) => setIntentSortOrder(e.target.value as any)}
                        className="w-full rounded-md border border-[#D7C5B5] bg-[#F8F5F2] px-3 py-2 text-sm focus:border-[#7A1E1E] focus:outline-none"
                      >
                        <option value="count_desc">Count (High to Low)</option>
                        <option value="count_asc">Count (Low to High)</option>
                        <option value="alpha_asc">Alphabetical (A-Z)</option>
                        <option value="alpha_desc">Alphabetical (Z-A)</option>
                      </select>
                    </div>
                    <div className="flex-1">
                      <label className="text-xs font-semibold uppercase text-[#475569] mb-1 block">
                        Time Filter
                      </label>
                      <select
                        value={intentTimeFilter}
                        onChange={(e) => setIntentTimeFilter(e.target.value)}
                        className="w-full rounded-md border border-[#D7C5B5] bg-[#F8F5F2] px-3 py-2 text-sm focus:border-[#7A1E1E] focus:outline-none"
                      >
                        <option value="all_time">All Time</option>
                        <option value="last_7_days">Last 7 Days</option>
                        <option value="last_30_days">Last 30 Days</option>
                      </select>
                    </div>
                  </div>
                  <div className="space-y-3 max-h-64 overflow-y-auto pr-2">
                    {[...data.analytics.intent_breakdown].sort((a, b) => {
                      switch (intentSortOrder) {
                        case "count_desc": return b.count - a.count;
                        case "count_asc": return a.count - b.count;
                        case "alpha_asc": return a.intent.localeCompare(b.intent);
                        case "alpha_desc": return b.intent.localeCompare(a.intent);
                        default: return b.count - a.count;
                      }
                    }).filter(slice => slice.intent !== "unknown").map((slice) => (
                      <div key={slice.intent}>
                        <div className="mb-1 flex items-center justify-between text-sm">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-[#1F2937] truncate" title={slice.intent}>{slice.intent}</span>
                          </div>
                          <span className="text-[#475569] shrink-0">{slice.percentage.toFixed(1)}% ({slice.count})</span>
                        </div>
                        <div className="h-3 rounded-full bg-[#E2D8D0] overflow-hidden">
                          <div className="h-full rounded-full bg-[#7A1E1E] transition-all duration-500" style={{ width: `${Math.max(slice.percentage, 1)}%` }} />
                        </div>
                      </div>
                    ))}
                    {/* removed instruction line */}
                  </div>
                </div>
              </section>
            </>
          ) : (
            <section className="flex flex-1 flex-col gap-6 lg:flex-row min-h-0">
              <div 
                className="flex flex-col rounded-xl border border-[#D7C5B5] bg-white p-5 shadow-sm lg:overflow-hidden min-h-0"
                style={typeof window !== "undefined" && window.innerWidth >= 1024 ? { width: `${tableWidth}%` } : {}}
              >
                <h2 className="mb-4 text-lg font-bold text-[#1A252F] shrink-0">Conversation Explorer (Table)</h2>

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

                <div className="mb-3 flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => setRefreshKey(prev => prev + 1)}
                    className="flex items-center gap-2 rounded-lg bg-[#7A1E1E] px-4 py-2 text-sm font-semibold text-white hover:bg-[#5F1616]"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16" />
                    </svg>
                    Refresh Data
                  </button>
                  <button
                    onClick={resetFilters}
                    className="rounded-lg border border-[#D7C5B5] px-4 py-2 text-sm font-semibold text-[#475569] hover:bg-[#F8F5F2]"
                  >
                    Clear Filters
                  </button>
                </div>

                <div className="flex-1 relative min-h-[400px] md:min-h-0">
                  <div className="h-full md:absolute md:inset-0 overflow-y-auto overflow-x-auto pb-32">
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
                          <td className="px-3 py-3 text-[#1F2937]">{parseIntentLabel(chat.dominant_category) === "unknown" ? "" : parseIntentLabel(chat.dominant_category)}</td>
                          <td className="px-3 py-3 text-[#1F2937]">{parseIntentLabel(chat.intent_raw_label) || parseIntentLabel(chat.dominant_intent) || ""}</td>
                          <td className="px-3 py-3 relative">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setOpenKebabMenuId(prev => prev === chat.conversation_id ? null : chat.conversation_id);
                              }}
                              className="rounded-md p-1 hover:bg-[#E2D8D0] text-[#475569]"
                            >
                              <MoreVertical size={16} />
                            </button>
                            {openKebabMenuId === chat.conversation_id && (
                              <div className="absolute right-10 top-10 z-[100] w-32 rounded-md border border-[#D7C5B5] bg-white shadow-xl overflow-hidden">
                                <button
                                  onClick={() => {
                                    setSelectedChatId(chat.conversation_id);
                                    setOpenKebabMenuId(null);
                                  }}
                                  className="w-full px-4 py-2 text-left text-sm text-[#1A252F] hover:bg-[#F8F5F2]"
                                >
                                  Open Chat
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelectedChatId(chat.conversation_id);
                                    setIsOverrideFormOpen(true);
                                    setOverrideIntentValue(chat.dominant_intent || "");
                                    setOverrideCategoryValue(chat.dominant_category || "");
                                    setOpenKebabMenuId(null);
                                  }}
                                  className="w-full px-4 py-2 text-left text-sm text-[#1A252F] hover:bg-[#F8F5F2]"
                                >
                                  Override Intent
                                </button>
                                <button
                                  onClick={async (e) => {
                                    e.stopPropagation();
                                    await fetch(`http://localhost:8000/admin/conversations/${chat.conversation_id}/reclassify`, { method: "POST" });
                                    setOpenKebabMenuId(null);
                                    alert("Reclassification backfill started.");
                                  }}
                                  className="w-full px-4 py-2 text-left text-sm text-[#1A252F] hover:bg-[#F8F5F2]"
                                >
                                  Reclassify Intent
                                </button>
                                <button
                                  onClick={async (e) => {
                                    e.stopPropagation();
                                    setOpenKebabMenuId(null);
                                    if (confirm("Are you sure you want to delete this conversation? This cannot be undone.")) {
                                      try {
                                        await deleteConversation({ conversationId: chat.conversation_id });
                                        setRefreshKey(prev => prev + 1);
                                      } catch (err) {
                                        alert("Failed to delete conversation.");
                                      }
                                    }
                                  }}
                                  className="w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50 border-t border-[#D7C5B5]"
                                >
                                  Delete Conversation
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                </div>

                <div className="mt-4 flex shrink-0 items-center justify-between border-t border-[#D7C5B5] pt-4">
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

              {/* Draggable Splitter */}
              <div
                className="hidden w-2 cursor-col-resize items-center justify-center rounded-full hover:bg-[#D7C5B5] lg:flex shrink-0"
                onMouseDown={() => setIsDragging(true)}
              >
                <div className="h-8 w-1 rounded-full bg-[#E2D8D0]"></div>
              </div>

              <div 
                className="flex flex-col rounded-xl border border-[#D7C5B5] bg-white p-6 shadow-sm lg:overflow-hidden min-h-0"
                style={typeof window !== "undefined" && window.innerWidth >= 1024 ? { width: `calc(${100 - tableWidth}% - 24px)` } : {}}
              >
                <div className="mb-4 flex shrink-0 items-center justify-between border-b border-[#D7C5B5] pb-4">
                  <div>
                    <h2 className="text-lg font-bold text-[#1A252F]">Chat Transcript Viewer</h2>
                    <p className="mt-1 text-xs font-mono text-[#64748B]">
                      {selectedChatId ? `Conversation: ${selectedChatId}` : "No conversation selected"}
                    </p>
                  </div>
                  {selectedChatId && transcriptData && (
                    <button
                      onClick={() => {
                        const csvContent = "Role,Time,Message\n" + transcriptData.map(msg => `"${msg.role}","${msg.created_at}","${msg.message.replace(/"/g, '""')}"`).join("\n");
                        const blob = new Blob([csvContent], { type: "text/csv" });
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `transcript_${selectedChatId}.csv`;
                        a.click();
                        window.URL.revokeObjectURL(url);
                      }}
                      className="rounded-md border border-[#D7C5B5] bg-[#F8F5F2] px-3 py-1.5 text-xs font-semibold text-[#1A252F] hover:bg-[#E2D8D0]"
                    >
                      Export CSV
                    </button>
                  )}
                </div>

                {isOverrideFormOpen && selectedChatId && (
                  <div className="mb-4 rounded-lg border border-[#D7C5B5] bg-[#F8F5F2] p-4 shadow-sm">
                    <h3 className="text-sm font-semibold text-[#1A252F] mb-3">Override Intent Classification</h3>
                    <div className="grid grid-cols-2 gap-4 mb-3">
                      <div>
                        <label className="block text-xs text-[#475569] mb-1">Intent Category</label>
                        <select
                          value={overrideCategoryValue}
                          onChange={(e) => setOverrideCategoryValue(e.target.value)}
                          className="w-full rounded-md border border-[#D7C5B5] px-3 py-1.5 text-sm outline-none focus:border-[#7A1E1E]"
                        >
                          <option value="">Select Category</option>
                          {dynamicCategories.map(cat => (
                            <option key={cat} value={cat}>{cat}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-[#475569] mb-1">Raw Intent Label</label>
                        <input
                          type="text"
                          value={overrideIntentValue}
                          onChange={(e) => setOverrideIntentValue(e.target.value)}
                          placeholder="e.g. track_order_status"
                          className="w-full rounded-md border border-[#D7C5B5] px-3 py-1.5 text-sm outline-none focus:border-[#7A1E1E]"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setIsOverrideFormOpen(false)}
                        className="rounded-md px-3 py-1.5 text-xs font-semibold text-[#475569] hover:bg-[#E2D8D0]"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={async () => {
                          setIsSubmittingOverride(true);
                          try {
                            await fetch(`http://localhost:8000/admin/conversations/${selectedChatId}/intent`, {
                              method: "POST",
                              headers: { "Content-Type": "application/json", "X-Role": "admin" },
                              body: JSON.stringify({ intent_label: overrideIntentValue, category: overrideCategoryValue })
                            });
                            setIsOverrideFormOpen(false);
                          } catch (e) {
                            console.error(e);
                          } finally {
                            setIsSubmittingOverride(false);
                          }
                        }}
                        disabled={isSubmittingOverride || !overrideIntentValue || !overrideCategoryValue}
                        className="rounded-md bg-[#7A1E1E] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#5F1616] disabled:opacity-50"
                      >
                        {isSubmittingOverride ? "Saving..." : "Save Override"}
                      </button>
                    </div>
                  </div>
                )}

                <div className="flex-1 relative min-h-[400px] md:min-h-0">
                  <div className="h-full md:absolute md:inset-0 overflow-y-auto pr-2 space-y-4">
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
                      const isAdminComment = msg.role === "system" && msg.event_metadata?.is_admin_comment;
                      
                      if (msg.role === "system" && !isAdminComment) return null;

                      return (
                        <div key={`${msg.created_at}-${index}`} className={`flex ${isUser ? "justify-end" : isAdminComment ? "justify-center" : "justify-start"}`}>
                          <div
                            className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                              isUser
                                ? "rounded-br-none bg-[#2C3E50] text-white"
                                : isAdminComment
                                ? "bg-[#FEF3C7] text-[#92400E] border border-[#FCD34D] rounded-2xl"
                                : "rounded-bl-none border border-[#E2D8D0] bg-[#F3EBE3] text-[#1A252F]"
                            }`}
                          >
                            <p className="whitespace-pre-wrap leading-relaxed">{msg.message}</p>
                            
                            {!isUser && !isAdminComment && msg.event_metadata?.tool_action === 'search_products' && (msg.event_metadata?.tool_result as any)?.results?.length > 0 && (
                              <div className="mt-4 flex flex-col gap-2 border-t border-[#D7C5B5] pt-3">
                                <p className="text-xs font-semibold text-[#1A252F]">Recommended Products:</p>
                                {(msg.event_metadata.tool_result as any).results.map((product: any, idx: number) => (
                                  <div key={idx} className="flex items-center gap-3 bg-white p-2 rounded-md shadow-sm border border-[#E2D8D0]">
                                    <img src={product.image_url} alt={product.title} className="w-10 h-10 object-cover rounded" />
                                    <div>
                                      <p className="text-xs font-medium text-[#1A252F] line-clamp-1">{product.title}</p>
                                      <p className="text-[10px] text-[#475569]">{product.currency} {product.price}</p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}

                            <div className={`mt-2 flex items-center justify-between text-[10px] ${isUser ? "text-gray-300" : isAdminComment ? "text-[#B45309]" : "text-[#64748B]"}`}>
                              <span>{isAdminComment ? `Admin Note • ${new Date(msg.created_at).toLocaleTimeString()}` : new Date(msg.created_at).toLocaleTimeString()}</span>
                              {!isUser && !isAdminComment && msg.intent && msg.intent !== "unknown" && (
                                <span className="rounded bg-black/5 px-1.5 py-0.5 opacity-80">{parseIntentLabel(msg.intent)}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-sm text-[#475569]">No messages available.</div>
                  )}
                  </div>
                </div>

                {selectedChatId && (
                  <div className="mt-4 flex shrink-0 items-center gap-2 border-t border-[#D7C5B5] pt-4">
                    <input
                      type="text"
                      value={adminComment}
                      onChange={(e) => setAdminComment(e.target.value)}
                      placeholder="Add an admin note..."
                      className="flex-1 rounded-lg border border-[#D7C5B5] bg-[#FFFDFC] px-3 py-2 text-sm focus:border-[#7A1E1E] focus:outline-none"
                      onKeyDown={async (e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          if (!adminComment.trim() || isSubmittingComment || !selectedChatId) return;
                          setIsSubmittingComment(true);
                          try {
                            await addConversationComment({ conversationId: selectedChatId, message: adminComment });
                            setAdminComment("");
                            // Trigger transcript reload
                            const res = await getAdminChatTranscript(selectedChatId);
                            setTranscriptData(res.transcript);
                          } catch (err) {
                            alert("Failed to add comment.");
                          } finally {
                            setIsSubmittingComment(false);
                          }
                        }
                      }}
                    />
                    <button
                      disabled={isSubmittingComment || !adminComment.trim() || !selectedChatId}
                      onClick={async () => {
                          if (!adminComment.trim() || isSubmittingComment || !selectedChatId) return;
                          setIsSubmittingComment(true);
                          try {
                            await addConversationComment({ conversationId: selectedChatId, message: adminComment });
                            setAdminComment("");
                            const res = await getAdminChatTranscript(selectedChatId);
                            setTranscriptData(res.transcript);
                          } catch (err) {
                            alert("Failed to add comment.");
                          } finally {
                            setIsSubmittingComment(false);
                          }
                      }}
                      className="rounded-lg bg-[#7A1E1E] px-4 py-2 text-sm font-semibold text-white hover:bg-[#5F1616] disabled:opacity-50"
                    >
                      {isSubmittingComment ? "Saving..." : "Add Note"}
                    </button>
                  </div>
                )}
              </div>
            </section>
          )}
        </div>
      )}
      </main>
    </div>
  );
}
