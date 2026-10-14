import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import ProtectedRoute from "@/components/ProtectedRoute";
import { lazy, Suspense } from "react";
import { Loader2 } from "lucide-react";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";

// Each page loads its own code when first opened, so the first visit doesn't download the deck
// builder's charts, the draft room and everything else up front. If a page's code can't be fetched
// because the site was updated while this tab was open, reload once to pick up the new version.
const lazyPage = (load) => lazy(() => load().then((m) => { try { sessionStorage.removeItem("grim_chunk_reload"); } catch { /* blocked */ } return m; },
  (err) => {
    let retried = false;
    try { retried = sessionStorage.getItem("grim_chunk_reload") === "1"; sessionStorage.setItem("grim_chunk_reload", "1"); } catch { /* blocked */ }
    if (!retried) { window.location.reload(); return new Promise(() => {}); }
    throw err;
  }));
const Dashboard = lazyPage(() => import("@/pages/Dashboard"));
const DeckBuilder = lazyPage(() => import("@/pages/DeckBuilder"));
const PublicDeck = lazyPage(() => import("@/pages/PublicDeck"));
const DraftSetup = lazyPage(() => import("@/pages/DraftSetup"));
const DraftRoom = lazyPage(() => import("@/pages/DraftRoom"));

const PageLoading = () => (
  <div className="h-screen flex items-center justify-center bg-[#060a14]"><Loader2 className="w-8 h-8 text-amber-400 animate-spin" /></div>
);

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<PageLoading />}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
              <Route path="/build" element={<DeckBuilder />} />
              <Route path="/deck/:id" element={<ProtectedRoute><DeckBuilder /></ProtectedRoute>} />
              <Route path="/d/:shareId" element={<PublicDeck />} />
              <Route path="/draft" element={<DraftSetup />} />
              <Route path="/draft/:shareId" element={<DraftRoom />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
        <Toaster position="bottom-right" theme="dark" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
