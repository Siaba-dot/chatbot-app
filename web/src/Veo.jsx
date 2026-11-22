import React, { useState } from "react";
import { api, waitJob } from "./api.js";

// 🎬 Google Veo: AI sukuria unikalų video kadrą pagal aprašymą (fone, 1–3 min.)
function fmt(t) {
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default function Veo({ id, proj, setProj, user, mode, ModeChips, chooseMode, setToast, setError }) {
  const [prompt, setPrompt] = useState("");
  const [at, setAt] = useState(0);
  const [job, setJob] = useState(null);
  const [ideas, setIdeas] = useState(null);
  const [busy, setBusy] = useState(false);
  const lines = proj.lines || [];

  if (!user.veo) {
    return user.plan === "admin" ? (
      <div className="card section">
        <h3>🎬 AI sukurti kadrai (Google Veo)</h3>
        <p className="hint">Unikalūs video kadrai pagal jūsų aprašymą, pvz. „kava pilama į puodelį, saulėtas rytas“.
          Įjunkite: „← Mano projektai“ → „🇱🇹 Google (Gemini) raktas“.</p>
      </div>
    ) : null;
  }

  async function suggest() {
    setBusy(true);
    try {
      const r = await api(`/projects/${id}/broll/veo_ideas`, { method: "POST" });
      setIdeas(r.ideas);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  function useIdea(it) {
    setPrompt(it.prompt);
    let k = 0;
    lines.forEach((l, i) => { if (l[0] <= it.t + 0.01) k = i; });
    setAt(k);
  }

  async function create(asClip) {
    setError("");
    const line = lines[at];
    try {
      const j = await api(`/projects/${id}/broll/veo`, { method: "POST", body: {
        prompt, t: line ? line[0] : 0, d: line ? Math.min(4, Math.max(2.5, line[1] - line[0])) : 3,
        mode, as_clip: asClip } });
      setJob(j);
      await waitJob(j.id, setJob);
      setProj(await api("/projects/" + id));
      setToast(asClip ? "AI kadras pridėtas kaip įrašas 🎬" : "AI kadras įterptas 🎬");
      setPrompt("");
    } catch (e) { setError(e.message); }
    finally { setJob(null); }
  }

  return (
    <div className="section card">
      <h3 style={{ marginTop: 0 }}>🎬 AI sukurs kadrą (Google Veo)</h3>
      <div className="hint" style={{ marginBottom: 10 }}>
        Aprašykite, ką turi rodyti kamera – AI sukurs unikalų video, kokio neturi niekas kitas. Kūrimas trunka 1–3 min.
        Google už kiekvieną kadrą ima mokestį pagal savo kainas.
      </div>
      {user.ai && proj.prepared && (
        <div style={{ marginBottom: 10 }}>
          <button className="btn small" onClick={suggest} disabled={busy || !!job}>{busy ? "Galvojama…" : "✨ Pasiūlyk idėjų pagal mano kalbą"}</button>
          {ideas && ideas.length > 0 && (
            <div className="clips" style={{ marginTop: 8 }}>
              {ideas.map((it, i) => (
                <div key={i} className="clip" style={{ cursor: "pointer" }} onClick={() => useIdea(it)}>
                  <div className="info"><b>{fmt(it.t)}</b><span>{it.prompt}</span></div>
                  <span className="hint">Naudoti →</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <textarea className="input" rows={3} value={prompt} maxLength={400} disabled={!!job}
                onChange={e => setPrompt(e.target.value)}
                placeholder="Pvz.: žieminė automobilio padanga sniege, iš arti, rytinė šviesa" />
      {lines.length > 0 && (
        <div className="field" style={{ marginTop: 8 }}>
          <label>Ties sakiniu</label>
          <select className="input" value={at} onChange={e => setAt(+e.target.value)} disabled={!!job}>
            {lines.map((l, i) => <option key={i} value={i}>{fmt(l[0])} – {l[2].slice(0, 50)}</option>)}
          </select>
        </div>
      )}
      <div style={{ margin: "8px 0" }}><ModeChips value={mode} onChange={chooseMode} /></div>
      {job ? (
        <div className="progress" style={{ maxWidth: "none" }}>
          <div className="bar"><i style={{ width: `${Math.round(Math.max(0.05, job.progress || 0) * 100)}%` }} /></div>
          <div className="msg">{job.message}</div>
        </div>
      ) : (
        <div className="row">
          <button className="btn gold" disabled={prompt.trim().length < 5} onClick={() => create(false)}>🎬 Sukurti ir įterpti</button>
          <button className="btn" disabled={prompt.trim().length < 5} onClick={() => create(true)}>Sukurti kaip įrašą</button>
        </div>
      )}
    </div>
  );
}
