import React, { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function AuthDialog({ open, onOpenChange, onSuccess }) {
  const { login, register, formatApiError } = useAuth();
  const [mode, setMode] = useState("register");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (mode === "register") await register(email, password, name);
      else await login(email, password);
      toast.success(mode === "register" ? "Account created" : "Welcome back");
      onSuccess && onSuccess();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-slate-900 border-slate-700 text-slate-100 max-w-md" data-testid="auth-dialog">
        <DialogHeader>
          <DialogTitle className="font-display flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-amber-400" />
            {mode === "register" ? "Save your deck" : "Welcome back"}
          </DialogTitle>
          <DialogDescription className="text-slate-400">
            {mode === "register"
              ? "Create a free account to save this deck and access it anywhere."
              : "Log in to save this deck to your account."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4 mt-2">
          {mode === "register" && (
            <div>
              <Label className="text-slate-300">Name</Label>
              <Input data-testid="auth-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Planeswalker" className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
            </div>
          )}
          <div>
            <Label className="text-slate-300">Email</Label>
            <Input data-testid="auth-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" />
          </div>
          <div>
            <Label className="text-slate-300">Password</Label>
            <Input data-testid="auth-password" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1.5 bg-slate-950 border-slate-700 text-slate-100 focus-visible:ring-amber-400" placeholder={mode === "register" ? "At least 6 characters" : ""} />
          </div>
          <Button data-testid="auth-submit" type="submit" disabled={loading} className="w-full h-11 bg-amber-400 hover:bg-amber-500 text-stone-900 font-semibold">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : mode === "register" ? "Create account & save" : "Log in & save"}
          </Button>
        </form>
        <p className="text-sm text-slate-400 text-center">
          {mode === "register" ? "Already have an account? " : "Need an account? "}
          <button data-testid="auth-toggle-mode" onClick={() => setMode(mode === "register" ? "login" : "register")} className="text-amber-400 hover:underline">
            {mode === "register" ? "Log in" : "Sign up"}
          </button>
        </p>
      </DialogContent>
    </Dialog>
  );
}
