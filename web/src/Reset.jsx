import React, { useState } from "react";
import { api, setToken } from "./api.js";

// 🔑 Naujas slaptažodis pagal nuorodą iš el. laiško (#/reset/<raktas>)
export default function Reset({ token, onLogin }) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const r = await api("/password/reset", { method: "POST", body: { token, password: pw } });
      setToken(r.token);
      window.location.hash = "";
      onLogin(r.user);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return (
    <div className="login">
      <div className="login-box">
        <img className="logo" src="/logo.svg" alt="" />
        <form className="card" onSubmit={submit}>
          <h3 className="serif" style={{ marginTop: 0, fontSize: 22 }}>🔑 Naujas slaptažodis</h3>
          <div className="field">
            <label htmlFor="np">Sugalvokite naują slaptažodį (bent 8 simboliai)</label>
            <input id="np" className="input" type="password" minLength={8} value={pw} onChange={e => setPw(e.target.value)}
                   autoComplete="new-password" required />
          </div>
          {error && <div className="error">{error}</div>}
          <button className="btn gold block" disabled={busy}>{busy ? "Palaukite…" : "Išsaugoti ir prisijungti"}</button>
        </form>
      </div>
    </div>
  );
}
