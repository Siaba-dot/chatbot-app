import React, { useState } from "react";
import { api, fileUrl, upload } from "./api.js";

// 🎵 Kadrui skirta muzika arba įgarsinimas – skamba tik per šį kadrą.
export default function ClipSound({ id, clip, opts, user, globalMusic, onClose, onSaved, setError }) {
  const cur = clip.sound || {};
  const [kind, setKind] = useState(cur.kind || "music");
  const [track, setTrack] = useState(cur.track || Object.keys(opts.music || {})[0] || "");
  const [text, setText] = useState(cur.text || "");
  const canGoogle = !!user.gemini, canOpenAI = !!user.ai;
  const [voice, setVoice] = useState(cur.voice || (canGoogle ? Object.keys(opts.gemini_voices || {})[0] : "coral"));
  const [volume, setVolume] = useState(cur.volume ?? (cur.kind === "voice" ? 100 : 60));
  const [orig, setOrig] = useState(cur.orig ?? (clip.audio === "speech" ? 100 : 30));
  const [busy, setBusy] = useState(false);
  const [saved, setSavedSound] = useState(cur.kind === "voice" ? cur : null);
  const clipLen = clip.image ? null : clip.trim ? clip.trim[1] - clip.trim[0] : clip.duration;
  const aiOk = canGoogle || canOpenAI;

  const [up, setUp] = useState(0);
  const [own, setOwn] = useState(cur.kind === "file" ? cur : null);
  async function uploadSound(file, voice) {
    if (!file) return;
    setUp(0.01);
    try {
      const p = await upload(`/projects/${id}/clips/${clip.id}/sound_upload`, file,
        { fields: { voice }, onProgress: x => setUp(Math.max(0.01, x)) });
      const c = p.clips.find(x => x.id === clip.id);
      setOwn(c && c.sound); setVolume(100); if (c && c.sound) setOrig(c.sound.orig);
      onSaved(p, voice ? "upvoice" : "upmusic");
    } catch (e) { setError(e.message); }
    finally { setUp(0); }
  }

  async function save(k = kind, close = false) {
    setBusy(true);
    try {
      const p = await api(`/projects/${id}/clips/${clip.id}/sound`, {
        method: "PUT", body: { kind: k, track, text, voice, volume: +volume, orig: +orig } });
      onSaved(p, k);
      const c = p.clips.find(x => x.id === clip.id);
      if (k === "voice" && c && c.sound && !close) setSavedSound(c.sound); else onClose();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  const voices = [
    ...(canGoogle ? Object.entries(opts.gemini_voices || {}) : []),
    ...(canOpenAI ? Object.entries(opts.voices || {}) : []),
  ];
  const slider = ({ label, value, set, max = 150 }) => (
    <div className="field"><label>{label}: {value}%</label>
      <input className="range" type="range" min="0" max={max} value={value} onChange={e => set(+e.target.value)} /></div>
  );

  return (
    <div className="modal" onClick={() => !busy && onClose()}>
      <div className="card" style={{ maxWidth: 520, width: "100%", maxHeight: "90vh", overflow: "auto" }} onClick={e => e.stopPropagation()}>
        <div className="row" style={{ marginBottom: 6 }}>
          <h3 className="serif" style={{ margin: 0, fontSize: 22 }}>🎵 Garsas šiam kadrui</h3>
          <span className="spacer" />
          <button className="btn small ghost" onClick={onClose}>✕</button>
        </div>
        <div className="hint" style={{ marginBottom: 10 }}>
          „{clip.name}“{clipLen ? ` · ${clipLen.toFixed(1)} s` : " · nuotrauka"}. Parinktas garsas skambės tik per šį kadrą.
        </div>
        <div className="chips" style={{ marginBottom: 12 }}>
          <button type="button" className={"chip" + (kind === "music" ? " on" : "")} onClick={() => setKind("music")}>🎵 Muzika</button>
          <button type="button" className={"chip" + (kind === "file" ? " on" : "")} onClick={() => setKind("file")}>⬆ Savas garsas</button>
          <button type="button" className={"chip" + (kind === "voice" ? " on" : "")} onClick={() => { setKind("voice"); if (cur.kind !== "voice") setOrig(clip.audio === "speech" ? 30 : 0); }}>🎙 Įgarsinimas</button>
        </div>

        {kind === "music" && (
          <>
            <div className="clips" style={{ marginBottom: 10 }}>
              {Object.entries(opts.music || {}).map(([name, desc]) => (
                <div key={name} className="clip" style={{ cursor: "pointer", borderColor: track === name ? "var(--amber)" : undefined }}
                     onClick={() => setTrack(name)}>
                  <div className="info"><b>{name}</b><span>{desc}</span></div>
                  <audio controls preload="none" src={"/api/music/" + encodeURIComponent(name)} style={{ height: 32, maxWidth: 150 }}
                         onClick={e => e.stopPropagation()} />
                </div>
              ))}
            </div>
            {slider({ label: "Muzikos garsumas", value: volume, set: setVolume, max: 100 })}
          </>
        )}

        {kind === "file" && (
          <>
            <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
              <label className="btn small">⬆ Įkelti muziką
                <input type="file" hidden accept="audio/*,video/mp4,video/quicktime,.mp3,.m4a,.wav,.aac,.ogg,.mp4,.mov"
                       onChange={e => { uploadSound(e.target.files[0], false); e.target.value = ""; }} /></label>
              <label className="btn small">🎙 Įkelti balso įrašą
                <input type="file" hidden accept="audio/*,video/mp4,video/quicktime,.mp3,.m4a,.wav,.aac,.ogg,.mp4,.mov"
                       onChange={e => { uploadSound(e.target.files[0], true); e.target.value = ""; }} /></label>
              {up > 0 && <span className="hint">Įkeliama {Math.round(up * 100)}%…</span>}
            </div>
            <div className="hint" style={{ marginBottom: 8 }}>MP3, M4A, WAV arba MP4 (paimamas garsas). Įkelkite tik tai, ką turite teisę naudoti.{clip.image ? " Su balso įrašu nuotrauka rodoma tiek, kiek trunka įrašas." : ""}</div>
            {own && (
              <div className="row" style={{ marginBottom: 8 }}>
                <audio controls src={fileUrl(`/projects/${id}/voiceover/${own.file}`)} style={{ height: 36, flex: 1 }} />
                <span className="hint">{own.voice ? "🎙" : "🎵"} {own.name} · {own.length} s</span>
              </div>
            )}
            {own && slider({ label: "Garsumas", value: volume, set: setVolume })}
          </>
        )}

        {kind === "voice" && (!aiOk ? (
          <p className="hint">🎙 AI įgarsinimas – Premium plane.</p>
        ) : (
          <>
            <div className="field"><label>Ką balsas pasakys per šį kadrą</label>
              <textarea className="input" rows={4} maxLength={1500} value={text} onChange={e => setText(e.target.value)}
                        placeholder="Pvz.: Štai mūsų naujasis salonas – ateikite ir įsitikinkite patys!" /></div>
            {clipLen && text.trim() && (
              <div className="hint" style={{ marginTop: -6, marginBottom: 8 }}>
                ≈ {(text.trim().split(/\s+/).length / 2.4).toFixed(0)} s kalbos{text.trim().split(/\s+/).length / 2.4 > clipLen + 0.5
                  ? ` – ilgiau nei kadras (${clipLen.toFixed(1)} s), pabaiga bus nukirsta. Sutrumpinkite tekstą.` : ""}
              </div>
            )}
            {clip.image && <div className="hint" style={{ marginTop: -6, marginBottom: 8 }}>Nuotrauka bus rodoma tiek, kiek trunka įgarsinimas.</div>}
            <div className="field"><label>Balsas</label>
              <select className="input" value={voice} onChange={e => setVoice(e.target.value)}>
                {voices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></div>
            {slider({ label: "Įgarsinimo garsumas", value: volume, set: setVolume })}
            {saved && saved.file && (
              <div className="row" style={{ margin: "4px 0 10px" }}>
                <audio controls src={fileUrl(`/projects/${id}/voiceover/${saved.file}`)} style={{ height: 36, flex: 1 }} />
                {saved.length && <span className="hint">{saved.length} s</span>}
              </div>
            )}
          </>
        ))}

        {!clip.image && clip.audio !== "none" && (kind === "music" || (kind === "file" && own) || (kind === "voice" && aiOk)) && (
          slider({ label: "Kadro originalus garsas (0 – nutildyti)", value: orig, set: setOrig })
        )}
        {kind === "music" && globalMusic && (
          <div className="hint" style={{ marginBottom: 8 }}>Visam video parinkta muzika „{globalMusic}“ skambės kartu – jei nenorite, išjunkite ją skiltyje „Muzika“.</div>
        )}

        <div className="row" style={{ marginTop: 8 }}>
          {cur.kind && <button className="btn ghost danger small" disabled={busy} onClick={() => save("none")}>Pašalinti garsą</button>}
          <span className="spacer" />
          {kind === "voice" && saved && saved.text === text.trim() && saved.voice === voice
            ? <button className="btn gold" disabled={busy} onClick={() => save("voice", true)}>{busy ? "Saugoma…" : "✓ Tinka – uždaryti"}</button>
            : <button className="btn gold" disabled={busy || (kind === "voice" && (!aiOk || !text.trim())) || (kind === "music" && !track) || (kind === "file" && !own)}
                      onClick={() => save()}>{busy ? (kind === "voice" ? "Kuriamas balsas…" : "Saugoma…") : kind === "voice" ? "🎙 Sukurti įgarsinimą" : "Išsaugoti"}</button>}
        </div>
      </div>
    </div>
  );
}
