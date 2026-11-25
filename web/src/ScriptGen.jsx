import React, { useEffect, useState } from "react";
import { api, waitJob } from "./api.js";

// ✨ Scenarijus pagal verslo sritį: keli teksto variantai → sufleris, įgarsinimas arba automatinis video.
function load(k, d) { try { return localStorage.getItem(k) || d; } catch { return d; } }
function save(k, v) { try { localStorage.setItem(k, v); } catch { /* privatus langas */ } }

export default function ScriptGen({ id, user, opts, s, onPrompter, onVoice, onAutoDone, setError, setToast, setJob }) {
  const [o, setO] = useState(null);
  const [open, setOpen] = useState(() => load("sg_open", "1") === "1");
  const [sector, setSector] = useState(() => load("sg_sector", ""));
  const [goal, setGoal] = useState("pristatymas");
  const [topic, setTopic] = useState("");
  const [secs, setSecs] = useState(30);
  const [vars, setVars] = useState(null);
  const [ai, setAi] = useState(false);
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState("");
  const aiVoice = user.ai || user.gemini;
  const [voice, setVoice] = useState(() => (s.voiceover && s.voiceover.voice) ||
    (user.gemini ? Object.keys(opts.gemini_voices || {})[0] : "coral"));

  useEffect(() => { api("/scripts/options").then(setO).catch(() => {}); }, []);
  useEffect(() => save("sg_open", open ? "1" : "0"), [open]);
  useEffect(() => { if (sector) save("sg_sector", sector); }, [sector]);

  async function generate(more = false) {
    if (!sector) { setError("Pasirinkite verslo sritį."); return; }
    setBusy("gen");
    try {
      const off = more ? offset + 3 : 0;
      const r = await api(`/projects/${id}/scripts`, { method: "POST", body: {
        sector, goal, topic, seconds: secs, offset: off, avoid: more && vars ? vars.map(v => v.title) : [] } });
      setVars(r.variants.map(v => ({ ...v, orig: v.text })));
      setAi(r.ai);
      setOffset(off);
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }

  function edit(i, text) {
    setVars(vars.map((v, k) => (k === i ? { ...v, text } : v)));
  }

  async function auto(v) {
    setBusy("auto");
    try {
      // tekstas pakeistas ranka – scenos sudaromos iš naujo pagal sakinius
      const scenes = v.text === v.orig ? v.scenes : [];
      const j = await api(`/projects/${id}/auto_video`, { method: "POST", body: {
        sector, text: v.text, scenes, voice: aiVoice && voice !== "none" ? voice : null } });
      setJob && setJob(j);
      await waitJob(j.id, setJob || (() => {}));
      setJob && setJob(null);
      setToast("Vaizdai sudėti – kuriu peržiūrą 🎬");
      onAutoDone();
    } catch (e) { setJob && setJob(null); setError(e.message); }
    finally { setBusy(""); }
  }

  if (!o) return null;
  const voices = [
    ...(user.gemini ? Object.entries(opts.gemini_voices || {}) : []),
    ...(user.ai ? Object.entries(opts.voices || {}) : []),
  ];
  return (
    <div className="card section">
      <div className="row" style={{ cursor: "pointer" }} onClick={() => setOpen(!open)}>
        <b>✨ Scenarijus pagal verslo sritį</b>
        <span className="hint">tekstas sufleriui, įgarsinimui arba visas video automatiškai</span>
        <span className="spacer" /><span className="hint">{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={{ marginTop: 12 }}>
          <div className="field">
            <label>Verslo sritis</label>
            <select className="input" value={sector} onChange={e => setSector(e.target.value)}>
              <option value="">– Pasirinkite –</option>
              {Object.entries(o.sectors).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div className="field">
            <label>Ko norite?</label>
            <div className="chips">{Object.entries(o.goals).map(([k, l]) => (
              <button key={k} type="button" className={"chip" + (goal === k ? " on" : "")} onClick={() => setGoal(k)}>{l}</button>))}</div>
          </div>
          <div className="field">
            <label>Apie ką? (nebūtina)</label>
            <input className="input" value={topic} maxLength={300} onChange={e => setTopic(e.target.value)}
                   placeholder="Pvz.: -20 % dažymui iki gruodžio 15 d., Vilnius" />
          </div>
          <div className="field">
            <label>Trukmė</label>
            <div className="chips">{o.lengths.map(n => (
              <button key={n} type="button" className={"chip" + (secs === n ? " on" : "")} onClick={() => setSecs(n)}>~{n} s</button>))}</div>
          </div>
          <button className="btn gold" onClick={() => generate(false)} disabled={!!busy}>
            {busy === "gen" ? "Rašoma…" : "✨ Sukurti 3 variantus"}</button>
          {!user.ai && <div className="hint" style={{ marginTop: 6 }}>Pagrindiniame plane – paruošti šablonai. Premium plane tekstus kiekvieną kartą naujai parašo AI.</div>}

          {vars && (
            <>
              <div className="row" style={{ margin: "16px 0 8px" }}>
                <b>Variantai {ai ? "(parašė AI)" : "(iš šablonų)"}</b>
                <span className="spacer" />
                <button className="btn small" onClick={() => generate(true)} disabled={!!busy}>🔄 Kiti variantai</button>
              </div>
              {aiVoice && (
                <div className="field">
                  <label>Balsas automatiniam video</label>
                  <select className="input" value={voice} onChange={e => setVoice(e.target.value)}>
                    {voices.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                    <option value="none">Be balso – tik titrai ir muzika</option>
                  </select>
                </div>
              )}
              <div className="variants">
                {vars.map((v, i) => (
                  <div className="card variant" key={i}>
                    <div className="hint" style={{ marginBottom: 4 }}>{i + 1} variantas · ~{Math.round(v.text.split(/\s+/).length / 2.3)} s</div>
                    <textarea className="input" rows={6} value={v.text} onChange={e => edit(i, e.target.value)} />
                    {v.text === v.orig && v.scenes && (
                      <div className="hint" style={{ margin: "6px 0" }}>🎞 Vaizdai: {v.scenes.map(sc => sc.query).join(" · ")}</div>
                    )}
                    <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                      <button className="btn small" onClick={() => onPrompter(v.text)} disabled={!!busy}>📜 Į suflerį ir filmuoti</button>
                      {aiVoice && <button className="btn small" onClick={() => onVoice(v.text, voice !== "none" ? voice : null)} disabled={!!busy}>🎙 Į įgarsinimą</button>}
                      <button className="btn small gold" onClick={() => auto(v)} disabled={!!busy}>
                        {busy === "auto" ? "Dėliojama…" : "🎬 Video automatiškai"}</button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="hint" style={{ marginTop: 8 }}>
                🎬 Automatinis video kiekvienam sakiniui parenka tinkamą vaizdą, uždeda {aiVoice ? "balsą, " : ""}titrus ir muziką.
                Vaizdus vėliau galite pakeisti: pašalinti, perdėlioti ar pridėti savo nuotraukų ir video.
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
