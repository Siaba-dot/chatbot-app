import React, { useEffect, useState } from "react";
import { api, getToken, setToken } from "./api.js";
import Login from "./Login.jsx";
import Projects from "./Projects.jsx";
import Editor from "./Editor.jsx";

// Paprastas maršrutizavimas per # (veikia be serverio nustatymų): #/ – projektai, #/p/<id> – redaktorius
function useRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const f = () => setHash(window.location.hash);
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  const m = hash.match(/^#\/p\/([a-f0-9]{12})/);
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
  if (!user) return <Login onLogin={u => setUser(u)} />;

  const logout = () => { setToken(""); setUser(null); window.location.hash = ""; };
  return (
    <>
      <header className="topbar">
        <div className="brand" onClick={() => (window.location.hash = "")}>
          <img src="/logo.svg" alt="" />
          <b>Reels montavimo studija</b>
        </div>
        <div className="spacer" />
        <div className="who">
          <b>{user.name}</b>
          {user.plan_title}{user.minutes_left != null ? ` · liko ${Math.floor(user.minutes_left)} min.` : ""}
        </div>
        <button className="btn small ghost" onClick={logout}>Atsijungti</button>
      </header>
      {route.page === "editor"
        ? <Editor key={route.id} id={route.id} user={user} />
        : <Projects user={user} />}
    </>
  );
}
