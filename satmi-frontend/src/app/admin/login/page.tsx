"use client";

export const dynamic = "force-dynamic";

import { useState } from "react";
import { signInWithEmailAndPassword } from "firebase/auth";
import { auth } from "@/lib/firebase";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    try {
      await signInWithEmailAndPassword(auth, email, password);
      router.push("/admin/dashboard");
    } catch (err: any) {
      console.error(err);
      setError("Invalid email or password");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#F8F5F2] font-sans">
      <div className="w-full max-w-md rounded-2xl border border-[#D7C5B5] bg-white p-8 shadow-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#7A1E1E]">
            <span className="text-xl font-bold text-white">S</span>
          </div>
          <h1 className="mt-4 text-2xl font-bold text-[#1A252F]">SATMI Dashboard</h1>
          <p className="mt-2 text-sm text-[#475569]">Sign in with your admin credentials</p>
        </div>

        <form onSubmit={handleLogin} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-[#334155] mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-[#E2D8D0] px-4 py-2.5 text-sm outline-none focus:border-[#7A1E1E] focus:ring-1 focus:ring-[#7A1E1E]"
              placeholder="admin@satmi.com"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-[#334155] mb-1">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-[#E2D8D0] px-4 py-2.5 text-sm outline-none focus:border-[#7A1E1E] focus:ring-1 focus:ring-[#7A1E1E]"
              placeholder="••••••••"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={isLoading}
            className="mt-6 w-full rounded-lg bg-[#7A1E1E] px-4 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-[#5F1616] disabled:opacity-50"
          >
            {isLoading ? "Signing in..." : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}
