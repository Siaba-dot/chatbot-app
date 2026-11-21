import React, { useState } from "react";
import { api, setToken } from "./api.js";
import Story from "./Story.jsx";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api("/login", { method: "POST", body: { username, password } });
      setToken(r.token);
      onLogin(r.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

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
          <div className="field">
            <label htmlFor="u">Prisijungimo vardas</label>
            <input id="u" className="input" value={username} onChange={e => setUsername(e.target.value)}
                   autoComplete="username" autoCapitalize="none" required />
          </div>
          <div className="field">
            <label htmlFor="p">Slaptažodis</label>
            <input id="p" className="input" type="password" value={password}
                   onChange={e => setPassword(e.target.value)} autoComplete="current-password" required />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn gold block" disabled={busy}>{busy ? "Jungiamasi…" : "Prisijungti"}</button>
        </form>
      </div>
    </div>
  );
}
