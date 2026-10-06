import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import { Toaster } from "@/components/ui/sonner";
import ProtectedRoute from "@/components/ProtectedRoute";
import Landing from "@/pages/Landing";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import DeckBuilder from "@/pages/DeckBuilder";
import PublicDeck from "@/pages/PublicDeck";

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/build" element={<DeckBuilder />} />
            <Route path="/deck/:id" element={<ProtectedRoute><DeckBuilder /></ProtectedRoute>} />
            <Route path="/d/:shareId" element={<PublicDeck />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="bottom-right" theme="dark" richColors />
      </AuthProvider>
    </div>
  );
}

export default App;
