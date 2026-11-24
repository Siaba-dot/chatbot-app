import React, { useEffect, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Login from "./Login.jsx";
import Projects from "./Projects.jsx";
import Editor from "./Editor.jsx";
import Admin from "./Admin.jsx";
import Reset from "./Reset.jsx";
import { Terms, Privacy } from "./Legal.jsx";

// Paprastas maršrutizavimas per # (veikia be serverio nustatymų): #/ – projektai, #/p/<id> – redaktorius
function useRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const f = () => setHash(window.location.hash);
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  const m = hash.match(/^#\/p\/([a-f0-9]{12})/);
  if (hash.startsWith("#/admin")) return { page: "admin" };
  if (hash.startsWith("#/terms")) return { page: "terms" };
  if (hash.startsWith("#/privacy")) return { page: "privacy" };
  const r = hash.match(/^#\/reset\/([\w-]+)/);
  if (r) return { page: "reset", token: r[1] };
  return m ? { page: "editor", id: m[1] } : { page: "projects" };
}

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(!!getToken());
  const route = useRoute();

  useEffect(() => {
    if (getToken()) {
      api("/me").then(setUser).catch(() => setToken("")).finally(() => setChecking(false));
    }
    const out = () => setUser(null);
    window.addEventListener("logout", out);
    return () => window.removeEventListener("logout", out);
  }, []);

  if (checking) return null;
  if (route.page === "terms") return <Terms />;       // viešai – ir neprisijungus
  if (route.page === "privacy") return <Privacy />;
  if (route.page === "reset") return <Reset token={route.token} onLogin={u => setUser(u)} />;
  if (!user) return <Login onLogin={u => setUser(u)} />;

  const logout = () => { setToken(""); setUser(null); window.location.hash = ""; };
  return (
    <>
      <header className="topbar">
        <div className="brand" onClick={() => (window.location.hash = "")}>
          <img src="/logo.svg" alt="" />
          <b>Reels montavimo studija</b>
        </div>
        {route.page !== "projects" && (
          <button className="btn small nav-back" onClick={() => (window.location.hash = "")}>← Mano projektai</button>
        )}
        {user.plan === "admin" && route.page !== "admin" && (
          <button className="btn small nav-back" onClick={() => (window.location.hash = "#/admin")}>👑 Klientai</button>
        )}
        <div className="spacer" />
        <div className="who">
          <b>{user.name}</b>
          {user.plan_title}{user.minutes_left != null && user.plan === "premium" ? ` · liko ${Math.floor(user.minutes_left)} min.` : ""}
          {user.ai_clips_left != null && user.plan !== "basic" ? ` · AI kadrų ${user.ai_clips_left}` : ""}
        </div>
        <button className="btn small ghost" onClick={logout}>Atsijungti</button>
      </header>
      {route.page === "admin" && user.plan === "admin"
        ? <Admin me={user} />
        : route.page === "editor"
        ? <Editor key={route.id} id={route.id} user={user} />
        : <Projects user={user} onUserChange={() => api("/me").then(setUser)} />}
    </>
  );
}
