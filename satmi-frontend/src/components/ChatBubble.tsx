"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ProductRecommendation } from "@/lib/satmiApi";
import { useState } from "react";

type ChatBubbleProps = {
  role: "user" | "assistant";
  content: string;
  recommendedProducts?: ProductRecommendation[];
  onDismissCards?: () => void;
};

const CARD_IMAGE_FALLBACK =
  "https://placehold.co/640x400/FDE68A/7C2D12?text=SATMI+Product";

function getShopifyCheckoutUrl(product: ProductRecommendation): string {
  const variantId = String(product.variant_id || "").trim();
  const handle = String(product.handle || "").trim();
  const productUrl = String(product.product_url || product.url || "").trim();

  // Priority 1: Variant-based GoKwik checkout URL
  if (variantId) {
    return `https://satmi.in/?pid=${variantId}&custom_source=true`;
  }

  // Priority 2: Product page fallback
  if (productUrl) {
    return productUrl;
  }

  if (handle) {
    return `https://satmi.in/products/${handle}`;
  }

  return "https://satmi.in";
}

export default function ChatBubble({ role, content, recommendedProducts = [], onDismissCards }: ChatBubbleProps) {
  const isUser = role === "user";
  const [isDismissed, setIsDismissed] = useState(false);

  return (
    <div className="space-y-3">
      <article
        className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
          isUser ? "bg-[#7A1E1E] text-[#F9F6F2]" : "bg-[#EFE7DE] text-[#000000]"
        }`}
      >
      <div className="markdown-body whitespace-pre-wrap wrap-break-word">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            table: ({ children }) => (
              <div className="my-2 overflow-x-auto">
                <table className="min-w-full">{children}</table>
              </div>
            ),
            th: ({ children }) => <th className="whitespace-nowrap">{children}</th>,
            td: ({ children }) => <td className="align-top">{children}</td>,
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
      </article>

      {!isUser && recommendedProducts.length > 0 && !isDismissed && (
        <div className="space-y-2">
          {onDismissCards && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => { setIsDismissed(true); if (onDismissCards) onDismissCards(); }}
                className="rounded-md border border-[#D7C5B5] bg-[#FFFFFF] px-2 py-1 text-[10px] font-medium text-[#7A1E1E] hover:bg-[#F9F6F2]"
              >
                Dismiss suggestions
              </button>
            </div>
          )}
          <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1">
          {recommendedProducts.slice(0, 8).map((product, idx) => {
            const viewLink = product.product_url || product.url || (product.handle ? `https://satmi.in/products/${product.handle}` : "https://satmi.in");
            return (
            <div
              key={`product-card-${idx}-${product.product_id || product.title}`}
              className="group min-w-45 max-w-45 snap-start overflow-hidden rounded-2xl border border-[#D7C5B5] bg-[#FFFFFF] shadow-sm"
            >
              <img
                src={product.image_url || CARD_IMAGE_FALLBACK}
                alt={product.title}
                className="h-28 w-full object-cover"
                onError={(event) => {
                  const imageElement = event.currentTarget;
                  if (imageElement.src !== CARD_IMAGE_FALLBACK) {
                    imageElement.src = CARD_IMAGE_FALLBACK;
                  }
                }}
              />
              <div className="space-y-1 p-3">
                <p className="line-clamp-2 text-xs font-medium text-[#000000]">{product.title}</p>
                <p className="text-sm font-bold text-[#000000]">{product.price}</p>
                <div className="mt-2 flex items-center justify-between gap-2">
                  <a
                    href={getShopifyCheckoutUrl(product)}
                    target="_top"
                    rel="noopener noreferrer"
                    className="rounded-lg bg-[#7A1E1E] px-2.5 py-1.5 text-[11px] font-semibold text-[#F9F6F2] transition hover:opacity-90"
                  >
                    Select & Buy
                  </a>
                  <button
                    type="button"
                    onClick={() => window.open(viewLink, "_blank")}
                    className="text-xs font-medium text-[#7A1E1E] underline transition hover:opacity-70"
                  >
                    View
                  </button>
                </div>
              </div>
            </div>
            );
          })}
          </div>
        </div>
      )}
    </div>
  );
}
