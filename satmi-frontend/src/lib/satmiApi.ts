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

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
const API_KEY = process.env.NEXT_PUBLIC_SATMI_API_KEY;

function buildAuthHeaders(idToken?: string): Record<string, string> {
  const headers: Record<string, string> = {};
  if (idToken) {
    headers.Authorization = `Bearer ${idToken}`;
  }
  if (API_KEY) {
    headers["X-API-Key"] = API_KEY;
  }
  return headers;
}

function buildAdminHeaders(idToken?: string, supportRole: "support_agent" | "admin" = "admin"): Record<string, string> {
  return {
    ...buildAuthHeaders(idToken),
    "X-Role": supportRole,
  };
}

export async function postChat(params: {
  userId: string;
  conversationId: string;
  message: string;
  idToken?: string;
}): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(params.idToken),
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

export async function getTask(taskId: string, idToken?: string): Promise<TaskResponse> {
  const response = await fetch(`${API_BASE_URL}/tasks/${taskId}`, {
    method: "GET",
    headers: {
      ...buildAuthHeaders(idToken),
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
  idToken?: string;
  supportRole?: "support_agent" | "admin";
}): Promise<SearchTermCount[]> {
  const search = new URLSearchParams({
    days: String(params.days),
    limit: String(params.limit),
  });
  const response = await fetch(`${API_BASE_URL}/admin/analytics/top-search-terms?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params.idToken, params.supportRole ?? "admin"),
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
  idToken?: string;
  supportRole?: "support_agent" | "admin";
}): Promise<SearchTermTrendPoint[]> {
  const search = new URLSearchParams({
    days: String(params.days),
    limit_terms: String(params.limitTerms),
  });
  const response = await fetch(`${API_BASE_URL}/admin/analytics/search-term-trends?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params.idToken, params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/analytics/search-term-trends failed (${response.status})`);
  }

  return response.json();
}

export async function getAdminIntentTrends(params: {
  days: number;
  idToken?: string;
  supportRole?: "support_agent" | "admin";
}): Promise<IntentTrendPoint[]> {
  const search = new URLSearchParams({
    days: String(params.days),
  });
  const response = await fetch(`${API_BASE_URL}/admin/analytics/intent-trends?${search.toString()}`, {
    method: "GET",
    headers: {
      ...buildAdminHeaders(params.idToken, params.supportRole ?? "admin"),
    },
  });

  if (!response.ok) {
    throw new Error(`GET /admin/analytics/intent-trends failed (${response.status})`);
  }

  return response.json();
}
