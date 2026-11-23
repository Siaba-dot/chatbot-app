import React, { useEffect, useState } from "react";
import { api, fileUrl } from "./api.js";

// 📚 Mano AI kadrai – kartą sukurti (ir apmokėti) kadrai, naudojami bet kuriame Reels'e nemokamai
function fmt(t) {
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function Library({ id, proj, setProj, mode, ModeChips, chooseMode, setToast, setError, refresh }) {
  const [items, setItems] = useState(null);
  const [pick, setPick] = useState(null);
  const [at, setAt] = useState(0);
  const [busy, setBusy] = useState(false);
  const lines = proj.lines || [];

  useEffect(() => { api("/library").then(r => setItems(r.items)).catch(() => setItems([])); }, [refresh]);

  if (!items || items.length === 0) return null;

  async function use(asClip) {
    setBusy(true);
    try {
      const line = lines[at];
      const p = await api(`/projects/${id}/broll/library`, { method: "POST", body: {
        lid: pick.id, t: line ? line[0] : 0, d: line ? Math.min(4, Math.max(2.5, line[1] - line[0])) : 3,
        mode, as_clip: asClip } });
      setProj(p);
      setToast(asClip ? "Kadras pridėtas kaip įrašas 🎬" : "Kadras įterptas – nemokamai 📚");
      setPick(null);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!window.confirm("Ištrinti šį kadrą iš bibliotekos? Jau sukurtuose Reels'uose jis liks.")) return;
    await api(`/library/${pick.id}`, { method: "DELETE" });
    setItems(items.filter(x => x.id !== pick.id));
    setPick(null);
  }

  return (
    <div className="section">
      <h3>📚 Mano AI kadrai ({items.length})</h3>
      <div className="hint" style={{ marginBottom: 8 }}>Visi jūsų sukurti AI kadrai – naudokite bet kuriame Reels'e, nemokamai.</div>
      <div className="tiles small">
        {items.map(it => (
          <button key={it.id} type="button" className="tile" title={it.prompt} onClick={() => { setPick(it); setAt(0); }}>
            <div className="img"><img src={fileUrl(`/library/${it.id}/thumb`)} alt="" loading="lazy" /></div>
            <div className="name">{it.prompt.slice(0, 40)}</div>
          </button>
        ))}
      </div>

      {pick && (
        <div className="modal" onClick={() => !busy && setPick(null)}>
          <div className="card" onClick={e => e.stopPropagation()}>
            <h3 className="serif" style={{ marginTop: 0, fontSize: 20 }}>📚 {pick.prompt.slice(0, 60)}</h3>
            <video src={fileUrl(`/library/${pick.id}/video`)} autoPlay muted loop playsInline
                   style={{ width: "100%", maxHeight: 260, objectFit: "contain", borderRadius: 12, background: "#000", marginBottom: 12 }} />
            {lines.length > 0 && (
              <div className="field">
                <label>Ties sakiniu</label>
                <select className="input" value={at} onChange={e => setAt(+e.target.value)}>
                  {lines.map((l, i) => <option key={i} value={i}>{fmt(l[0])} – {l[2].slice(0, 50)}</option>)}
                </select>
              </div>
            )}
            <div className="field"><label>Kaip rodyti</label><ModeChips value={mode} onChange={chooseMode} /></div>
            <div className="row">
              <button className="btn gold" onClick={() => use(false)} disabled={busy}>{busy ? "…" : "🎞 Įterpti (nemokamai)"}</button>
              <button className="btn" onClick={() => use(true)} disabled={busy}>Kaip įrašą</button>
              <span className="spacer" />
              <button className="btn small ghost danger" onClick={remove} disabled={busy} title="Ištrinti iš bibliotekos">🗑</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
