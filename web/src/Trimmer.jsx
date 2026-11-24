import React, { useEffect, useRef, useState } from "react";
import { api, fileUrl } from "./api.js";

// ✂ Įrašo karpymas kaip CapCut / Instagram: kadrų juosta, tempiamos pradžios / pabaigos rankenėlės,
// peržiūra tik pasirinktos dalies, padalinimas ties žymekliu.
const fmt = t => {
  const m = Math.floor(t / 60), s = (t % 60).toFixed(1);
  return `${m}:${s.padStart(4, "0")}`;
};

export default function Trimmer({ id, clip, onClose, onSaved, setError }) {
  const dur = clip.duration;
  const [a, setA] = useState(clip.trim ? clip.trim[0] : 0);
  const [b, setB] = useState(clip.trim ? clip.trim[1] : dur);
  const [t, setT] = useState(clip.trim ? clip.trim[0] : 0);
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [shown, setShown] = useState(false);   // video kadras jau matomas
  const [frameT, setFrameT] = useState(clip.trim ? clip.trim[0] : 0);
  const video = useRef(null);
  const bar = useRef(null);
  const drag = useRef(null);

  // Kol video kadras nematomas (iPhone neužkrauna video be paspaudimo), rodom kadro paveikslėlį
  useEffect(() => {
    if (shown) return;
    const h = setTimeout(() => setFrameT(Math.round(t * 10) / 10), 120);
    return () => clearTimeout(h);
  }, [t, shown]);

  function primed() {  // iPhone: tyliai paleidžiam ir sustabdom, kad parodytų kadrą
    const v = video.current;
    setReady(true);
    if (!v) return;
    v.muted = true;
    const p = v.play();
    const done = () => { v.pause(); v.muted = false; try { v.currentTime = a; } catch (e) { /* */ } };
    if (p && p.then) p.then(done).catch(() => { v.muted = false; }); else done();
  }

  // grojam tik pasirinktą dalį
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    const tick = () => {
      setT(v.currentTime);
      if (!v.paused && v.currentTime >= b) { v.pause(); v.currentTime = a; }
    };
    v.addEventListener("timeupdate", tick);
    return () => v.removeEventListener("timeupdate", tick);
  }, [a, b]);

  const pos = x => {
    const r = bar.current.getBoundingClientRect();
    return Math.max(0, Math.min(dur, ((x - r.left) / r.width) * dur));
  };
  function down(kind, e) {
    e.preventDefault();
    e.stopPropagation();
    drag.current = kind;
    e.currentTarget.setPointerCapture && e.currentTarget.setPointerCapture(e.pointerId);
  }
  function move(e) {
    if (!drag.current) return;
    const x = pos(e.clientX);
    const v = video.current;
    if (drag.current === "a") { const na = Math.min(x, b - 0.3); setA(na); if (v) v.currentTime = na; }
    else if (drag.current === "b") { const nb = Math.max(x, a + 0.3); setB(nb); if (v) v.currentTime = nb; }
    else if (v) { v.currentTime = x; }
    if (!v || !shown) setT(x);
  }
  const up = () => { drag.current = null; };

  function toggle() {
    const v = video.current;
    if (!v) return;
    if (v.paused) {
      if (v.currentTime < a || v.currentTime >= b - 0.05) v.currentTime = a;
      v.play();
      setPlaying(true);
    } else { v.pause(); setPlaying(false); }
  }

  async function save() {
    setBusy(true);
    try { onSaved(await api(`/projects/${id}/clips/${clip.id}/trim`, { method: "PUT", body: { start: a, end: b } })); onClose(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  async function split() {
    setBusy(true);
    try {
      await api(`/projects/${id}/clips/${clip.id}/trim`, { method: "PUT", body: { start: a, end: b } });
      onSaved(await api(`/projects/${id}/clips/${clip.id}/split`, { method: "POST", body: { at: t } }));
      onClose();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const pct = x => `${(x / dur) * 100}%`;
  const canSplit = t > a + 0.3 && t < b - 0.3;

  return (
    <div className="modal rec-modal" onPointerMove={move} onPointerUp={up}>
      <div className="rec-box">
        <div className="row" style={{ marginBottom: 10 }}>
          <h3 className="serif" style={{ margin: 0, fontSize: 22 }}>✂ Karpyti įrašą</h3>
          <span className="spacer" />
          <button className="btn small ghost" onClick={onClose}>✕</button>
        </div>
        <div className="trim-video">
          <video ref={video} src={fileUrl(`/projects/${id}/clips/${clip.id}/preview`)} playsInline preload="auto"
                 onLoadedMetadata={primed}
                 onLoadedData={() => { setReady(true); setShown(true); try { video.current.currentTime = a; } catch (e) { /* */ } }}
                 onPause={() => setPlaying(false)} onPlay={() => { setPlaying(true); setShown(true); }} onClick={toggle} />
          {!shown && <img className="trim-frame" alt="" onClick={toggle}
                          src={fileUrl(`/projects/${id}/clips/${clip.id}/frame`, `&t=${frameT}`)} />}
          {!ready && <div className="empty small-note">Ruošiama peržiūra…</div>}
        </div>

        <div className="trim-bar" ref={bar} onPointerDown={e => { drag.current = "t"; move(e); }}>
          <div className="trim-strip" style={{ backgroundImage: `url(${fileUrl(`/projects/${id}/clips/${clip.id}/strip`)})` }} />
          <div className="trim-dim" style={{ left: 0, width: pct(a) }} />
          <div className="trim-dim" style={{ left: pct(b), right: 0 }} />
          <div className="trim-sel" style={{ left: pct(a), width: `calc(${pct(b)} - ${pct(a)})` }}>
            <span className="trim-h l" onPointerDown={e => down("a", e)} />
            <span className="trim-h r" onPointerDown={e => down("b", e)} />
          </div>
          <div className="trim-head" style={{ left: pct(t) }} />
        </div>
        <div className="row" style={{ justifyContent: "space-between", fontSize: 13, color: "var(--muted)", margin: "6px 2px 10px" }}>
          <span>Pradžia {fmt(a)}</span><b style={{ color: "var(--text)" }}>Liks {(b - a).toFixed(1)} s</b><span>Pabaiga {fmt(b)}</span>
        </div>

        <div className="row" style={{ justifyContent: "center" }}>
          <button className="btn small" onClick={() => { const na = Math.min(t, b - 0.3); setA(na); }} title="Pradžia ties žymekliu">⟤ Pradžia čia</button>
          <button className="btn" onClick={toggle} disabled={!ready}>{playing ? "⏸" : "▶"}</button>
          <button className="btn small" onClick={() => { const nb = Math.max(t, a + 0.3); setB(nb); }} title="Pabaiga ties žymekliu">Pabaiga čia ⟥</button>
        </div>
        <div className="hint" style={{ textAlign: "center", margin: "8px 0" }}>
          Tempkite geltonas rankenėles arba spustelėkite juostoje. ✂ padalina įrašą ties žymekliu – gautas dalis galėsite perdėlioti ar ištrinti.
        </div>
        <div className="row">
          <button className="btn" onClick={split} disabled={busy || !canSplit}>✂ Padalinti ties {fmt(t)}</button>
          <span className="spacer" />
          <button className="btn ghost" onClick={() => { setA(0); setB(dur); }} disabled={busy}>Atstatyti</button>
          <button className="btn gold" onClick={save} disabled={busy}>{busy ? "…" : "Išsaugoti"}</button>
        </div>
      </div>
    </div>
  );
}
