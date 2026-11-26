import React, { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

// 💬 AI režisierius: klientas rašo, ką pakeisti – AI pats atlieka pakeitimus ir sukuria naują peržiūrą.
const IDEAS = [
  "Linksmiau, kaip TikTok – ryškūs titrai ir greitesnis tempas",
  "Elegantiškiau ir ramiau",
  "Kalėdinis stilius",
  "Padaryk kaip kino anonsą",
  "Sutrumpink iki 15 sekundžių",
  "Muziką parink energingesnę",
  "Pradžioje užrašas „-20 % iki penktadienio“",
  "Pabaigoje pakviesk rašyti žinutę",
];

export default function Director({ id, user, busyJob, onChanged, onAiScene, setError }) {
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [left, setLeft] = useState(null);
  const [props, setProps] = useState([]);
  const [open, setOpen] = useState(true);
  const box = useRef(null);
  const ok = !!user.ai;

  useEffect(() => {
    if (!ok) return;
    api(`/projects/${id}/director`).then(r => { setMsgs(r.messages || []); setLeft(r.left); }).catch(() => {});
  }, [id, ok]);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [msgs, busy]);

  async function send(m) {
    const message = (m ?? text).trim();
    if (!message || busy) return;
    setText("");
    setMsgs(x => [...x, { role: "user", text: message }]);
    setBusy(true);
    setProps([]);
    try {
      const r = await api(`/projects/${id}/director`, { method: "POST", body: { message } });
      setMsgs(x => [...x, { role: "assistant", text: r.reply }]);
      setLeft(r.left);
      setProps(r.proposals || []);
      if (r.preview) onChanged(r.project);
    } catch (e) {
      setMsgs(x => [...x, { role: "assistant", text: "⚠ " + e.message }]);
    } finally { setBusy(false); }
  }

  return (
    <div className="card section director">
      <div className="row" style={{ cursor: "pointer" }} onClick={() => setOpen(!open)}>
        <b>💬 AI režisierius</b>
        <span className="hint">parašykite, ką pakeisti – AI padarys pats</span>
        <span className="spacer" /><span className="hint">{open ? "▲" : "▼"}</span>
      </div>
      {open && (!ok ? (
        <p className="hint" style={{ marginTop: 10 }}>💬 Pataisymai paprastais žodžiais („sutrumpink“, „pakeisk muziką“, „padaryk kaip kino anonsą“) – Premium plane.</p>
      ) : (
        <div style={{ marginTop: 10 }}>
          <div className="dir-msgs" ref={box}>
            {!msgs.length && <div className="hint">Pvz.: „Antra scena nuobodi – įdėk ką nors gyvesnio“, „Titrus padaryk kaip kino anonse“, „Balsas tegul būna vyriškas“.</div>}
            {msgs.map((m, i) => <div key={i} className={"dir-msg " + m.role}>{m.text}</div>)}
            {busy && <div className="dir-msg assistant">🎬 Dirbu… (gali užtrukti iki minutės)</div>}
          </div>
          {props.map(p => (
            <div key={p.clip_id} className="dir-prop">
              <span>✨ Siūlau sukurti AI kadrą scenai „{p.name}“: <i>{p.prompt}</i></span>
              <button className="btn small gold" disabled={busyJob} onClick={() => { setProps([]); onAiScene(p.clip_id, p.prompt); }}>Sukurti AI kadrą</button>
            </div>
          ))}
          <div className="chips" style={{ margin: "8px 0" }}>
            {IDEAS.map(t => <button key={t} type="button" className="chip" disabled={busy || busyJob} onClick={() => send(t)}>{t}</button>)}
          </div>
          <form className="row" style={{ flexWrap: "nowrap", gap: 6 }} onSubmit={e => { e.preventDefault(); send(); }}>
            <input className="input" value={text} onChange={e => setText(e.target.value)} maxLength={1500}
                   placeholder="Ką pakeisti? Pvz.: muziką ramesnę, o titrus baltus" disabled={busy} />
            <button className="btn gold" disabled={busy || busyJob || !text.trim()}>{busy ? "…" : "Siųsti"}</button>
          </form>
          {left != null && <div className="hint" style={{ marginTop: 6 }}>Šį mėnesį liko {left} žinučių. Po pakeitimų peržiūra sukuriama automatiškai.</div>}
        </div>
      ))}
    </div>
  );
}
