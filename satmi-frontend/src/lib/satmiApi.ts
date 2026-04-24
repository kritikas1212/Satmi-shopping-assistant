export type ProductRecommendation = {
  product_id?: string | null;
  variant_id?: string | null;
  handle?: string | null;
  url?: string | null;
  title: string;
  price: string;
  image_url?: string | null;
  product_url?: string | null;
};

export type ChatMetadata = {
  action?: string;
  async_task_id?: string | null;
  async_task_status?: string | null;
  [key: string]: unknown;
};

export type ChatResponse = {
  conversation_id: string;
  status: "active" | "awaiting_human" | "resolved";
  response?: string;
  response_text?: string;
  auth_required?: boolean;
  recommended_products?: ProductRecommendation[];
  intent: string;
  confidence: number;
  handoff_id?: string | null;
  metadata?: ChatMetadata;
};

export type TaskResponse = {
  task_id: string;
  task_type: string;
  status: "queued" | "in_progress" | "completed" | "failed";
  conversation_id: string;
  user_id: string;
  result?: Record<string, unknown>;
  error?: string | null;
};

export type SearchTermCount = {
  normalized_term: string;
  query_count: number;
};

export type SearchTermTrendPoint = {
  stat_date: string;
  normalized_term: string;
  query_count: number;
};

export type IntentTrendPoint = {
  stat_date: string;
  intent: string;
  query_count: number;
};

export type WeeklyInsightCard = {
  key: string;
  title: string;
  value: string;
  delta_percent?: number | null;
  direction: "up" | "down" | "flat";
  summary: string;
};

export type AdminChatHistoryEvent = {
  conversation_id: string;
  user_id_hash: string;
  role: string;
  message: string;
  status: string;
  intent?: string | null;
  created_at: string;
};

export type ConversationEventResponse = {
  role: string;
  message: string;
  status: string;
  intent?: string | null;
  confidence?: number | null;
  action?: string | null;
  handoff_id?: string | null;
  metadata?: Record<string, unknown>;
  created_at: string;
};

export type DashboardChatMessage = {
  role: "user" | "assistant" | "system";
  message: string;
  created_at: string;
  intent?: string | null;
  event_metadata?: Record<string, unknown>;
};

export type DashboardChatSession = {
  conversation_id: string;
  user_id_hash: string;
  is_frustrated: boolean;
  status: "Resolved" | "Abandoned";
  dominant_category: "Order Tracking" | "Product Search" | "Returns" | "Policy & FAQ" | "General";
  dominant_intent: string;
  intent_confidence?: number | null;
  intent_model_name?: string | null;
  intent_model_version?: string | null;
  intent_source_version?: string | null;
  intent_needs_review?: boolean | null;
  intent_is_overridden?: boolean;
  intent_override_reason?: string | null;
  intent_raw_label?: string | null;
  intent_classifier_mode?: string | null;
  intent_classifier_error?: string | null;
  intent_classifier_total_tokens?: number | null;
  started_at: string;
  last_activity_at: string;
};

export type DashboardCategorySlice = {
  category: "Order Tracking" | "Product Search" | "Returns" | "Policy & FAQ" | "General";
  count: number;
  percentage: number;
};

export type DashboardIntentSlice = {
  intent: string;
  count: number;
  percentage: number;
};

export type DashboardIntentSubcategorySlice = {
  parent_intent: string;
  subcategory: string;
  count: number;
};

export type DashboardTopTrend = {
  term: string;
  count: number;
};

export type DashboardExportRow = {
  conversation_id: string;
  user_id_hash: string;
  session_status: string;
  dominant_category: string;
  dominant_intent: string;
  intent_confidence?: number | null;
  intent_model_version?: string | null;
  intent_raw_label?: string | null;
  intent_classifier_mode?: string | null;
  role: string;
  intent?: string | null;
  message: string;
  created_at: string;
};

export type ConversationIntentOverrideResponse = {
  conversation_id: string;
  saved?: boolean;
  cleared?: boolean;
  label?: Record<string, unknown> | null;
};

export type IntentClassifierBackfillResponse = {
  queued: number;
  limit: number;
  inactive_minutes: number;
};

