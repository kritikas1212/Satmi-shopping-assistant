"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";

import ChatBubble from "@/components/ChatBubble";
import {
  ChatResponse,
  ProductRecommendation,
  getTask,
} from "@/lib/satmiApi";

type UiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  recommended_products?: ProductRecommendation[];
};

type ChatApiResponse = ChatResponse & { reply?: string };

const STORAGE_KEYS = {
  conversationId: "satmi_chat_conversation_id",
  messages: "satmi_chat_messages",
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
const API_KEY = process.env.NEXT_PUBLIC_SATMI_API_KEY;

const FAQ_CHIPS = [
  { label: "🔥 Best Sellers", query: "Show me your best selling products" },
  { label: "🛡️ 2X Money Back", query: "What is the 2X Money Back Assurance?" },
  { label: "📦 Shipping & Returns", query: "What is your shipping and return policy?" },
];

const WELCOME_TEXT = "Namaste! I am your SATMI Concierge. How can I assist you with our authentic spiritual wellness products today?";

function createWelcomeMessage(): UiMessage {
  return {
    id: uuidv4(),
    role: "assistant",
    content: WELCOME_TEXT,
    timestamp: new Date().toISOString(),
    recommended_products: [],
  };
}

function parseMessages(raw: string | null): UiMessage[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item) => item && item.role && item.content && item.id);
  } catch {
    return [];
  }
}

function formatTaskResult(result?: Record<string, unknown>): string {
  if (!result || Object.keys(result).length === 0) {
    return "Task completed successfully.";
  }

  return `Task completed.\n\n\`\`\`json\n${JSON.stringify(result, null, 2)}\n\`\`\``;
}

