import React, { useEffect, useRef, useState } from "react";
import { api, fileUrl, upload } from "./api.js";

// ✂ Įrašo karpymas kaip CapCut / Instagram: kadrų juosta, tempiamos pradžios / pabaigos rankenėlės,
// peržiūra tik pasirinktos dalies, padalinimas ties žymekliu.
const fmt = t => {
  const m = Math.floor(t / 60), s = (t % 60).toFixed(1);
  return `${m}:${s.padStart(4, "0")}`;
};

// muzikos nuotaikos filtrui (pagal pavadinimą)
const MOODS = {
  "Visos": null,
  "Ramios": ["pianinas", "lounge", "lo-fi", "romant", "spa", "akust", "kinemat"],
  "Energingos": ["energ", "house", "trap", "phonk", "reggaeton", "funk", "retro", "motyv"],
  "Šventinės": ["kalėd", "romant", "funk", "tropical"],
};

export default function Trimmer({ id, clip, onClose, onSaved, setError, opts, projLines, lineTexts, span,
                                  onSaveLines, onSoundSaved }) {
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
  const music = useRef(null);   // 🎵 parinktos muzikos peržiūra kartu su video
  const sample = useRef(null);  // perklausa sąraše
  const bar = useRef(null);
  const [snd, setSnd] = useState(clip.sound || null);
  const [picker, setPicker] = useState(false);
  const [q, setQ] = useState("");
  const [mood, setMood] = useState("Visos");
  const [pick, setPick] = useState(clip.sound && clip.sound.kind === "music" ? clip.sound.track : "");
  const [vol, setVol] = useState(clip.sound && clip.sound.kind === "music" ? clip.sound.volume ?? 60 : 60);
  const [orig, setOrig] = useState(clip.sound ? clip.sound.orig ?? 100 : (clip.audio === "speech" ? 100 : 30));
  const [playingSample, setPlayingSample] = useState("");
  const [texts, setTexts] = useState(lineTexts || (projLines || []).map(l => l[2]));
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

  const musicOn = snd && (snd.kind === "music" || snd.kind === "file");
  const sndSrc = !snd ? "" : snd.kind === "file" ? fileUrl(`/projects/${id}/voiceover/${snd.file}`)
    : "/api/music/" + encodeURIComponent(snd.track || "");
  const [upBusy, setUpBusy] = useState(0);
  async function uploadSound(file, voice) {
    if (!file) return;
    setUpBusy(0.01);
    try {
      const p = await upload(`/projects/${id}/clips/${clip.id}/sound_upload`, file,
        { fields: { voice }, onProgress: x => setUpBusy(Math.max(0.01, x)) });
      const c = p.clips.find(x => x.id === clip.id);
      setSnd((c && c.sound) || null);
      setPick(""); setVol(100);
      if (c && c.sound) setOrig(c.sound.orig);
      onSoundSaved && onSoundSaved(p, voice ? "upvoice" : "upmusic");
    } catch (e) { setError(e.message); }
    finally { setUpBusy(0); }
  }
  useEffect(() => {  // garsumai peržiūroje: muzika ir originalus kadro garsas
    if (video.current) video.current.volume = Math.min(1, (musicOn ? (snd.orig ?? 100) : 100) / 100);
    if (music.current && musicOn) music.current.volume = Math.min(1, (snd.volume ?? 60) / 100);
  }, [snd, musicOn]);
  function syncMusic(play) {
    const m = music.current, v = video.current;
    if (!m || !musicOn || !v) return;
    if (play) {
      try { m.currentTime = Math.max(0, v.currentTime - a) % (m.duration || 1e9); } catch (e) { /* */ }
      m.play().catch(() => {});
    } else m.pause();
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

  async function saveSound(kind) {
    setBusy(true);
    try {
      const p = await api(`/projects/${id}/clips/${clip.id}/sound`, {
        method: "PUT", body: { kind, track: pick, volume: +vol, orig: +orig } });
      const c = p.clips.find(x => x.id === clip.id);
      setSnd((c && c.sound) || null);
      if (sample.current) sample.current.pause();
      setPlayingSample(""); setPicker(false);
      onSoundSaved && onSoundSaved(p, kind);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  function playSample(name) {
    const el = sample.current;
    if (!el) return;
    if (playingSample === name) { el.pause(); setPlayingSample(""); return; }
    el.src = "/api/music/" + encodeURIComponent(name);
    el.play().catch(() => {});
    setPlayingSample(name);
  }

  // 💬 titrai, kurie patenka į šį kadrą (span – kadro vieta sumontuotame video)
  const base = clip.trim ? clip.trim[0] : 0;
  const mine = (projLines && span) ? projLines.map((l, i) => [l, i]).filter(([l]) => l[1] > span[0] + 0.05 && l[0] < span[1] - 0.05).map(([, i]) => i) : [];
  const et = span ? span[0] + (t - base) : -1;
  const cur = mine.find(i => projLines[i][0] <= et && et < projLines[i][1] + 0.1) ?? -1;
  function editLine(i, v) { const n = [...texts]; n[i] = v; setTexts(n); }
  function commitLine(i) {
    const was = lineTexts || (projLines || []).map(l => l[2]);
    if (texts[i] !== was[i]) onSaveLines && onSaveLines(texts);
  }

  const lib = Object.entries((opts && opts.music) || {}).filter(([n, d]) => {
    const hay = (n + " " + d).toLowerCase();
    const m = MOODS[mood];
    return (!q.trim() || hay.includes(q.trim().toLowerCase())) && (!m || m.some(k => hay.includes(k)));
  });

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
                 onPause={() => { setPlaying(false); syncMusic(false); }}
                 onPlay={() => { setPlaying(true); setShown(true); syncMusic(true); }} onClick={toggle} />
          {musicOn && <audio ref={music} src={sndSrc} preload="auto" />}
          {cur >= 0 && <div className="trim-sub">{texts[cur]}</div>}
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
        <div className="trim-lane">
          {snd && snd.kind === "voice" ? (
            <div className="lane-bar voice" style={{ left: pct(a), width: `calc(${pct(b)} - ${pct(a)})` }} title="Keičiama 🎵 mygtuku prie kadro">🎙 Įgarsinimas</div>
          ) : musicOn ? (
            <button className="lane-bar" style={{ left: pct(a), width: `calc(${pct(b)} - ${pct(a)})` }} onClick={() => setPicker(true)}>
              {snd.kind === "file" ? `${snd.voice ? "🎙" : "🎵"} ${snd.name}` : `🎵 ${snd.track}`}</button>
          ) : (
            <button className="lane-add" onClick={() => setPicker(true)}>＋ Pridėti muziką</button>
          )}
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
        <div className="trim-subs">
          <b>💬 Titrai šiame kadre</b>
          {mine.length ? mine.map(i => (
            <input key={i} className={"input" + (i === cur ? " now" : "")} value={texts[i] ?? ""}
                   onChange={e => editLine(i, e.target.value)} onBlur={() => commitLine(i)}
                   onFocus={() => { const v = video.current; if (v && span) { try { v.currentTime = Math.max(a, base + projLines[i][0] - span[0] + 0.05); } catch (e) { /* */ } } }} />
          )) : <div className="hint">{projLines ? "Šiame kadre titrų nėra." : "Titrai atsiras, kai juos paruošite: „💬 Titrai“ → „Paruošti titrus“ (arba spauskite „▶ Peržiūra“)."}</div>}
          {mine.length > 0 && <div className="hint">Pataisykite tekstą ir paspauskite už laukelio – išsaugoma iškart. Pakeitus apkarpymą, titrai paruošiami iš naujo.</div>}
        </div>
        {picker && (
          <div className="music-pick">
            <div className="row" style={{ marginBottom: 8 }}>
              <button className="btn small ghost" onClick={() => { setPicker(false); if (sample.current) sample.current.pause(); setPlayingSample(""); }}>←</button>
              <b style={{ fontSize: 17 }}>Muzika</b>
            </div>
            <div className="row" style={{ gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
              <label className="btn small">⬆ Įkelti savo muziką
                <input type="file" hidden accept="audio/*,video/mp4,video/quicktime,.mp3,.m4a,.wav,.aac,.ogg,.mp4,.mov"
                       onChange={e => { uploadSound(e.target.files[0], false); e.target.value = ""; }} /></label>
              <label className="btn small">🎙 Įkelti balso įrašą
                <input type="file" hidden accept="audio/*,video/mp4,video/quicktime,.mp3,.m4a,.wav,.aac,.ogg,.mp4,.mov"
                       onChange={e => { uploadSound(e.target.files[0], true); e.target.value = ""; }} /></label>
              {upBusy > 0 && <span className="hint">Įkeliama {Math.round(upBusy * 100)}%…</span>}
            </div>
            {snd && snd.kind === "file" && (
              <div className={"music-row" + (!pick ? " on" : "")} onClick={() => setPick("")} style={{ marginBottom: 6 }}>
                <div className="info"><b>{snd.voice ? "🎙" : "🎵"} {snd.name}</b><span>Jūsų įkeltas {snd.voice ? "balso įrašas" : "garsas"} · {snd.length} s</span></div>
              </div>
            )}
            <div className="hint" style={{ marginBottom: 6 }}>Įkelkite tik tokią muziką, kurią turite teisę naudoti. Tinka MP3, M4A, WAV ar MP4 (paimamas garsas).</div>
            <input className="input" value={q} onChange={e => setQ(e.target.value)} placeholder="🔍 Ieškoti studijos muzikos" />
            <div className="chips" style={{ margin: "8px 0" }}>{Object.keys(MOODS).map(m => (
              <button key={m} type="button" className={"chip" + (mood === m ? " on" : "")} onClick={() => setMood(m)}>{m}</button>))}</div>
            <div className="music-list">
              {lib.map(([name, desc]) => (
                <div key={name} className={"music-row" + (pick === name ? " on" : "")} onClick={() => setPick(name)}>
                  <div className="info"><b>{name}</b><span>{desc}</span></div>
                  <button className="play" onClick={e => { e.stopPropagation(); playSample(name); }}
                          aria-label="Perklausyti">{playingSample === name ? "■" : "▶"}</button>
                </div>
              ))}
              {!lib.length && <div className="hint" style={{ padding: 10 }}>Nieko nerasta.</div>}
            </div>
            <audio ref={sample} onEnded={() => setPlayingSample("")} />
            <div className="field" style={{ marginTop: 8 }}><label>Muzikos garsumas: {vol}%</label>
              <input className="range" type="range" min="0" max="100" value={vol} onChange={e => setVol(+e.target.value)} /></div>
            {clip.audio !== "none" && (
              <div className="field"><label>Kadro originalus garsas: {orig}%</label>
                <input className="range" type="range" min="0" max="150" value={orig} onChange={e => setOrig(+e.target.value)} /></div>
            )}
            <div className="row">
              {musicOn && <button className="btn ghost danger small" disabled={busy} onClick={() => saveSound("none")}>Pašalinti garsą</button>}
              <span className="spacer" />
              <button className="btn gold" disabled={busy || (!pick && !(snd && snd.kind === "file"))}
                      onClick={() => saveSound(pick ? "music" : "file")}>{busy ? "…" : "Atlikta"}</button>
            </div>
          </div>
        )}
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
