import React, { useEffect, useState } from "react";
import VoiceOptions from "./VoiceOptions.jsx";
import { api, waitJob } from "./api.js";

// ✨ Scenarijus pagal verslo sritį: keli teksto variantai → sufleris, įgarsinimas arba automatinis video.
function load(k, d) { try { return localStorage.getItem(k) || d; } catch { return d; } }
function save(k, v) { try { localStorage.setItem(k, v); } catch { /* privatus langas */ } }

export default function ScriptGen({ id, user, opts, s, onPrompter, onVoice, onAutoDone, setError, setToast, setJob }) {
  const [o, setO] = useState(null);
  const [open, setOpen] = useState(() => load("sg_open", "1") === "1");
  const [sector, setSector] = useState(() => load("sg_sector", ""));
  // kas pasirinkta ir sugeneruota – išsaugoma šiam projektui (perjungus skiltį ar atnaujinus puslapį neprarandama)
  const mem = (() => { try { return JSON.parse(localStorage.getItem("sg_state_" + id) || "{}"); } catch { return {}; } })();
  const [goal, setGoal] = useState(mem.goal || "pristatymas");
  const [topic, setTopic] = useState(mem.topic || "");
  const [secs, setSecs] = useState(mem.secs || 30);
  const [vars, setVars] = useState(mem.vars || null);
  const [ai, setAi] = useState(!!mem.ai);
  const [offset, setOffset] = useState(mem.offset || 0);
  const [busy, setBusy] = useState("");
  const [mode, setMode] = useState(mem.mode || ((user.ai) ? "prompt" : "sector"));
  const [prompt, setPrompt] = useState(mem.prompt || "");
  const [plan, setPlan] = useState(mem.plan || null);
  const aiVoice = user.ai || user.gemini;
  // numatytas – natūralus lietuviškas Google balsas (OpenAI – tik jei pasirinktas sąmoningai arba Google nėra)
  const firstGoogle = Object.keys(opts.gemini_voices || {})[0];
  const projVoice = s.voiceover && s.voiceover.voice;
  const [voice, setVoice] = useState(() => mem.voice ||
    (user.gemini ? (projVoice && projVoice.startsWith("g:") ? projVoice : firstGoogle) : (user.ai ? "coral" : "none")));
  useEffect(() => {
    try { localStorage.setItem("sg_state_" + id, JSON.stringify({ goal, topic, secs, vars, ai, offset, voice, mode, prompt, plan })); }
    catch { /* privatus langas */ }
  }, [id, goal, topic, secs, vars, ai, offset, voice, mode, prompt, plan]);

  const [left, setLeft] = useState(user.auto_videos_left);
  const refreshLeft = () => api("/me").then(u => setLeft(u.auto_videos_left)).catch(() => {});
  useEffect(() => { api("/scripts/options").then(setO).catch(() => {}); refreshLeft(); }, []);  // eslint-disable-line
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

  async function makePlan() {
    setBusy("plan");
    try {
      const r = await api(`/projects/${id}/prompt_plan`, { method: "POST", body: { prompt } });
      setPlan({ ...r, orig: r.text });
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }

  function edit(i, text) {
    setVars(vars.map((v, k) => (k === i ? { ...v, text } : v)));
  }

  async function auto(v, sec = sector) {
    setBusy("auto");
    try {
      // tekstas pakeistas ranka – scenos sudaromos iš naujo pagal sakinius
      const scenes = v.text === v.orig ? v.scenes : [];
      const j = await api(`/projects/${id}/auto_video`, { method: "POST", body: {
        sector: sec || "kita", text: v.text, scenes, voice: aiVoice && voice !== "none" ? voice : null } });
      setJob && setJob(j);
      await waitJob(j.id, setJob || (() => {}));
      setJob && setJob(null);
      setToast("Vaizdai sudėti – kuriu peržiūrą 🎬");
      refreshLeft();
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
        <b>✨ Sukurti video su AI</b>
        <span className="hint">aprašykite video arba pasirinkite verslo sritį</span>
        <span className="spacer" /><span className="hint">{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <div style={{ marginTop: 12 }}>
          <div className="chips" style={{ marginBottom: 12 }}>
            <button type="button" className={"chip" + (mode === "prompt" ? " on" : "")} onClick={() => setMode("prompt")}>✨ Aprašykite video</button>
            <button type="button" className={"chip" + (mode === "sector" ? " on" : "")} onClick={() => setMode("sector")}>📋 Pagal verslo sritį</button>
          </div>
          {mode === "prompt" && (!user.ai ? (
            <p className="hint">✨ Video pagal jūsų aprašymą kuria AI – tai Premium funkcija. Pagrindiniame plane naudokite „📋 Pagal verslo sritį“.</p>
          ) : (
            <>
              <div className="field">
                <label>Aprašykite, kokio video norite – kaip ChatGPT</label>
                <textarea className="input" rows={4} maxLength={1500} value={prompt} onChange={e => setPrompt(e.target.value)}
                          placeholder="Pvz.: 30 s video mano kavinei Kaune: jaukus rytas, kava ir šilti croissant'ai, pakviesk į pusryčius savaitgalį. Nuotaika šilta, balsas moteriškas." />
              </div>
              <button className="btn accent" onClick={makePlan} disabled={!!busy || prompt.trim().length < 10}>
                {busy === "plan" ? "AI planuoja…" : plan ? "✨ Suplanuoti iš naujo" : "✨ Suplanuoti video"}</button>
              {plan && (
                <div className="card variant" style={{ marginTop: 14 }}>
                  <b>{plan.title || "Jūsų video"}</b>
                  <label className="hint" style={{ marginTop: 8 }}>Tekstas įgarsinimui (galite taisyti) · ~{Math.round(plan.text.split(/\s+/).length / 2.3)} s</label>
                  <textarea className="input" rows={5} value={plan.text} onChange={e => setPlan({ ...plan, text: e.target.value })} />
                  {plan.text === plan.orig && (
                    <div className="scenes">
                      {plan.scenes.map((sc, i) => (
                        <div key={i} className="scene"><b>{i + 1}.</b> {sc.text}<span className="hint"> 🎞 {sc.query}</span></div>
                      ))}
                    </div>
                  )}
                  {aiVoice && (
                    <div className="field" style={{ marginTop: 8 }}>
                      <label>Balsas{plan.voice === "female" ? " (siūlomas moteriškas)" : plan.voice === "male" ? " (siūlomas vyriškas)" : ""}</label>
                      <select className="input" value={voice} onChange={e => setVoice(e.target.value)}>
                        <VoiceOptions opts={opts} google={user.gemini} openai={user.ai} />
                        <option value="none">Be balso – tik titrai ir muzika</option>
                      </select>
                    </div>
                  )}
                  <div className="row" style={{ gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                    <button className="btn accent" onClick={() => auto(plan, plan.sector)} disabled={!!busy}>
                      {busy === "auto" ? "Kuriama…" : "🎬 Kurti video"}</button>
                    <button className="btn small" onClick={() => onPrompter(plan.text)} disabled={!!busy}>📜 Filmuosiu pati (sufleris)</button>
                  </div>
                  <div className="hint" style={{ marginTop: 8 }}>
                    Vaizdai parenkami iš nemokamos bibliotekos. Norite tikslesnio vaizdo? Po to prie scenos kadro spauskite
                    <b> ✨</b> – AI sukurs jį pagal aprašymą (naudoja AI kadrų limitą).
                    {left != null && <> Šį mėnesį dar galite sukurti <b>{left}</b> automatinių video.</>}
                  </div>
                </div>
              )}
            </>
          ))}
          {mode === "sector" && (<>
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
          <button className="btn accent" onClick={() => generate(false)} disabled={!!busy}>
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
                    <VoiceOptions opts={opts} google={user.gemini} openai={user.ai} />
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
                      <button className="btn small accent" onClick={() => auto(v)} disabled={!!busy}>
                        {busy === "auto" ? "Dėliojama…" : "🎬 Video automatiškai"}</button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="card" style={{ marginTop: 10, borderColor: "var(--amber)" }}>
                <b>Kaip gauti video?</b>
                <ol className="hint" style={{ fontSize: 13.5, paddingLeft: 18, margin: "6px 0 0" }}>
                  <li>Po patikusiu variantu spauskite <b>„🎬 Video automatiškai“</b> – studija parinks vaizdus{aiVoice ? ", sukurs balsą" : ""} ir parodys peržiūrą.</li>
                  <li>Peržiūrėkite kairėje. Jei patinka – spauskite <b>„KURTI VIDEO“</b> (galutinis video 3 formatais).</li>
                  <li>Turite savo video? Spauskite <b>„🎙 Į įgarsinimą“</b> arba <b>„📜 Į suflerį“</b> ir įkelkite ar nufilmuokite medžiagą žemiau.</li>
                </ol>
              </div>
              {left != null && (
                <div className="hint" style={{ marginTop: 8 }}>🎞 Šį mėnesį dar galite sukurti <b>{left}</b> automatinių video (įskaitant „Kiti vaizdai“).</div>
              )}
              <div className="hint" style={{ marginTop: 8 }}>
                🎬 Automatinis video kiekvienam sakiniui parenka tinkamą vaizdą, uždeda {aiVoice ? "balsą, " : ""}titrus ir muziką.
                Vaizdus vėliau galite pakeisti: pašalinti, perdėlioti ar pridėti savo nuotraukų ir video.
              </div>
            </>
          )}
          </>)}
        </div>
      )}
    </div>
  );
}
