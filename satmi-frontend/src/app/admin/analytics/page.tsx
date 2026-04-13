"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getAdminIntentTrends,
  getAdminSearchTermTrends,
  getAdminTopSearchTerms,
  getAdminWeeklyInsights,
  IntentTrendPoint,
  SearchTermCount,
  SearchTermTrendPoint,
  WeeklyInsightCard,
} from "@/lib/satmiApi";

type LoadingState = "idle" | "loading" | "ready" | "error";

const DAY_FILTERS = [7, 14, 30, 60];

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

export default function AdminAnalyticsPage() {
  const [days, setDays] = useState(30);
  const [limitTerms, setLimitTerms] = useState(8);
  const [state, setState] = useState<LoadingState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [topTerms, setTopTerms] = useState<SearchTermCount[]>([]);
  const [termTrends, setTermTrends] = useState<SearchTermTrendPoint[]>([]);
  const [intentTrends, setIntentTrends] = useState<IntentTrendPoint[]>([]);
  const [weeklyInsights, setWeeklyInsights] = useState<WeeklyInsightCard[]>([]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      setState("loading");
      setError(null);
      try {
        const [top, terms, intents, insights] = await Promise.all([
          getAdminTopSearchTerms({ days, limit: 20 }),
          getAdminSearchTermTrends({ days, limitTerms }),
          getAdminIntentTrends({ days }),
          getAdminWeeklyInsights(),
        ]);
        if (!mounted) return;
        setTopTerms(top);
        setTermTrends(terms);
        setIntentTrends(intents);
        setWeeklyInsights(insights);
        setState("ready");
      } catch (loadError) {
        if (!mounted) return;
        const message = loadError instanceof Error ? loadError.message : "Unable to load analytics";
        setError(message);
        setState("error");
      }
    }

    load();
    return () => {
      mounted = false;
    };
  }, [days, limitTerms]);

  const maxTopCount = useMemo(() => {
    return topTerms.reduce((max, row) => (row.query_count > max ? row.query_count : max), 1);
  }, [topTerms]);

  const intentSummary = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of intentTrends) {
      map.set(row.intent, (map.get(row.intent) || 0) + row.query_count);
    }
    return Array.from(map.entries())
      .map(([intent, queryCount]) => ({ intent, queryCount }))
      .sort((a, b) => b.queryCount - a.queryCount);
  }, [intentTrends]);

  return (
    <main className="min-h-screen bg-[#F9F6F2] px-4 py-6 text-[#1F2937] md:px-8">
      <section className="mx-auto max-w-6xl space-y-6">
        <header className="rounded-2xl border border-[#D7C5B5] bg-[#FFFFFF] p-5">
          <p className="text-xs uppercase tracking-[0.2em] text-[#7A1E1E]">SATMI Admin</p>
          <h1 className="mt-1 text-2xl font-semibold [font-family:var(--font-serif-display)]">Search Analytics Dashboard</h1>
          <p className="mt-2 text-sm text-[#475569]">
            Read-only analytics for user search behavior and intent trends. This page relies on backend admin analytics APIs.
          </p>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <label className="text-sm font-medium">Window</label>
            <select
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
              className="rounded-lg border border-[#D7C5B5] bg-white px-3 py-2 text-sm"
            >
              {DAY_FILTERS.map((value) => (
                <option key={value} value={value}>
                  Last {value} days
                </option>
              ))}
            </select>

            <label className="ml-2 text-sm font-medium">Tracked terms</label>
            <input
              type="number"
              min={3}
              max={20}
              value={limitTerms}
              onChange={(event) => setLimitTerms(Number(event.target.value) || 8)}
              className="w-24 rounded-lg border border-[#D7C5B5] bg-white px-3 py-2 text-sm"
            />
          </div>
        </header>

        {state === "loading" && (
          <div className="rounded-xl border border-[#D7C5B5] bg-white px-4 py-3 text-sm">Loading analytics...</div>
        )}

        {state === "error" && (
          <div className="rounded-xl border border-[#EF4444] bg-[#FEF2F2] px-4 py-3 text-sm text-[#B91C1C]">
            {error || "Failed to load analytics. Ensure ANALYTICS_ADMIN_PANEL_ENABLED=true and support headers are allowed."}
          </div>
        )}

        {state === "ready" && (
          <>
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {weeklyInsights.map((card) => (
                <article key={card.key} className="rounded-2xl border border-[#D7C5B5] bg-white p-4">
                  <p className="text-xs uppercase tracking-wide text-[#7A1E1E]">{card.title}</p>
                  <p className="mt-2 text-xl font-semibold text-[#111827]">{card.value}</p>
                  <p className="mt-1 text-xs text-[#64748B]">{card.summary}</p>
                  {typeof card.delta_percent === "number" && (
                    <p
                      className={`mt-2 text-xs font-medium ${
                        card.direction === "up"
                          ? "text-emerald-700"
                          : card.direction === "down"
                            ? "text-rose-700"
                            : "text-slate-600"
                      }`}
                    >
                      {card.delta_percent > 0 ? "+" : ""}
                      {card.delta_percent}% vs previous week
                    </p>
                  )}
                </article>
              ))}
            </section>

            <section className="rounded-2xl border border-[#D7C5B5] bg-white p-5">
              <h2 className="text-lg font-semibold">Top Search Terms</h2>
              <div className="mt-4 space-y-3">
                {topTerms.length === 0 && <p className="text-sm text-[#64748B]">No search term data yet.</p>}
                {topTerms.map((row) => (
                  <div key={row.normalized_term} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium text-[#111827]">{row.normalized_term}</span>
                      <span className="text-[#475569]">{row.query_count}</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-[#F1F5F9]">
                      <div
                        className="h-full rounded-full bg-[#7A1E1E]"
                        style={{ width: `${Math.max((row.query_count / maxTopCount) * 100, 3)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="grid gap-4 md:grid-cols-2">
              <div className="rounded-2xl border border-[#D7C5B5] bg-white p-5">
                <h2 className="text-lg font-semibold">Intent Mix</h2>
                <div className="mt-4 space-y-2">
                  {intentSummary.length === 0 && <p className="text-sm text-[#64748B]">No intent trend data yet.</p>}
                  {intentSummary.map((row) => (
                    <div key={row.intent} className="flex items-center justify-between rounded-lg bg-[#F8FAFC] px-3 py-2 text-sm">
                      <span className="font-medium capitalize">{row.intent.replace(/_/g, " ")}</span>
                      <span>{row.queryCount}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-[#D7C5B5] bg-white p-5">
                <h2 className="text-lg font-semibold">Daily Trend Snapshot</h2>
                <div className="mt-3 max-h-64 overflow-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-[#E2E8F0] text-[#475569]">
                        <th className="py-2">Date</th>
                        <th className="py-2">Term</th>
                        <th className="py-2">Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {termTrends.slice(0, 40).map((row, index) => (
                        <tr key={`${row.stat_date}-${row.normalized_term}-${index}`} className="border-b border-[#F1F5F9]">
                          <td className="py-2">{formatDate(row.stat_date)}</td>
                          <td className="py-2">{row.normalized_term}</td>
                          <td className="py-2">{row.query_count}</td>
                        </tr>
                      ))}
                      {termTrends.length === 0 && (
                        <tr>
                          <td className="py-2 text-[#64748B]" colSpan={3}>
                            No trend rows available.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </>
        )}
      </section>
    </main>
  );
}
