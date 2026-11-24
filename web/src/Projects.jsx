import React, { useEffect, useState } from "react";
import { api, fileUrl } from "./api.js";
import AdminKey from "./AdminKey.jsx";

function ago(t) {
  const s = Date.now() / 1000 - t;
  if (s < 60) return "ką tik";
  if (s < 3600) return `prieš ${Math.floor(s / 60)} min.`;
  if (s < 86400) return `prieš ${Math.floor(s / 3600)} val.`;
  return new Date(t * 1000).toLocaleDateString("lt-LT");
}

export default function Projects({ user, onUserChange }) {
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api("/projects").then(setList).catch(e => setError(e.message)); }, []);

  const [naming, setNaming] = useState(null);  // naujo projekto pavadinimas (langas)

  async function create(e) {
    e && e.preventDefault();
    setBusy(true);
    try {
      const p = await api("/projects", { method: "POST", body: { title: (naming || "").trim() || "Naujas Reels" } });
      window.location.hash = "#/p/" + p.id;
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  }

  async function buy() {
    setBusy(true);
    try { window.location.href = (await api("/billing/checkout", { method: "POST" })).url; }
    catch (e) { setError(e.message); setBusy(false); }
  }
  async function portal() {
    setBusy(true);
    try { window.location.href = (await api("/billing/portal", { method: "POST" })).url; }
    catch (e) { setError(e.message); setBusy(false); }
  }
  useEffect(() => {  // grįžus iš apmokėjimo – atnaujinam planą
    if (window.location.hash.includes("paid=1")) {
      window.location.hash = "";
      setTimeout(() => onUserChange && onUserChange(), 1500);
    }
  }, []);  // eslint-disable-line

  async function rename(e, p) {
    e.stopPropagation();
    const title = window.prompt("Naujas pavadinimas:", p.title);
    if (!title || !title.trim() || title === p.title) return;
    await api(`/projects/${p.id}/settings`, { method: "PUT", body: { settings: {}, title } });
    setList(list.map(x => (x.id === p.id ? { ...x, title: title.trim() } : x)));
  }

  async function remove(e, p) {
    e.stopPropagation();
    if (!window.confirm(`Ištrinti „${p.title}“? Video ir įrašai bus pašalinti.`)) return;
    await api("/projects/" + p.id, { method: "DELETE" });
    setList(list.filter(x => x.id !== p.id));
  }

  return (
    <div className="page">
      <div className="kicker">MANO PROJEKTAI</div>
      <h2>Kurkime naują Reels ✨</h2>
      <div className="hint">Visi jūsų video išsaugomi čia – galite grįžti, pataisyti ir sukurti iš naujo.</div>
      {error && <div className="error">{error}</div>}
      {user && user.plan === "basic" && (
        <div className="card" style={{ marginTop: 14 }}>
          <b>⭐ Jūsų planas – Pagrindinis.</b>
          <div className="hint" style={{ marginTop: 4 }}>
            Galite kurti Reels su šablonais, titrais, efektais, filmuoti su sufleriu ir karpyti. AI funkcijos – titrai iš
            kalbos, natūralūs lietuviški AI balsai ir AI sukurti kadrai – Premium plane.
            {user.contact && !user.billing ? <> Norite Premium? Susisiekite: <b style={{ color: "var(--honey)" }}>{user.contact}</b></> : null}
          </div>
          {user.billing && (
            <button className="btn gold" style={{ marginTop: 10 }} onClick={buy} disabled={busy}>
              ⭐ Įsigyti Premium{user.price_label ? ` – ${user.price_label}` : ""}</button>
          )}
        </div>
      )}
      {user && user.trial_until && (() => {
        const d = Math.max(1, Math.ceil((user.trial_until * 1000 - Date.now()) / 86400000));
        return (
          <div className="card" style={{ marginTop: 14 }}>
            <b>🎁 Premium bandymas – liko {d} {d === 1 ? "diena" : d < 10 ? "dienos" : "dienų"}</b>
            <div className="hint" style={{ marginTop: 4 }}>
              Išbandykite AI titrus iš kalbos, lietuviškus AI balsus ir AI kadrus. Pasibaigus bandymui paskyra lieka su
              nemokamu Pagrindiniu planu – niekas automatiškai nenuskaičiuojama.
              {user.contact && !user.billing ? <> Norite pasilikti Premium? Susisiekite: <b style={{ color: "var(--honey)" }}>{user.contact}</b></> : null}
            </div>
            {user.billing && (
              <button className="btn gold" style={{ marginTop: 10 }} onClick={buy} disabled={busy}>
                ⭐ Pasilikti Premium{user.price_label ? ` – ${user.price_label}` : ""}</button>
            )}
          </div>
        );
      })()}
      {user && user.plan === "premium" && user.subscribed && (
        <div className="hint" style={{ marginTop: 10 }}>⭐ Premium prenumerata aktyvi ·{" "}
          <button className="btn small ghost" onClick={portal} disabled={busy}>Valdyti prenumeratą / sąskaitas</button></div>
      )}
      {user && user.plan === "admin" && <AdminKey kind="openai" onChange={onUserChange} />}
      {user && user.plan === "admin" && <AdminKey kind="gemini" onChange={onUserChange} />}
      {user && user.plan === "admin" && <AdminKey kind="pixabay" onChange={onUserChange} />}
      <div className="grid-projects">
        <div className="proj new" onClick={() => setNaming("")}>
          <div><span>＋</span>{busy ? "Kuriama…" : "Naujas Reels"}</div>
        </div>
        {(list || []).map(p => {
          const fin = p.outputs && p.outputs.final;
          return (
            <div className="proj" key={p.id} onClick={() => (window.location.hash = "#/p/" + p.id)}>
              <div className="thumb" style={fin && fin.cover
                ? { backgroundImage: `url(${fileUrl(`/projects/${p.id}/files/cover.jpg`, "&v=" + fin.at)})` } : {}}>
                {!(fin && fin.cover) && "🎬"}
              </div>
              {fin && <span className="pill badge">Paruošta</span>}
              <div className="meta">
                <b>{p.title}</b>
                <span>{p.clips} įraš. · {ago(p.updated)}</span>
                <div className="row" style={{ gap: 6, marginTop: 6 }}>
                  <button className="btn small ghost icon" onClick={e => rename(e, p)} title="Pervadinti" aria-label="Pervadinti">✏️</button>
                  <button className="btn small ghost danger icon" onClick={e => remove(e, p)} title="Ištrinti" aria-label="Ištrinti">🗑</button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {naming !== null && (
        <div className="modal" onClick={() => !busy && setNaming(null)}>
          <form className="card" onClick={e => e.stopPropagation()} onSubmit={create}>
            <h3 className="serif" style={{ marginTop: 0, fontSize: 22 }}>Kaip pavadinsime šį Reels?</h3>
            <input className="input" autoFocus value={naming} maxLength={80} placeholder="Pvz.: Automobilių priežiūra"
                   onChange={e => setNaming(e.target.value)} />
            <div className="hint" style={{ margin: "6px 0 14px" }}>Pavadinimą matysite tik jūs – „Mano projektuose“.</div>
            <div className="row">
              <button type="button" className="btn ghost" onClick={() => setNaming(null)} disabled={busy}>Atšaukti</button>
              <span className="spacer" />
              <button className="btn gold" disabled={busy}>{busy ? "Kuriama…" : "Sukurti"}</button>
            </div>
          </form>
        </div>
      )}
      {list && list.length === 0 && (
        <p className="hint" style={{ marginTop: 18 }}>Dar neturite projektų – spauskite „Naujas Reels“.</p>
      )}
    </div>
  );
}