export type ConversationIntentBackfillResponse = {
  conversation_id: string;
  status?: "queued" | "completed";
  queued?: boolean;
  task_id?: string | null;
  result?: Record<string, unknown>;
};

export type DeleteConversationResponse = {
  conversation_id: string;
  deleted: Record<string, number>;
};

export type DashboardDailyActivity = {
  date: string;
  sessions: number;
};

export type DashboardSnapshotResponse = {
  total_sessions: number;
  chats: DashboardChatSession[];
  analytics: {
    resolution_rate: number;
    recommendation_conversions: number;
    category_divide: DashboardCategorySlice[];
    intent_breakdown: DashboardIntentSlice[];
    intent_subcategory_breakdown?: DashboardIntentSubcategorySlice[];
    top_trending_terms: DashboardTopTrend[];
    daily_activity: DashboardDailyActivity[];
  };
};

const API_BASE_URL =
  (process.env.NEXT_PUBLIC_API_BASE_URL || (process.env.NODE_ENV !== "production" ? "http://127.0.0.1:8000" : "")).trim();
const REQUEST_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_API_TIMEOUT_MS || 60000);
const API_KEY = process.env.NEXT_PUBLIC_SATMI_API_KEY;

function normalizeBaseUrl(url: string): string {
  return url.replace(/\/$/, "");
}

function getApiBaseUrlCandidates(): string[] {
  const configured = API_BASE_URL ? normalizeBaseUrl(API_BASE_URL) : "";

  if (process.env.NODE_ENV === "production") {
    return configured ? [configured] : [];
  }

  const candidates = [configured, "http://127.0.0.1:8000", "http://localhost:8000"]
    .map(normalizeBaseUrl)
    .filter(Boolean);
  return [...new Set(candidates)];
}

function isRecoverableNetworkError(error: unknown): boolean {
  if (error instanceof TypeError) {
    return true;
  }
  if (typeof DOMException !== "undefined" && error instanceof DOMException) {
    return error.name === "AbortError";
  }
  return false;
}

async function fetchWithBaseFallback(path: string, init: RequestInit): Promise<Response> {
  const candidates = getApiBaseUrlCandidates();
  if (candidates.length === 0) {
    console.error("SATMI API base URL is not configured for this environment.");
    throw new Error("Service is temporarily unavailable. Please try again.");
  }

  let lastError: unknown;

  for (let index = 0; index < candidates.length; index += 1) {
    const baseUrl = candidates[index];
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      const response = await fetch(`${baseUrl}${path}`, {
        ...init,
        signal: controller.signal,
      });

      if (index > 0 && process.env.NODE_ENV !== "production") {
        console.warn(`Recovered API request via fallback base URL: ${baseUrl}`);
      }
      return response;
    } catch (error) {
      lastError = error;
      if (!isRecoverableNetworkError(error)) {
        throw error;
      }
      if (index === candidates.length - 1) {
        console.error("Unable to reach SATMI backend.", {
          attemptedBaseUrls: candidates,
          cause: error,
        });
        throw new Error("Service is temporarily unavailable. Please try again.");
      }
    } finally {
      clearTimeout(timeoutId);
    }
  }

  console.error("Unexpected API connectivity failure.", {
    attemptedBaseUrls: candidates,
    cause: lastError,
  });
  throw new Error("Service is temporarily unavailable. Please try again.");
}

function buildBaseHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }
  return headers;
}

function buildAdminHeaders(supportRole: "support_agent" | "admin" = "admin"): Record<string, string> {
  return {
    ...buildBaseHeaders(),
    "X-Role": supportRole,
  };
}

export async function postChat(params: {
  userId: string;
  conversationId: string;
  message: string;
}): Promise<ChatResponse> {
  const response = await fetchWithBaseFallback("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildBaseHeaders(),
    },
    body: JSON.stringify({
      user_id: params.userId,
      conversation_id: params.conversationId,
      message: params.message,
    }),
  });

  if (!response.ok) {
    throw new Error(`POST /chat failed (${response.status})`);
  }

  return response.json();
}

