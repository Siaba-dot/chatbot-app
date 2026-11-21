import React, { useEffect, useState } from "react";
import { api, fileUrl } from "./api.js";

function ago(t) {
  const s = Date.now() / 1000 - t;
  if (s < 60) return "ką tik";
  if (s < 3600) return `prieš ${Math.floor(s / 60)} min.`;
  if (s < 86400) return `prieš ${Math.floor(s / 3600)} val.`;
  return new Date(t * 1000).toLocaleDateString("lt-LT");
}

export default function Projects() {
  const [list, setList] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { api("/projects").then(setList).catch(e => setError(e.message)); }, []);

  async function create() {
    setBusy(true);
    try {
      const p = await api("/projects", { method: "POST", body: { title: "Naujas Reels" } });
      window.location.hash = "#/p/" + p.id;
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
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
      <div className="grid-projects">
        <div className="proj new" onClick={busy ? undefined : create}>
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
                <div><button className="btn small ghost danger" onClick={e => remove(e, p)}>Ištrinti</button></div>
              </div>
            </div>
          );
        })}
      </div>
      {list && list.length === 0 && (
        <p className="hint" style={{ marginTop: 18 }}>Dar neturite projektų – spauskite „Naujas Reels“.</p>
      )}
    </div>
  );
}
