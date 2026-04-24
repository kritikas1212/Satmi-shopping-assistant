"use client";

import React, { useState, useEffect } from "react";

export function CategoryManager({ onClose }: { onClose: () => void }) {
  const [categories, setCategories] = useState<string[]>([]);
  const [newCategory, setNewCategory] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("http://localhost:8000/admin/categories")
      .then(r => r.json())
      .then(data => {
        setCategories(data);
        setIsLoading(false);
      })
      .catch(err => {
        console.error(err);
        setError("Failed to load categories");
        setIsLoading(false);
      });
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await fetch("http://localhost:8000/admin/categories", {
        method: "PUT",
        headers: { "Content-Type": "application/json", "X-Role": "admin" },
        body: JSON.stringify(categories)
      });
      onClose();
    } catch (err) {
      console.error(err);
      setError("Failed to save categories");
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddCategory = () => {
    const trimmed = newCategory.trim();
    if (trimmed && !categories.includes(trimmed)) {
      setCategories([...categories, trimmed]);
      setNewCategory("");
    }
  };

  const handleRemoveCategory = (catToRemove: string) => {
    setCategories(categories.filter(cat => cat !== catToRemove));
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-bold text-[#1A252F]">Manage Dynamic Categories</h2>
        
        {isLoading ? (
          <p className="text-sm text-[#475569]">Loading...</p>
        ) : (
          <>
            <div className="mb-4 flex gap-2">
              <input
                type="text"
                value={newCategory}
                onChange={e => setNewCategory(e.target.value)}
                placeholder="New category name"
                className="flex-1 rounded-md border border-[#D7C5B5] px-3 py-2 text-sm outline-none focus:border-[#7A1E1E]"
                onKeyDown={e => e.key === "Enter" && handleAddCategory()}
              />
              <button
                onClick={handleAddCategory}
                className="rounded-md bg-[#2C3E50] px-4 py-2 text-sm font-semibold text-white hover:bg-[#1A252F]"
              >
                Add
              </button>
            </div>

            <div className="max-h-60 overflow-y-auto space-y-2 mb-6">
              {categories.map(cat => (
                <div key={cat} className="flex items-center justify-between rounded-md border border-[#E2D8D0] bg-[#F8F5F2] px-3 py-2 text-sm">
                  <span className="text-[#1A252F]">{cat}</span>
                  <button onClick={() => handleRemoveCategory(cat)} className="text-red-500 hover:text-red-700">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M18 6L6 18M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>

            {error && <p className="mb-4 text-xs text-red-600">{error}</p>}

            <div className="flex justify-end gap-3">
              <button
                onClick={onClose}
                className="rounded-md px-4 py-2 text-sm font-semibold text-[#475569] hover:bg-[#F8F5F2]"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="rounded-md bg-[#7A1E1E] px-4 py-2 text-sm font-semibold text-white hover:bg-[#5F1616] disabled:opacity-50"
              >
                {isSaving ? "Saving..." : "Save Categories"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
