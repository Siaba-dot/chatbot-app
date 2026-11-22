import React, { useState } from "react";
import { api, fileUrl } from "./api.js";
import Veo from "./Veo.jsx";

// 🎞 Nemokami video intarpai (Pixabay arba Pexels): paieška, įterpimas ties sakiniu arba kaip atskiras įrašas, AI parinkimas
function fmt(t) {
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

const MODES = [["card", "🪟 Kortelė"], ["split", "◧ Pusė ekrano"], ["full", "⬛ Visas kadras"]];
const MODE_HELP = { card: "Mažas kadras kampe – jūs matotės visą laiką; studija pati randa kampą, kur nėra jūsų veido.", split: "Intarpas viršuje, jūs – apačioje.",
                    full: "Intarpas uždengia visą kadrą (balsas ir titrai lieka)." };

function ModeChips({ value, onChange }) {
  return (
    <div className="chips" style={{ marginBottom: 0 }}>
      {MODES.map(([k, l]) => (
        <button key={k} type="button" className={"chip" + (value === k ? " on" : "")} style={{ padding: "3px 9px", fontSize: 12 }}
                onClick={() => onChange(k)}>{l}</button>
      ))}
    </div>
  );
}

export default function Broll({ id, proj, setProj, s, user, setToast, setError }) {
  const [mode, setMode] = useState(() => { try { return localStorage.getItem("brollMode") || "card"; } catch { return "card"; } });
  const chooseMode = m => { setMode(m); try { localStorage.setItem("brollMode", m); } catch { /* */ } };
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [busy, setBusy] = useState("");
  const [pick, setPick] = useState(null);   // pasirinktas video (langas „kur įterpti“)
  const lines = proj.lines || [];
  const [at, setAt] = useState(0);

  const noStock = !user.pexels;

  async function search(e, page = 1) {
    e && e.preventDefault();
    if (!q.trim()) return;
    setBusy("search");
    try {
      const r = await api(`/stock/search?q=${encodeURIComponent(q)}&fmt=${encodeURIComponent(s.format)}&page=${page}`);
      setRes({ ...r, page, videos: page > 1 && res ? [...res.videos, ...r.videos] : r.videos });
    } catch (e2) { setError(e2.message); }
    finally { setBusy(""); }
  }

  async function add(asClip) {
    setBusy("add");
    try {
      const line = lines[at];
      const t = line ? line[0] : 0;
      const d = line ? Math.min(3.5, Math.max(2, line[1] - line[0])) : 2.5;
      const p = await api(`/projects/${id}/broll`, { method: "POST",
        body: { pexels_id: pick.id, provider: pick.provider, t, d, query: q, as_clip: asClip, mode } });
      setProj(p);
      setToast(asClip ? "Pridėta kaip įrašas 🎬" : "Intarpas įterptas 🎞");
      setPick(null);
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }

  async function auto() {
    setBusy("auto");
    try {
      const p = await api(`/projects/${id}/broll/auto?mode=${mode}`, { method: "POST" });
      setProj(p);
      setToast("AI parinko intarpus ✨");
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }

  async function edit(b, patch) {
    setProj(await api(`/projects/${id}/broll/${b.id}`, { method: "PUT", body: patch }));
  }
  async function remove(b) {
    setProj(await api(`/projects/${id}/broll/${b.id}`, { method: "DELETE" }));
  }

  const lineAt = t => {
    let k = 0;
    lines.forEach((l, i) => { if (l[0] <= t + 0.01) k = i; });
    return lines[k] ? lines[k][2] : "";
  };

  return (
    <>
      <Veo id={id} proj={proj} setProj={setProj} user={user} mode={mode} ModeChips={ModeChips} chooseMode={chooseMode}
           setToast={setToast} setError={setError} />
      {noStock ? (
        <div className="card section">
          <h3>🎞 Nemokami video intarpai</h3>
          <p className="hint">Milijonai nemokamų, licencijuotų video: kalbate apie automobilius – įterpiamas kadras su
            automobiliu, apie kavą – su kava.</p>
          <p className="hint">{user.plan === "admin"
            ? "Įjunkite: „← Mano projektai“ → „🎞 Pixabay raktas“ (nemokamas)."
            : "Ši funkcija dar neįjungta – kreipkitės į studijos administratorių."}</p>
        </div>
      ) : (
      <div className="section card">
        <div className="row">
          <div style={{ flex: 1, minWidth: 200 }}>
            <h3 style={{ margin: 0 }}>✨ AI parinks intarpus</h3>
            <div className="hint">Pagal tai, ką sakote, įterps 3–4 tinkamus kadrus. Reikia paruoštų titrų.</div>
          </div>
          <button className="btn gold" onClick={auto} disabled={!!busy || !user.ai || !proj.prepared}>
            {busy === "auto" ? "Ieškoma…" : "✨ Parinkti"}</button>
        </div>
        {!proj.prepared && <div className="hint" style={{ marginTop: 6 }}>💬 Titrai → „Paruošti titrus“ – tada AI žinos, ką sakote.</div>}
        <div style={{ marginTop: 12 }}>
          <div className="hint" style={{ marginBottom: 6 }}>Kaip rodyti naujus intarpus:</div>
          <ModeChips value={mode} onChange={chooseMode} />
          <div className="hint" style={{ marginTop: 4 }}>{MODE_HELP[mode]}</div>
        </div>
      </div>

      )}

      {(proj.broll || []).length > 0 && (
        <div className="section">
          <h3>Įterpti intarpai</h3>
          <div className="clips">
            {proj.broll.map(b => (
              <div className="clip" key={b.id}>
                <img src={b.image && b.image.startsWith("/api") ? fileUrl(b.image.slice(4)) : b.image} alt="" />
                <div className="info">
                  <b>{fmt(b.t)} · {b.query || "intarpas"}</b>
                  <span>„{lineAt(b.t).slice(0, 60)}“</span>
                  <div style={{ marginTop: 4 }}><ModeChips value={b.mode || "full"} onChange={m => edit(b, { mode: m })} /></div>
                  {(b.mode || "full") === "card" && (
                    <div className="chips" style={{ marginBottom: 0, marginTop: 4 }}>
                      {[["auto", "✨ Kur nėra veido"], ["tl", "↖ Kairėje"], ["tr", "↗ Dešinėje"]].map(([k, l]) => (
                        <button key={k} type="button" className={"chip" + ((b.pos || "auto") === k ? " on" : "")}
                                style={{ padding: "3px 9px", fontSize: 12 }} onClick={() => edit(b, { pos: k })}>{l}</button>
                      ))}
                    </div>
                  )}
                  <div className="row" style={{ gap: 6, marginTop: 4 }}>
                    <span className="hint">Trukmė</span>
                    {[2, 2.5, 3, 4].map(d => (
                      <button key={d} className={"chip" + (Math.abs(b.d - d) < 0.05 ? " on" : "")} style={{ padding: "2px 8px" }}
                              onClick={() => edit(b, { d })}>{d} s</button>
                    ))}
                  </div>
                </div>
                <button className="btn small ghost" onClick={() => edit(b, { t: Math.max(0, b.t - 0.5) })} title="Anksčiau">−½s</button>
                <button className="btn small ghost" onClick={() => edit(b, { t: b.t + 0.5 })} title="Vėliau">+½s</button>
                <button className="btn small ghost danger" onClick={() => remove(b)} aria-label="Pašalinti">✕</button>
              </div>
            ))}
          </div>
          <div className="hint">Jūsų balsas ir titrai lieka. Pakeitimai matysis sukūrus peržiūrą.</div>
        </div>
      )}

      {!noStock && <div className="section">
        <h3>🔎 Ieškoti {user.stock || "video"}</h3>
        <form className="row" style={{ flexWrap: "nowrap" }} onSubmit={search}>
          <input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="Pvz.: car winter, coffee, beach sunset" />
          <button className="btn" disabled={!!busy || !q.trim()}>{busy === "search" ? "…" : "Ieškoti"}</button>
        </form>
        <div className="hint" style={{ margin: "6px 0 10px" }}>Geriausiai randa angliškai. Video iš {user.stock === "Pexels"
          ? <a href="https://www.pexels.com" target="_blank" rel="noreferrer">Pexels</a>
          : <a href="https://pixabay.com/videos/" target="_blank" rel="noreferrer">Pixabay</a>} – nemokami ir licencijuoti.</div>
        {res && (
          <>
            <div className="tiles">
              {res.videos.map(v => (
                <button key={v.id} type="button" className="tile" onClick={() => { setPick(v); setAt(0); }}>
                  <div className="img"><img src={v.image} alt="" loading="lazy" />
                    <span className="pill" style={{ position: "absolute", right: 5, bottom: 5 }}>{v.duration} s</span></div>
                  <div className="name">{v.user}</div>
                </button>
              ))}
            </div>
            {res.videos.length === 0 && <p className="hint">Nieko nerasta – pabandykite kitais žodžiais (angliškai).</p>}
            {res.videos.length >= 18 * res.page && (
              <button className="btn small" style={{ marginTop: 10 }} onClick={e => search(e, res.page + 1)} disabled={!!busy}>Daugiau</button>
            )}
          </>
        )}
      </div>

      }

      {pick && (
        <div className="modal" onClick={() => !busy && setPick(null)}>
          <div className="card" onClick={e => e.stopPropagation()}>
            <h3 className="serif" style={{ marginTop: 0, fontSize: 20 }}>Kur įterpti?</h3>
            <img src={pick.image} alt="" style={{ width: "100%", maxHeight: 220, objectFit: "cover", borderRadius: 12, marginBottom: 12 }} />
            {lines.length > 0 ? (
              <div className="field">
                <label>Ties sakiniu</label>
                <select className="input" value={at} onChange={e => setAt(+e.target.value)}>
                  {lines.map((l, i) => <option key={i} value={i}>{fmt(l[0])} – {l[2].slice(0, 50)}</option>)}
                </select>
              </div>
            ) : <p className="hint">Paruošus titrus, galėsite pasirinkti sakinį. Dabar intarpas bus pradžioje.</p>}
            <div className="field">
              <label>Kaip rodyti</label>
              <ModeChips value={mode} onChange={chooseMode} />
              <div className="hint">{MODE_HELP[mode]}</div>
            </div>
            <div className="row">
              <button className="btn gold" onClick={() => add(false)} disabled={!!busy}>{busy === "add" ? "Atsisiunčiama…" : "🎞 Įterpti kaip intarpą"}</button>
              <button className="btn" onClick={() => add(true)} disabled={!!busy}>🎬 Pridėti kaip įrašą</button>
            </div>
            <div className="hint" style={{ marginTop: 8 }}>„Kaip įrašą“ – kadras taps video dalimi (pvz. video be filmavimo su AI įgarsinimu).</div>
          </div>
        </div>
      )}
    </>
  );
}
