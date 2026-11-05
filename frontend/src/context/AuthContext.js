import React, { createContext, useContext, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = logged out
  const [token, setToken] = useState(localStorage.getItem("grimoire_token") || "");

  useEffect(() => {
    let active = true;
    let timer = null;
    // Only a definite "not signed in" (401/403) logs you out. A server restart, an outage or no network
    // keeps the saved token and tries again for about a minute; after that the page treats you as
    // signed out for now, and the next page load tries again.
    // Worst case: 5 tries x 8 s timeout + 29 s of waits, about 70 s.
    const waits = [2000, 4000, 8000, 15000];
    const check = async (attempt = 0) => {
      if (!token) { setUser(false); return; }
      try {
        const { data } = await api.get("/auth/me", { timeout: 8000 });
        if (active) setUser(data);
      } catch (e) {
        if (!active) return;
        const status = e.response?.status;
        if (status === 401 || status === 403) {
          if (localStorage.getItem("grimoire_token") === token) localStorage.removeItem("grimoire_token");
          setToken(""); setUser(false);
        } else if (attempt < waits.length) {
          timer = setTimeout(() => check(attempt + 1), waits[attempt]);
        } else {
          setUser(false);
        }
      }
    };
    check();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [token]);

  const persist = (data) => {
    localStorage.setItem("grimoire_token", data.token);
    setToken(data.token);
    setUser(data.user);
  };

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    persist(data);
    return data.user;
  };

  const register = async (email, password, name) => {
    const { data } = await api.post("/auth/register", { email, password, name });
    persist(data);
    return data.user;
  };

  const logout = () => {
    localStorage.removeItem("grimoire_token");
    setToken("");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, login, register, logout, formatApiError }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
