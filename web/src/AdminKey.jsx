import React, { useEffect, useState } from "react";
import { api } from "./api.js";

// Administratoriui: OpenAI raktas (kalbos atpažinimas, AI aprašymai, efektų parinkimas)
export default function AdminKey({ onChange }) {
  const [st, setSt] = useState(null);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => { api("/admin/openai").then(x => { setSt(x); setOpen(!x.set); }).catch(() => {}); }, []);

  async function save(e, remove = false) {
    e && e.preventDefault();
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await api("/admin/openai", { method: "POST", body: { key: remove ? "" : key } });
      setSt(r); setKey("");
      setMsg(remove ? "Raktas pašalintas." : "Raktas išsaugotas ir veikia ✅");
      onChange && onChange();
    } catch (e2) { setErr(e2.message); }
    finally { setBusy(false); }
  }

  if (!st) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="row" style={{ cursor: "pointer" }} onClick={() => setOpen(o => !o)}>
        <b>🔑 OpenAI raktas</b>
        <span className={st.set ? "pill" : "pill"} style={st.set ? {} : { color: "var(--danger)", borderColor: "var(--danger)" }}>
          {st.set ? `įrašytas …${st.tail}` : "neįrašytas"}
        </span>
        <span className="spacer" />
        <span className="hint">{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <form onSubmit={save} style={{ marginTop: 12 }}>
          <div className="hint" style={{ marginBottom: 10 }}>
            Reikalingas kalbos atpažinimui (titrams), AI aprašymams ir efektų parinkimui pagal tai, ką sakote.
            Raktą gausite <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">platform.openai.com → API keys</a>.
            Jis išsaugomas serveryje ir veikia ir senojoje studijoje.
          </div>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input className="input" type="password" value={key} onChange={e => setKey(e.target.value)} placeholder="sk-…" autoComplete="off" />
            <button className="btn gold" disabled={busy || !key.trim()}>{busy ? "Tikrinama…" : "Išsaugoti"}</button>
          </div>
          {st.set && <button type="button" className="btn small ghost danger" style={{ marginTop: 8 }} onClick={e => save(e, true)} disabled={busy}>Pašalinti raktą</button>}
          {msg && <div className="hint" style={{ color: "var(--ok)", marginTop: 8 }}>{msg}</div>}
          {err && <div className="error">{err}</div>}
        </form>
      )}
    </div>
  );
}
