import React, { useState } from "react";
import { api, fileUrl, waitJob } from "./api.js";

// 🎯 Efektai laiko juostoje: vartotojas pasirenka efektą ir vietą peržiūroje, pamato trumpą peržiūrą ir tik tada
// pritaiko. Kiekvieną efektą galima pašalinti atskirai.
export default function FxTimeline({ id, opts, s, set, hasPreview, getTime, seek, setError }) {
  const kinds = (opts.timeline_fx || []).filter(k => opts.gfx && opts.gfx[k]);
  const [kind, setKind] = useState(kinds[0] || "");
  const [t, setT] = useState(0);
  const [busy, setBusy] = useState(null);     // vykstantis peržiūros darbas
  const [prev, setPrev] = useState(null);     // {file, kind, t, text, v}
  const items = s.fx_items || [];
  const name = k => (opts.gfx && opts.gfx[k]) || k;

  function takeTime() {
    const x = getTime();
    if (x != null) setT(Math.round(x * 10) / 10);
  }

  async function preview() {
    setError("");
    setPrev(null);
    try {
      const j = await api(`/projects/${id}/fx_preview`, { method: "POST", body: { kind, t: +t } });
      setBusy(j);
      const done = await waitJob(j.id, setBusy);
      setPrev({ ...done.result, v: Date.now() });
    } catch (e) { setError(e.message); }
    finally { setBusy(null); }
  }

  function apply() {
    const it = { id: Math.random().toString(36).slice(2, 9), kind: prev.kind, t: prev.t };
    set({ fx_items: [...items, it].sort((a, b) => a.t - b.t) });
    setPrev(null);
  }

  function remove(it) {
    set({ fx_items: items.filter(x => x.id !== it.id) });
  }

  return (
    <div className="section card">
      <h3 style={{ marginTop: 0 }}>🎯 Efektai laiko juostoje</h3>
      <div className="hint" style={{ marginBottom: 8 }}>
        Sustabdykite peržiūrą norimoje vietoje, pasirinkite efektą ir pažiūrėkite, kaip jis atrodys – tik tada pritaikykite.
        {items.length > 0 && " Kai efektai sudėti čia, automatinis grafikos parinkimas nenaudojamas."}
      </div>
      {!hasPreview ? (
        <p className="hint">Pirmiausia sukurkite peržiūrą (▶ Peržiūra) – efektai dedami į jos laiko juostą.</p>
      ) : (
        <>
          <div className="row" style={{ gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <select className="input" style={{ maxWidth: 260 }} value={kind} onChange={e => { setKind(e.target.value); setPrev(null); }}
                    aria-label="Efektas">
              {kinds.map(k => <option key={k} value={k}>{name(k)}</option>)}
            </select>
            <label className="hint" htmlFor="fx-t">Vieta:</label>
            <input id="fx-t" className="input" type="number" min="0" step="0.1" value={t} style={{ width: 90 }}
                   onChange={e => { setT(e.target.value); setPrev(null); }} />
            <span className="hint">s</span>
            <button type="button" className="btn small" onClick={takeTime}>📍 Paimti vietą iš peržiūros</button>
          </div>
          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            <button type="button" className="btn small accent" disabled={!!busy || !kind} onClick={preview}>
              {busy ? `Ruošiama… ${Math.round((busy.progress || 0) * 100)}%` : "👁 Peržiūrėti efektą"}
            </button>
            {prev && <button type="button" className="btn small gold" onClick={apply}>✓ Pritaikyti</button>}
            {prev && <button type="button" className="btn small ghost" onClick={() => setPrev(null)}>Atšaukti</button>}
          </div>
          {prev && (
            <div style={{ marginTop: 8 }}>
              <video key={prev.v} src={fileUrl(`/projects/${id}/files/${prev.file}`, "&v=" + prev.v)} controls autoPlay playsInline
                     style={{ width: "100%", maxWidth: 240, borderRadius: 10, background: "#000" }} />
              <div className="hint">{name(prev.kind)} nuo {prev.t} s{prev.text ? ` · žodis „${prev.text}“` : ""}</div>
            </div>
          )}
        </>
      )}
      {items.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <b>Pritaikyti efektai</b>
          {items.map(it => (
            <div key={it.id} className="row" style={{ gap: 6, marginTop: 6, alignItems: "center" }}>
              <span style={{ flex: 1 }}>{name(it.kind)} · {it.t} s</span>
              {hasPreview && <button type="button" className="btn small ghost" onClick={() => seek(it.t)}>▶ Rodyti vietą</button>}
              <button type="button" className="btn small ghost danger" onClick={() => remove(it)}>✕ Pašalinti</button>
            </div>
          ))}
          <div className="hint" style={{ marginTop: 6 }}>Pakeitę efektus, sukurkite peržiūrą iš naujo – galutinis video bus toks pat kaip peržiūra.</div>
        </div>
      )}
    </div>
  );
}
