import React, { useRef, useState } from "react";
import { api, fileUrl } from "./api.js";

// 🎙 AI įgarsinimas: tekstas -> balsas (OpenAI). Titrai daromi iš įgarsinimo.
function Switch({ on, onChange, title, desc, disabled }) {
  return (
    <div className="switch" onClick={() => !disabled && onChange(!on)} style={disabled ? { opacity: .5 } : {}}>
      <div className="txt"><b>{title}</b>{desc && <span>{desc}</span>}</div>
      <div className={"toggle" + (on ? " on" : "")} />
    </div>
  );
}

function VoiceList({ voices, vo, setVo, sample, playing }) {
  return (
    <div className="clips">
      {Object.entries(voices || {}).map(([v, label]) => (
        <div key={v} className="clip" style={{ cursor: "pointer", borderColor: vo.voice === v ? "var(--amber)" : undefined }}
             onClick={() => setVo({ voice: v })}>
          <div className="info"><b>{label}</b></div>
          <button className="btn small" onClick={e => { e.stopPropagation(); sample(v); }}>{playing === v ? "■" : "▶"}</button>
        </div>
      ))}
    </div>
  );
}

export default function Voice({ id, s, set, setS, opts, user, setToast, setError }) {
  const vo = s.voiceover || { on: false, text: "", voice: "coral" };
  const [topic, setTopic] = useState("");
  const [secs, setSecs] = useState(30);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState("");
  const audio = useRef(null);
  const words = vo.text.trim() ? vo.text.trim().split(/\s+/).length : 0;
  const setVo = patch => set({ voiceover: { ...vo, ...patch } });

  if (!user.ai && !user.gemini) {
    return (
      <div className="card section">
        <h3>🎙 AI įgarsinimas</h3>
        <p className="hint">Parašykite tekstą – natūralus AI balsas jį perskaitys, o titrai susidės patys. Galima kurti
          video net nefilmuojant savęs (pvz. su nemokamais video kadrais).</p>
        <p className="hint">{user.plan === "admin" ? "Įjunkite: „← Mano projektai“ → „🔑 OpenAI raktas“." : "Įgarsinimas – Premium plane."}</p>
      </div>
    );
  }

  async function write() {
    if (!topic.trim()) return;
    setBusy(true);
    try {
      const r = await api(`/projects/${id}/voice_text`, { method: "POST", body: { topic, seconds: secs } });
      setVo({ text: r.text, on: true });
      setToast("Tekstas parašytas ✍️");
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }

  function sample(v) {
    if (audio.current) audio.current.pause();
    if (playing === v) { setPlaying(""); return; }
    const a = new Audio(fileUrl(`/voice_sample/${encodeURIComponent(v)}`));
    audio.current = a;
    setPlaying(v);
    a.onended = () => setPlaying("");
    a.onerror = () => { setPlaying(""); setError("Pavyzdžio nepavyko paleisti"); };
    a.play().catch(() => setPlaying(""));
  }

  return (
    <>
      <div className="section card">
        <Switch on={vo.on} onChange={v => setVo({ on: v })} title="🎙 AI įgarsinimas"
                desc="Video skambės AI balsu; jūsų įrašo garsas patyla. Titrai – iš įgarsinimo. Nuotraukos rodomos tiek, kad tilptų visas įgarsinimas." />
      </div>

      <div className="section">
        <h3>✨ AI parašys tekstą</h3>
        <div className="row" style={{ flexWrap: "nowrap" }}>
          <input className="input" value={topic} onChange={e => setTopic(e.target.value)} placeholder="Apie ką video? Pvz.: 3 patarimai, kaip paruošti automobilį žiemai" />
          <button className="btn" onClick={write} disabled={busy || !topic.trim() || !user.ai}>{busy ? "Rašoma…" : "Parašyk"}</button>
        </div>
        <div className="chips" style={{ marginTop: 8 }}>
          {[15, 30, 45, 60].map(x => (
            <button key={x} type="button" className={"chip" + (secs === x ? " on" : "")} onClick={() => setSecs(x)}>~{x} s</button>
          ))}
        </div>
      </div>

      <div className="section">
        <h3>Įgarsinimo tekstas</h3>
        <textarea className="input" rows={6} value={vo.text} maxLength={4000}
                  onChange={e => setS({ ...s, voiceover: { ...vo, text: e.target.value } })}
                  onBlur={e => setVo({ text: e.target.value })}
                  placeholder="Įrašykite, ką turi pasakyti balsas. Skyrybos ženklai – natūralios pauzės." />
        <div className="hint">{words} žodž. · ~{Math.round(words / 2.3)} s</div>
      </div>

      <div className="section">
        <h3>Balsas</h3>
        <div className="hint" style={{ marginBottom: 8 }}>▶ – pasiklausykite (pirmą kartą pavyzdys kuriamas kelias sekundes).</div>
        {user.gemini ? (
          <>
            <div className="row" style={{ margin: "4px 0 8px" }}><b>🇱🇹 Google balsai</b><span className="pill">natūralus lietuviškas tarimas</span></div>
            <VoiceList voices={opts.gemini_voices} vo={vo} setVo={setVo} sample={sample} playing={playing} />
          </>
        ) : user.plan === "admin" ? (
          <div className="card" style={{ marginBottom: 12 }}>
            <b>🇱🇹 Nori natūralaus lietuviško balso (kaip NotebookLM)?</b>
            <div className="hint">„← Mano projektai“ → „🇱🇹 Google (Gemini) raktas“ – tada čia atsiras Google balsai.</div>
          </div>
        ) : null}
        {user.ai && (
          <>
            <div className="row" style={{ margin: "12px 0 8px" }}><b>OpenAI balsai</b>{user.gemini && <span className="hint">(lietuviškai – su akcentu)</span>}</div>
            <VoiceList voices={opts.voices} vo={vo} setVo={setVo} sample={sample} playing={playing} />
          </>
        )}
      </div>

      <div className="section card">
        <div className="field" style={{ marginBottom: 0 }}>
          <label>Jūsų įrašo garsas po įgarsinimu: {s.clip_gain}%</label>
          <input className="range" type="range" min="0" max="100" step="5" value={s.clip_gain}
                 onChange={e => setS({ ...s, clip_gain: +e.target.value })} onMouseUp={e => set({ clip_gain: +e.target.value })}
                 onTouchEnd={e => set({ clip_gain: +e.target.value })} />
          <div className="hint">0% – tik AI balsas ir muzika; 20% – lengvas fonas (pvz. gatvės, kavinės garsai).</div>
        </div>
      </div>
    </>
  );
}