export async function getConversationEvents(params: {
  conversationId: string;
  limit?: number;
  supportRole?: "support_agent" | "admin";
}): Promise<ConversationEventResponse[]> {
  const search = new URLSearchParams({
    limit: String(params.limit ?? 100),
  });

  const response = await fetchWithBaseFallback(`/conversations/${params.conversationId}/events?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /conversations/${params.conversationId}/events failed (${response.status})`);
  }

  return response.json();
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  const response = await fetchWithBaseFallback(`/tasks/${taskId}`, {
    method: "GET",
    headers: {
      ...buildBaseHeaders(),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /tasks/${taskId} failed (${response.status})`);
  }

  return response.json();
}

export async function getAdminTopSearchTerms(params: {
  days: number;
  limit: number;
  supportRole?: "support_agent" | "admin";
}): Promise<SearchTermCount[]> {
  const search = new URLSearchParams({
    days: String(params.days),
    limit: String(params.limit),
  });
  const response = await fetchWithBaseFallback(`/admin/analytics/top-search-terms?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/analytics/top-search-terms failed (${response.status})`);
  }

  return response.json();
}

export async function getAdminSearchTermTrends(params: {
  days: number;
  limitTerms: number;
  supportRole?: "support_agent" | "admin";
}): Promise<SearchTermTrendPoint[]> {
  const search = new URLSearchParams({
    days: String(params.days),
    limit_terms: String(params.limitTerms),
  });
  const response = await fetchWithBaseFallback(`/admin/analytics/search-term-trends?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/analytics/search-term-trends failed (${response.status})`);
  }

  return response.json();
}

export async function getAdminIntentTrends(params: {
  days: number;
  supportRole?: "support_agent" | "admin";
}): Promise<IntentTrendPoint[]> {
  const search = new URLSearchParams({
    days: String(params.days),
  });
  const response = await fetchWithBaseFallback(`/admin/analytics/intent-trends?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/analytics/intent-trends failed (${response.status})`);
  }

  return response.json();
}

export async function getAdminWeeklyInsights(params?: {
  supportRole?: "support_agent" | "admin";
}): Promise<WeeklyInsightCard[]> {
  const response = await fetchWithBaseFallback("/admin/analytics/weekly-insights", {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params?.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/analytics/weekly-insights failed (${response.status})`);
  }

  return response.json();
}

export async function getAdminChatHistory(params: {
  days: number;
  limit?: number;
  offset?: number;
  userIdHash?: string;
  supportRole?: "support_agent" | "admin";
}): Promise<AdminChatHistoryEvent[]> {
  const search = new URLSearchParams({
    days: String(params.days),
    limit: String(params.limit ?? 120),
    offset: String(params.offset ?? 0),
  });
  if (params.userIdHash) {
    search.set("user_id_hash", params.userIdHash);
  }

  const response = await fetchWithBaseFallback(`/admin/analytics/chat-history?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/analytics/chat-history failed (${response.status})`);
  }

  return response.json();
}

export async function getAdminDashboardSnapshot(params?: {
  limit?: number;
  offset?: number;
  startDate?: string | null;
  endDate?: string | null;
  supportRole?: "support_agent" | "admin";
}): Promise<DashboardSnapshotResponse> {
  const search = new URLSearchParams({
    limit: String(params?.limit ?? 10),
    offset: String(params?.offset ?? 0),
  });
  if (params?.startDate) search.set("start_date", params.startDate);
  if (params?.endDate) search.set("end_date", params.endDate);

  const response = await fetchWithBaseFallback(`/admin/dashboard/snapshot?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params?.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/dashboard/snapshot failed (${response.status})`);
  }

  return response.json();
}

export interface ChatTranscriptResponse {
  conversation_id: string;
  transcript: DashboardChatMessage[];
}

export async function getAdminDashboardExport(params?: {
  limit?: number;
  offset?: number;
  supportRole?: "support_agent" | "admin";
}): Promise<DashboardExportRow[]> {
  const search = new URLSearchParams({
    limit: String(params?.limit ?? 10),
    offset: String(params?.offset ?? 0),
  });

  const response = await fetchWithBaseFallback(`/admin/dashboard/export?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params?.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/dashboard/export failed (${response.status})`);
  }

  return response.json();
}

