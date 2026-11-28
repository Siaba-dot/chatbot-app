import React, { useRef, useState } from "react";
import { api, fileUrl, waitJob } from "./api.js";

// ✨ 3D akcentai: pasiūlymai pagal klipo turinį (žodis / detalė / rezultatas), peržiūra vienu paspaudimu,
// kitas variantas, vietos, dydžio, spalvos, pradžios ir trukmės keitimas.

const CAT_LABEL = { word: "🔠 Pabrėžtas žodis", detail: "➡️ Rodoma detalė", reveal: "💥 Rezultatas" };
const ANCHOR = { arrow3d: 0.5, ring3d: 0.15, card3d: 0.12, glass3d: 0.35, flip3d: 0.12, blocks3d: 0.1, word3d: 0.06 };

export async function previewItem(id, item, onJob) {
  const j = await api(`/projects/${id}/fx_preview`, { method: "POST", body: { kind: item.kind, t: +item.t, item } });
  onJob && onJob(j);
  const done = await waitJob(j.id, onJob);
  return { ...done.result, v: Date.now() };
}

// kitas tos pačios grupės variantas – momentas (kada pasiekia detalę / keičiasi kadras) išlieka tas pats
export function nextVariant(item, acc) {
  const vs = acc.variants[acc.category[item.kind]] || [item.kind];
  return withKind(item, vs[(vs.indexOf(item.kind) + 1) % vs.length], acc);
}

export function withKind(item, kind, acc) {
  const durOld = +item.dur || acc.len[item.kind];
  const anchor = +item.t + (ANCHOR[item.kind] || 0) * durOld;
  const dur = acc.len[kind];
  return { ...item, kind, dur, t: Math.max(0, Math.round((anchor - (ANCHOR[kind] || 0) * dur) * 100) / 100) };
}

