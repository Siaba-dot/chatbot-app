import React, { useEffect, useState } from "react";
import { api, setToken } from "./api.js";
import Story from "./Story.jsx";

export default function Login({ onLogin }) {
  const [mode, setMode] = useState("login");   // login | register
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");  // robotams (paslėptas)
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [canRegister, setCanRegister] = useState(false);

  useEffect(() => { api("/public/settings").then(s => setCanRegister(!!s.registration)).catch(() => {}); }, []);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = mode === "register"
        ? await api("/register", { method: "POST", body: { name, email: username, password, website } })
        : await api("/login", { method: "POST", body: { username, password } });
      setToken(r.token);
      onLogin(r.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const reg = mode === "register";
  return (
    <div className="login">
      <div className="login-box">
        <img className="logo" src="/logo.svg" alt="" />
        <div className="kicker">LIETUVIŠKA STUDIJA · BALTIJOS GINTARO DVASIA</div>
        <h1 className="goldtext">Reels montavimo studija</h1>
        <div className="quote">Gintaras milijonus metų saugo sustabdytą akimirką.<br />Mes darome tą patį su jūsų video.</div>
        <div className="quote goldtext" style={{ fontStyle: "normal", marginTop: -12 }}>Jūsų akimirkos – kaip gintaras: išsaugotos gražiausios.</div>
        <Story />
        <form className="card" onSubmit={submit}>
          <h3 className="serif" style={{ marginTop: 0, fontSize: 22 }}>{reg ? "Registracija" : "Prisijungimas"}</h3>
          {reg && (
            <div className="field">
              <label htmlFor="n">Vardas arba įmonės pavadinimas</label>
              <input id="n" className="input" value={name} onChange={e => setName(e.target.value)} maxLength={80}
                     autoComplete="organization" placeholder="Pvz.: Kirpykla „Žavesys“" required />
            </div>
          )}
          <div className="field">
            <label htmlFor="u">{reg ? "El. paštas" : "Prisijungimo vardas arba el. paštas"}</label>
            <input id="u" className="input" type={reg ? "email" : "text"} value={username} onChange={e => setUsername(e.target.value)}
                   autoComplete={reg ? "email" : "username"} autoCapitalize="none" required />
          </div>
          <div className="field">
            <label htmlFor="p">{reg ? "Sugalvokite slaptažodį (bent 8 simboliai)" : "Slaptažodis"}</label>
            <input id="p" className="input" type="password" value={password} minLength={reg ? 8 : undefined}
                   onChange={e => setPassword(e.target.value)} autoComplete={reg ? "new-password" : "current-password"} required />
          </div>
          <input value={website} onChange={e => setWebsite(e.target.value)} tabIndex={-1} autoComplete="off" aria-hidden="true"
                 style={{ position: "absolute", left: -9999, width: 1, height: 1, opacity: 0 }} />
          {reg && <div className="hint" style={{ marginBottom: 10 }}>Iš karto gausite Pagrindinį planą. AI funkcijos (titrai iš kalbos, AI balsai ir kadrai) – Premium plane.</div>}
          {error && <div className="error">{error}</div>}
          <button className="btn gold block" disabled={busy}>{busy ? "Palaukite…" : reg ? "Registruotis" : "Prisijungti"}</button>
          {canRegister && (
            <div style={{ textAlign: "center", marginTop: 12 }}>
              <button type="button" className="btn ghost small" onClick={() => { setMode(reg ? "login" : "register"); setError(""); }}>
                {reg ? "Jau turite paskyrą? Prisijungti" : "Neturite paskyros? Registruotis"}</button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
