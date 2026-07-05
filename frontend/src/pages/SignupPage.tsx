import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Layers,
  Mail,
  Lock,
  User,
  ArrowRight,
  AlertCircle,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { AuroraBackground } from "../components/ui/aurora-background";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Spinner } from "../components/ui/spinner";
import { FadeIn } from "../components/ui/motion";

// The backend authenticates by email, not a separate username field, so a
// bare "username" is mapped to this facility's local email convention
// (mirrors the seeded admin@industrialbrain.local account).
const DEFAULT_EMAIL = "ratish01@industrialbrain.local";
const DEFAULT_PASSWORD = "Ratish*966";

export const SignupPage: React.FC = () => {
  const { setTokens } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState(DEFAULT_EMAIL);
  const [password, setPassword] = useState(DEFAULT_PASSWORD);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          full_name: fullName.trim() || undefined,
        }),
      });
      if (res.status === 409) {
        setError(
          "An account with this email already exists — try signing in instead.",
        );
        return;
      }
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        setError(data?.detail ?? "Unable to create the account.");
        return;
      }
      const data = await res.json();
      setTokens(data.access_token, data.refresh_token);
      navigate("/knowledge", { replace: true });
    } catch {
      setError("Unable to reach the authentication service.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuroraBackground className="flex items-center justify-center px-6 py-12">
      <FadeIn className="w-full max-w-md">
        <div className="glass rounded-2xl p-8 shadow-2xl">
          <div className="mb-8 flex flex-col items-center text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-violet-500 shadow-glow">
              <Layers className="h-6 w-6 text-white" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight">
              Create your account
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Join the Industrial Brain console
            </p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="full-name">Full name</Label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="full-name"
                  type="text"
                  autoComplete="name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Ratish"
                  className="pl-9"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="signup-email">Email</Label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="signup-email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@facility.com"
                  className="pl-9"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="signup-password">Password</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="signup-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="pl-9"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                At least 8 characters.
              </p>
            </div>

            {error && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                <AlertCircle className="h-4 w-4 shrink-0" />
                {error}
              </div>
            )}

            <Button
              type="submit"
              variant="gradient"
              className="w-full"
              disabled={loading}
            >
              {loading ? (
                <Spinner className="h-4 w-4 text-white" />
              ) : (
                <>
                  Sign up <ArrowRight className="h-4 w-4" />
                </>
              )}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            Already have an account?{" "}
            <Link to="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
          <p className="mt-2 text-center text-xs text-muted-foreground">
            <Link to="/" className="hover:text-foreground">
              ← Back to home
            </Link>
          </p>
        </div>
      </FadeIn>
    </AuroraBackground>
  );
};