export function AccentEditor({ id, item, acc, previewSrc, onSave, onCancel, setError }) {
  const [it, setIt] = useState({ size: 1, dur: acc.len[item.kind], ...item });
  const [busy, setBusy] = useState(null);
  const [prev, setPrev] = useState(null);
  const vid = useRef(null);
  const upd = patch => { setIt(x => ({ ...x, ...patch })); setPrev(null); };
  const cat = acc.category[it.kind];
  const hasXY = cat !== "reveal" || it.kind === "glass3d";

  async function preview() {
    setError("");
    try { setPrev(await previewItem(id, it, setBusy)); } catch (e) { setError(e.message); } finally { setBusy(null); }
  }

  function pick(e) {
    const r = e.currentTarget.getBoundingClientRect();
    upd({ x: Math.round(((e.clientX - r.left) / r.width) * 1000) / 1000,
          y: Math.round(((e.clientY - r.top) / r.height) * 1000) / 1000 });
  }

  return (
    <div className="card" style={{ marginTop: 8, padding: 10 }}>
      <div className="row" style={{ gap: 6, flexWrap: "wrap", alignItems: "center" }}>
        <label className="hint" htmlFor="acc-kind">Variantas</label>
        <select id="acc-kind" className="input" style={{ maxWidth: 230 }} value={it.kind}
                onChange={e => upd(withKind(it, e.target.value, acc))}>
          {(acc.variants[cat] || [it.kind]).map(k => <option key={k} value={k}>{acc.kinds[k]}</option>)}
        </select>
      </div>
      <div className="row" style={{ gap: 10, flexWrap: "wrap", marginTop: 8 }}>
        <label className="hint">Pradžia, s
          <input className="input" type="number" min="0" step="0.05" value={it.t} style={{ width: 80, display: "block" }}
                 onChange={e => upd({ t: +e.target.value })} /></label>
        <label className="hint">Trukmė, s
          <input className="input" type="number" min="0.4" max="6" step="0.1" value={it.dur} style={{ width: 80, display: "block" }}
                 onChange={e => upd({ dur: +e.target.value })} /></label>
        <label className="hint">Spalva
          <input type="color" value={it.color || "#E9A23B"} style={{ display: "block", height: 34, width: 50 }}
                 onChange={e => upd({ color: e.target.value })} /></label>
        <label className="hint" style={{ minWidth: 150 }}>Dydis: {Math.round((it.size || 1) * 100)}%
          <input className="range" type="range" min="0.5" max="2" step="0.05" value={it.size || 1}
                 onChange={e => upd({ size: +e.target.value })} /></label>
        {(it.kind === "word3d" || it.kind === "card3d") && (
          <label className="hint">Tekstas
            <input className="input" maxLength={20} value={it.text || ""} style={{ width: 140, display: "block" }}
                   onChange={e => upd({ text: e.target.value })} /></label>
        )}
      </div>
      {hasXY && previewSrc && (
        <div style={{ marginTop: 8 }}>
          <div className="hint">Vieta – spustelėkite kadre{cat === "detail" ? " ant detalės, į kurią rodyti" : ""}:</div>
          <div style={{ position: "relative", width: 160, cursor: "crosshair", marginTop: 4 }} onClick={pick}>
            <video ref={vid} src={previewSrc} muted playsInline preload="auto" style={{ width: "100%", display: "block", borderRadius: 8 }}
                   onLoadedMetadata={e => { e.currentTarget.currentTime = (+it.t || 0) + (ANCHOR[it.kind] || 0.3) * (+it.dur || 1); }} />
            <span style={{ position: "absolute", left: `${(it.x ?? 0.5) * 100}%`, top: `${(it.y ?? 0.5) * 100}%`,
                           transform: "translate(-50%,-50%)", width: 16, height: 16, borderRadius: "50%",
                           border: "3px solid #fff", background: it.color || "#E9A23B", boxShadow: "0 0 0 2px rgba(0,0,0,.4)" }} />
          </div>
        </div>
      )}
      <div className="row" style={{ gap: 6, marginTop: 10, flexWrap: "wrap" }}>
        <button type="button" className="btn small accent" disabled={!!busy} onClick={preview}>
          {busy ? `Ruošiama… ${Math.round((busy.progress || 0) * 100)}%` : "👁 Peržiūrėti"}</button>
        <button type="button" className="btn small" onClick={() => upd(nextVariant(it, acc))}>🔄 Kitas variantas</button>
        <button type="button" className="btn small gold" onClick={() => onSave(it)}>✓ Išsaugoti</button>
        <button type="button" className="btn small ghost" onClick={onCancel}>Atšaukti</button>
      </div>
      {prev && (
        <video key={prev.v} src={fileUrl(`/projects/${id}/files/${prev.file}`, "&v=" + prev.v)} controls autoPlay playsInline
               style={{ width: "100%", maxWidth: 240, borderRadius: 10, background: "#000", marginTop: 8 }} />
      )}
    </div>
  );
}