export async function getAdminChatTranscript(conversationId: string, params?: {
  supportRole?: "support_agent" | "admin";
}): Promise<ChatTranscriptResponse> {
  const response = await fetchWithBaseFallback(`/admin/dashboard/chat/${conversationId}/transcript`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params?.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      throw new Error("Unauthorized to access admin dashboard. Please contact an admin.");
    }
    throw new Error(`Failed to fetch chat transcript (Status: ${response.status})`);
  }

  return response.json();
}

export async function setAdminConversationIntentOverride(params: {
  conversationId: string;
  intentLabel: string;
  overrideReason: string;
  overriddenBy?: string;
  supportRole?: "support_agent" | "admin";
}): Promise<ConversationIntentOverrideResponse> {
  const response = await fetchWithBaseFallback(`/admin/dashboard/chat/${params.conversationId}/intent-override`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
    body: JSON.stringify({
      intent_label: params.intentLabel,
      override_reason: params.overrideReason,
      overridden_by: params.overriddenBy,
    }),
  });

  if (!response.ok) {
    throw new Error(`POST /admin/dashboard/chat/${params.conversationId}/intent-override failed (${response.status})`);
  }

  return response.json();
}

export async function clearAdminConversationIntentOverride(params: {
  conversationId: string;
  supportRole?: "support_agent" | "admin";
}): Promise<ConversationIntentOverrideResponse> {
  const response = await fetchWithBaseFallback(`/admin/dashboard/chat/${params.conversationId}/intent-override`, {
    method: "DELETE",
    headers: {
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`DELETE /admin/dashboard/chat/${params.conversationId}/intent-override failed (${response.status})`);
  }

  return response.json();
}

export async function addConversationComment(params: {
  conversationId: string;
  message: string;
  supportRole?: "support_agent" | "admin";
}): Promise<{ conversation_id: string; status: string }> {
  const response = await fetchWithBaseFallback(`/admin/dashboard/chat/${params.conversationId}/comment`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
    body: JSON.stringify({ message: params.message }),
  });

  if (!response.ok) {
    throw new Error(`POST /admin/dashboard/chat/${params.conversationId}/comment failed (${response.status})`);
  }

  return response.json();
}

export async function deleteConversation(params: {
  conversationId: string;
  supportRole?: "support_agent" | "admin";
}): Promise<DeleteConversationResponse> {
  const response = await fetchWithBaseFallback(`/admin/dashboard/chat/${params.conversationId}`, {
    method: "DELETE",
    headers: {
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`DELETE /admin/dashboard/chat/${params.conversationId} failed (${response.status})`);
  }

  return response.json();
}

export async function triggerAdminIntentClassifierBackfill(params?: {
  limit?: number;
  inactiveMinutes?: number;
  supportRole?: "support_agent" | "admin";
}): Promise<IntentClassifierBackfillResponse> {
  const search = new URLSearchParams({
    limit: String(params?.limit ?? 200),
    inactive_minutes: String(params?.inactiveMinutes ?? 15),
  });

  const response = await fetchWithBaseFallback(`/admin/dashboard/intent-classifier/backfill?${search.toString()}`, {
    method: "POST",
    headers: {
      ...buildAdminHeaders(params?.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`POST /admin/dashboard/intent-classifier/backfill failed (${response.status})`);
  }

  return response.json();
}

export async function queueAdminConversationIntentBackfill(params: {
  conversationId: string;
  supportRole?: "support_agent" | "admin";
}): Promise<ConversationIntentBackfillResponse> {
  const response = await fetchWithBaseFallback(
    `/admin/dashboard/chat/${params.conversationId}/intent-classifier/backfill`,
    {
      method: "POST",
      headers: {
        ...buildAdminHeaders(params.supportRole ?? "admin"),
      },
    },
  );

  if (!response.ok) {
    throw new Error(
      `POST /admin/dashboard/chat/${params.conversationId}/intent-classifier/backfill failed (${response.status})`,
    );
  }

  return response.json();
}

export async function deleteAdminConversation(params: {
  conversationId: string;
  supportRole?: "support_agent" | "admin";
}): Promise<DeleteConversationResponse> {
  const response = await fetchWithBaseFallback(`/admin/dashboard/chat/${params.conversationId}`, {
    method: "DELETE",
    headers: {
      ...buildAdminHeaders(params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`DELETE /admin/dashboard/chat/${params.conversationId} failed (${response.status})`);
  }

  return response.json();
}
