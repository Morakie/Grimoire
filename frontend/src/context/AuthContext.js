import React, { createContext, useContext, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = checking, false = logged out
  const [token, setToken] = useState(localStorage.getItem("grimoire_token") || "");

  useEffect(() => {
    let active = true;
    const check = async () => {
      if (!token) { setUser(false); return; }
      try {
        const { data } = await api.get("/auth/me");
        if (active) setUser(data);
      } catch (e) {
        localStorage.removeItem("grimoire_token");
        if (active) { setToken(""); setUser(false); }
      }
    };
    check();
    return () => { active = false; };
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
