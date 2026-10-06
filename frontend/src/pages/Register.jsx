import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Register() {
  const { register, formatApiError } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(email, password, name);
      toast.success("Account created");
      navigate("/dashboard");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Sign up failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#060a14] grim-grain flex items-center justify-center px-4">
      <div className="w-full max-w-md animate-fade-up">
        <Link to="/" className="flex items-center justify-center gap-2 mb-8" data-testid="logo">
          <Sparkles className="w-6 h-6 text-amber-400" />
          <span className="font-display text-2xl font-bold text-white">Grimoire</span>
        </Link>
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-7">
          <h1 className="font-display text-2xl font-bold text-white">Create account</h1>
          <p className="text-sm text-slate-400 mt-1">Start building your library.</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <Label className="text-slate-300">Name</Label>
              <Input data-testid="register-name" value={name} onChange={(e) => setName(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" placeholder="Planeswalker" />
            </div>
            <div>
              <Label className="text-slate-300">Email</Label>
              <Input data-testid="register-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
            </div>
            <div>
              <Label className="text-slate-300">Password</Label>
              <Input data-testid="register-password" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" placeholder="At least 6 characters" />
            </div>
            <Button data-testid="register-submit" type="submit" disabled={loading} className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Create account"}
            </Button>
          </form>
          <p className="text-sm text-slate-400 mt-5 text-center">
            Already have an account? <Link to="/login" className="text-amber-400 hover:underline" data-testid="to-login">Log in</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
