// app/login/page.tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true); setError("");
    try {
      await login(email, password);
      router.push("/admin");
    } catch {
      setError("Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-sm mx-auto mt-20">
      <h2 className="text-xl font-bold text-foreground text-center mb-6">Login</h2>
      <div className="space-y-3">
        <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)}
          className="w-full h-10 bg-card border border-border rounded-md px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent-blue" />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)}
          className="w-full h-10 bg-card border border-border rounded-md px-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-accent-blue"
          onKeyDown={e => e.key === "Enter" && handleLogin()} />
        <button onClick={handleLogin} disabled={loading}
          className="w-full h-10 bg-accent-blue text-white rounded-md text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-50">
          {loading ? "..." : "Login"}
        </button>
        {error && <p className="text-critical text-xs text-center">{error}</p>}
      </div>
    </div>
  );
}