export default function SatmiChat() {
  const [hydrated, setHydrated] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<UiMessage[]>([createWelcomeMessage()]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isPollingTask, setIsPollingTask] = useState(false);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const userId = useMemo(() => `web-${conversationId || "guest"}`, [conversationId]);

  useEffect(() => {
    const savedConversationId = localStorage.getItem(STORAGE_KEYS.conversationId);
    const savedMessages = parseMessages(localStorage.getItem(STORAGE_KEYS.messages));

    const nextConversationId = savedConversationId || uuidv4();
    const nextMessages = savedMessages.length > 0 ? savedMessages : [createWelcomeMessage()];

    setConversationId(nextConversationId);
    setMessages(nextMessages);

    localStorage.setItem(STORAGE_KEYS.conversationId, nextConversationId);
    localStorage.setItem(STORAGE_KEYS.messages, JSON.stringify(nextMessages));

    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated || !conversationId) return;
    localStorage.setItem(STORAGE_KEYS.conversationId, conversationId);
  }, [conversationId, hydrated]);

  useEffect(() => {
    if (!hydrated) return;
    localStorage.setItem(STORAGE_KEYS.messages, JSON.stringify(messages));
  }, [messages, hydrated]);

  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    container.scrollTop = container.scrollHeight;
  }, [messages, isPollingTask, isOpen]);

  const appendMessage = (role: UiMessage["role"], content: string, products?: ProductRecommendation[]) => {
    const nextProducts = (products || []).slice(0, 8);

    setMessages((prev) => [
      ...prev,
      {
        id: uuidv4(),
        role,
        content,
        timestamp: new Date().toISOString(),
        recommended_products: nextProducts,
      },
    ]);
  };

  const pollTaskUntilComplete = async (taskId: string) => {
    setIsPollingTask(true);
    setActiveTaskId(taskId);
    appendMessage("assistant", "Processing your request...");

    return new Promise<void>((resolve) => {
      const intervalId = window.setInterval(async () => {
        try {
          const task = await getTask(taskId, undefined);

          if (task.status === "completed") {
            window.clearInterval(intervalId);
            setIsPollingTask(false);
            setActiveTaskId(null);
            appendMessage("assistant", formatTaskResult(task.result));
            resolve();
          }

          if (task.status === "failed") {
            window.clearInterval(intervalId);
            setIsPollingTask(false);
            setActiveTaskId(null);
            appendMessage("assistant", `Task failed: ${task.error || "Unknown task error"}`);
            resolve();
          }
        } catch (error) {
          window.clearInterval(intervalId);
          setIsPollingTask(false);
          setActiveTaskId(null);
          const message = error instanceof Error ? error.message : "Task polling failed";
          appendMessage("assistant", `Task polling error: ${message}`);
          resolve();
        }
      }, 2000);
    });
  };

  const sendChatMessage = async (
    message: string,
    options?: {
      appendUserMessage?: boolean;
      messageOverride?: string;
    }
  ) => {
    const appendUserMessage = options?.appendUserMessage ?? true;

    if (appendUserMessage) {
      appendMessage("user", message);
    }

    const headers: HeadersInit = {
      "Content-Type": "application/json",
    };
    if (API_KEY) {
      headers["X-API-Key"] = API_KEY;
    }

    const apiResponse = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        user_id: userId,
        conversation_id: conversationId,
        message: options?.messageOverride ?? message,
      }),
    });

    if (!apiResponse.ok) {
      throw new Error(`POST /chat failed (${apiResponse.status})`);
    }

    const response = (await apiResponse.json()) as ChatApiResponse;

    appendMessage(
      "assistant",
      response.response_text || response.reply || "I am here to help.",
      response.recommended_products || []
    );

    const asyncTaskId = response.metadata?.async_task_id;
    if (typeof asyncTaskId === "string" && asyncTaskId.length > 0) {
      await pollTaskUntilComplete(asyncTaskId);
    }

    return response;
  };

  const handleFaqClick = async (question: string) => {
    if (isSending || !conversationId) return;
    setErrorMessage(null);
    setIsSending(true);
    try {
      await sendChatMessage(question);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to process your message";
      setErrorMessage("Unable to reach SATMI right now. Please try again.");
      appendMessage("assistant", `I am unable to process that right now. ${message}`);
    } finally {
      setIsSending(false);
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (isSending || !conversationId) return;

    setErrorMessage(null);
    setIsSending(true);

    try {
      const trimmed = draft.trim();
      if (!trimmed) return;
      setDraft("");
      await sendChatMessage(trimmed);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unable to process your message";
      setErrorMessage("Unable to reach SATMI right now. Please try again.");
      appendMessage("assistant", `I am unable to process that right now. ${message}`);
    } finally {
      setIsSending(false);
    }
  };

  if (!hydrated) {
    return null;
  }

  return (
    <div className="satmi-widget-root">
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="satmi-widget-fab"
          aria-label="Open SATMI Chat"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5" aria-hidden="true">
            <path
              d="M8 9h8M8 13h5m7 8-3.2-2H7a4 4 0 0 1-4-4V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v14Z"
              stroke="currentColor"
              strokeWidth="1.7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}

      {isOpen && (
        <div className="satmi-widget-window bg-[#F9F6F2]">
          <header className="flex items-center justify-between border-b border-[#E6D8C9] bg-[#F9F6F2] px-5 py-4">
            <div>
              <img src="/logo.png" alt="SATMI Logo" className="h-6 w-auto mb-1" />
              <h2 className="text-xl font-semibold text-[#000000] [font-family:var(--font-serif-display)]">Luxury Spiritual Shopping</h2>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="rounded-lg border border-[#7A1E1E] px-2.5 py-1 text-xs font-medium text-[#7A1E1E] hover:bg-[#EFE7DE]"
            >
              Close
            </button>
          </header>

          <div ref={scrollRef} className="h-[calc(100%-148px)] space-y-4 overflow-y-auto bg-[#F9F6F2] px-4 py-4">
            {messages.map((message, index) => (
              <div key={message.id} className={`max-w-[92%] ${message.role === "user" ? "ml-auto" : ""}`}>
                <ChatBubble
                  role={message.role}
                  content={message.content}
                  recommendedProducts={message.recommended_products || []}
                />

                {messages.length === 1 && index === 0 && message.role === "assistant" && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {FAQ_CHIPS.map((chip) => (
                      <button
                        key={chip.label}
                        type="button"
                        onClick={() => handleFaqClick(chip.query)}
                        disabled={isSending}
                        className="rounded-full bg-[#7A1E1E] px-3 py-1.5 text-xs font-medium text-[#F9F6F2] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {chip.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {isSending && !isPollingTask && (
              <div className="max-w-[92%] mb-4">
                <div className="w-fit rounded-2xl px-4 py-3 shadow-sm bg-[#EFE7DE]">
                  <span className="flex gap-1.5 items-center h-4">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#7A1E1E] animate-bounce [animation-delay:-0.3s]"></span>
                    <span className="h-1.5 w-1.5 rounded-full bg-[#7A1E1E] animate-bounce [animation-delay:-0.15s]"></span>
                    <span className="h-1.5 w-1.5 rounded-full bg-[#7A1E1E] animate-bounce"></span>
                  </span>
                </div>
              </div>
            )}

            {isPollingTask && (
              <div className="inline-flex items-center gap-2 rounded-xl border border-[#D7C5B5] bg-[#EFE7DE] px-3 py-2 text-xs text-[#000000]">
                <span className="h-2 w-2 animate-pulse rounded-full bg-[#7A1E1E]" />
                Processing your request{activeTaskId ? ` (${activeTaskId})` : ""}...
              </div>
            )}
          </div>

          <form onSubmit={handleSubmit} className="border-t border-[#E6D8C9] bg-[#F9F6F2] px-4 py-3">
            {errorMessage && (
              <p className="mb-2 text-xs text-red-600">{errorMessage}</p>
            )}

            <div className="flex gap-2">
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="Ask about SATMI, products, shipping, or your order..."
                inputMode="text"
                className="flex-1 rounded-xl border border-[#D7C5B5] bg-[#FFFFFF] px-3 py-2 text-sm text-[#000000] outline-none ring-[#7A1E1E] transition focus:ring-2"
              />
              <button
                type="submit"
                disabled={isSending}
                className="rounded-xl bg-[#7A1E1E] px-4 py-2 text-sm font-semibold text-[#F9F6F2] transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSending ? "..." : "Send"}
              </button>
            </div>

            <p className="mt-2 text-[10px] text-[#000000]">
              conversation_id: {conversationId}
            </p>
          </form>
        </div>
      )}
    </div>
  );
}