export default function Accents3D({ id, opts, s, set, hasPreview, previewSrc, setError }) {
  const acc = opts.accents;
  const [busy, setBusy] = useState(null);
  const [sugs, setSugs] = useState(null);
  const [pv, setPv] = useState({});        // pasiūlymo id -> peržiūra / vykdomas darbas
  const [editing, setEditing] = useState(null);
  if (!acc) return null;
  const items = s.fx_items || [];

  async function suggest() {
    setError("");
    try {
      const j = await api(`/projects/${id}/accents/suggest`, { method: "POST" });
      setBusy(j);
      const done = await waitJob(j.id, setBusy);
      setSugs(done.result.suggestions || []);
    } catch (e) { setError(e.message); } finally { setBusy(null); }
  }

  async function preview(sg) {
    setError("");
    setPv(x => ({ ...x, [sg.id]: { busy: { progress: 0 } } }));
    try {
      const r = await previewItem(id, sg, j => setPv(x => ({ ...x, [sg.id]: { busy: j } })));
      setPv(x => ({ ...x, [sg.id]: { res: r } }));
    } catch (e) { setError(e.message); setPv(x => ({ ...x, [sg.id]: {} })); }
  }

  function apply(sg) {
    const { id: _id, why, variants, cat, ...rest } = sg;
    set({ fx_items: [...items, { ...rest, id: Math.random().toString(36).slice(2, 9) }].sort((a, b) => a.t - b.t) });
    setSugs(x => x.filter(y => y.id !== sg.id));
  }

  function replace(sg, next) {
    setSugs(x => x.map(y => (y.id === sg.id ? { ...next, id: sg.id, why: sg.why, cat: sg.cat, variants: sg.variants } : y)));
    setPv(x => ({ ...x, [sg.id]: {} }));
  }

  return (
    <div className="section card">
      <h3 style={{ marginTop: 0 }}>✨ 3D akcentai</h3>
      <div className="hint" style={{ marginBottom: 8 }}>
        Studija pažiūri į jūsų klipą ir pasiūlo tūrinių elementų tiksliai tuo metu, kai jie prasmingi:
        pabrėžtas žodis ar skaičius iškyla iš titrų, rodyklė, žiedas ar kortelė pasiekia rodomą detalę, o rezultatas
        atsiskleidžia kadrui keičiantis. Veidai, titrai ir veiksmas lieka matomi.
      </div>
      {!hasPreview ? (
        <p className="hint">Pirmiausia sukurkite peržiūrą (▶ Peržiūra) – akcentai parenkami pagal sumontuotą video.</p>
      ) : (
        <button type="button" className="btn accent" disabled={!!busy} onClick={suggest}>
          {busy ? `${busy.message || "Ieškau…"} ${Math.round((busy.progress || 0) * 100)}%` : sugs ? "🔄 Pasiūlyti iš naujo" : "✨ Pasiūlyti 3D akcentus"}
        </button>
      )}
      {sugs && sugs.length === 0 && <p className="hint">Tinkamų vietų nerasta – efektą galite pridėti ir patys žemiau.</p>}
      {sugs && sugs.map(sg => (
        <div key={sg.id} className="card" style={{ marginTop: 8, padding: 10 }}>
          <div><b>{CAT_LABEL[acc.category[sg.kind]] || ""}</b> · {acc.kinds[sg.kind]} · nuo {sg.t} s</div>
          <div className="hint">{sg.why}</div>
          {editing === sg.id ? (
            <AccentEditor id={id} item={sg} acc={acc} previewSrc={previewSrc} setError={setError}
              onCancel={() => setEditing(null)} onSave={it => { replace(sg, it); setEditing(null); }} />
          ) : (
            <div className="row" style={{ gap: 6, marginTop: 6, flexWrap: "wrap" }}>
              <button type="button" className="btn small accent" disabled={!!(pv[sg.id] || {}).busy} onClick={() => preview(sg)}>
                {(pv[sg.id] || {}).busy ? `Ruošiama… ${Math.round(((pv[sg.id].busy || {}).progress || 0) * 100)}%` : "👁 Peržiūrėti ant klipo"}</button>
              {(sg.variants || []).length > 1 && (
                <button type="button" className="btn small" onClick={() => replace(sg, nextVariant(sg, acc))}>🔄 Kitas variantas</button>
              )}
              <button type="button" className="btn small" onClick={() => setEditing(sg.id)}>✎ Keisti</button>
              <button type="button" className="btn small gold" onClick={() => apply(sg)}>✓ Pritaikyti</button>
              <button type="button" className="btn small ghost" onClick={() => setSugs(x => x.filter(y => y.id !== sg.id))}>✕</button>
            </div>
          )}
          {(pv[sg.id] || {}).res && editing !== sg.id && (
            <video key={pv[sg.id].res.v} src={fileUrl(`/projects/${id}/files/${pv[sg.id].res.file}`, "&v=" + pv[sg.id].res.v)}
                   controls autoPlay playsInline style={{ width: "100%", maxWidth: 240, borderRadius: 10, background: "#000", marginTop: 8 }} />
          )}
        </div>
      ))}
    </div>
  );
}
