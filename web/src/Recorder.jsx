import React, { useEffect, useRef, useState } from "react";

// Filmavimas naršyklėje (kompiuterio ar telefono kamera) su sufleriu.
// Sufleris slenka pagal teksto ilgį (~1,8 žodžio/s); 🐢/🐇 – jūsų tempas (įsimenamas).
const WPS = 1.8;
const MAX_SECONDS = 600;

function load(key, def) {
  try { const v = localStorage.getItem(key); return v == null ? def : v; } catch { return def; }
}
function save(key, v) {
  try { localStorage.setItem(key, String(v)); } catch { /* privatus langas */ }
}
function pickMime() {
  const types = ["video/mp4;codecs=avc1,mp4a", "video/mp4", "video/webm;codecs=vp9,opus",
                 "video/webm;codecs=vp8,opus", "video/webm"];
  return types.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(t)) || "";
}

export default function Recorder({ projectId, onClose, onRecorded }) {
  const [stage, setStage] = useState("setup");       // setup | live | rec | review
  const [script, setScript] = useState(() => load("script_" + projectId, ""));
  const [facing, setFacing] = useState("user");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [secs, setSecs] = useState(0);
  const [rate, setRate] = useState(() => parseFloat(load("prompterRate", "1")) || 1);
  const [size, setSize] = useState(() => parseInt(load("prompterSize", "26"), 10) || 26);
  const [paused, setPaused] = useState(false);
  const [blobUrl, setBlobUrl] = useState("");
  const [sending, setSending] = useState(false);

  const video = useRef(null);
  const stream = useRef(null);
  const recorder = useRef(null);
  const chunks = useRef([]);
  const blob = useRef(null);
  const meter = useRef(null);
  const audioCtx = useRef(null);
  const box = useRef(null);
  const text = useRef(null);
  const off = useRef(0);
  const run = useRef(false);
  const timer = useRef(null);
  const st = useRef({ rate, paused });
  st.current = { rate, paused };

  useEffect(() => () => { stopAll(); }, []);  // uždarius – kamera išjungiama
  useEffect(() => save("script_" + projectId, script), [script, projectId]);

  function stopAll() {
    run.current = false;
    clearInterval(timer.current);
    if (recorder.current && recorder.current.state !== "inactive") {
      recorder.current.onstop = null;
      recorder.current.stop();
    }
    if (stream.current) stream.current.getTracks().forEach(t => t.stop());
    stream.current = null;
    if (audioCtx.current) { audioCtx.current.close(); audioCtx.current = null; }
  }

  function startMeter(s) {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      audioCtx.current = ctx;
      const an = ctx.createAnalyser();
      an.fftSize = 512;
      ctx.createMediaStreamSource(s).connect(an);
      const buf = new Uint8Array(an.fftSize);
      const tick = () => {
        if (audioCtx.current !== ctx) return;
        an.getByteTimeDomainData(buf);
        let peak = 0;
        for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
        if (meter.current) meter.current.style.width = Math.min(100, (peak / 128) * 250) + "%";
        requestAnimationFrame(tick);
      };
      tick();
    } catch { /* garso juostelė neprivaloma */ }
  }

  async function openCamera(face = facing) {
    setErr("");
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      setErr("Ši naršyklė neleidžia filmuoti. Atidarykite svetainę naujausioje Chrome, Edge arba Safari " +
             "(ne per Messenger ar Facebook) arba nufilmuokite telefonu ir įkelkite video.");
      return;
    }
    stopAll();
    setMsg("Laukiu leidimo naudoti kamerą ir mikrofoną…");
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: face, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      const denied = e && (e.name === "NotAllowedError" || e.name === "SecurityError");
      setErr(denied
        ? "Kamera ar mikrofonas neleisti. Naršyklės adreso juostoje spauskite 🔒 → leiskite kamerą ir mikrofoną, tada bandykite dar kartą."
        : "Nepavyko įjungti kameros: " + ((e && e.message) || e));
      setMsg("");
      return;
    }
    setStage("live");
    setMsg(stream.current.getAudioTracks().length
      ? (script.trim() ? "Pakalbėkite – juostelė turi judėti. Pradėjus filmuoti, tekstas slinks ramiu tempu."
                       : "Pakalbėkite – juostelė turi judėti. Tada spauskite „Pradėti filmuoti“.")
      : "⚠️ Mikrofonas nerastas – video bus be garso.");
    setTimeout(() => {
      if (video.current) { video.current.srcObject = stream.current; video.current.play().catch(() => {}); }
    }, 0);
    startMeter(stream.current);
    off.current = 0;
    render();
  }

  // ---------- sufleris ----------
  function render() {
    if (text.current) text.current.style.transform = `translateY(${-off.current}px)`;
  }
  function speed() {
    const words = Math.max(1, script.trim().split(/\s+/).length);
    const dist = Math.max(40, (text.current ? text.current.scrollHeight : 400) - (box.current ? box.current.clientHeight * 0.45 : 0));
    return dist / (words / WPS);
  }
  function promptStart() {
    run.current = true;
    let last = 0;
    const tick = ts => {
      if (!run.current) return;
      if (last && !st.current.paused) off.current += (speed() * st.current.rate * (ts - last)) / 1000;
      last = ts;
      render();
      requestAnimationFrame(tick);
    };
    setTimeout(() => run.current && requestAnimationFrame(tick), 2000);  // 2 s – spėsite perskaityti pirmą eilutę
  }
  function changeRate(d) {
    const r = Math.round(Math.max(0.3, Math.min(2.5, rate + d)) * 10) / 10;
    setRate(r);
    save("prompterRate", r);
  }
  function changeSize(d) {
    const v = Math.max(16, Math.min(44, size + d));
    setSize(v);
    save("prompterSize", v);
  }

  // ---------- įrašymas ----------
  function startRec() {
    chunks.current = [];
    const mime = pickMime();
    try {
      recorder.current = new MediaRecorder(stream.current, { videoBitsPerSecond: 2500000, ...(mime ? { mimeType: mime } : {}) });
    } catch (e) {
      setErr("Nepavyko pradėti filmuoti: " + e.message);
      return;
    }
    recorder.current.ondataavailable = e => e.data && e.data.size && chunks.current.push(e.data);
    recorder.current.onstop = finishRec;
    recorder.current.start(1000);
    const t0 = Date.now();
    setSecs(0);
    timer.current = setInterval(() => {
      const s = Math.floor((Date.now() - t0) / 1000);
      setSecs(s);
      if (s >= MAX_SECONDS) recorder.current.stop();
    }, 250);
    off.current = 0;
    setPaused(false);
    promptStart();
    setStage("rec");
    setMsg("");
  }
  function stopRec() {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
  }
  function finishRec() {
    clearInterval(timer.current);
    run.current = false;
    const type = (recorder.current && recorder.current.mimeType) || (chunks.current[0] && chunks.current[0].type) || "video/webm";
    blob.current = new Blob(chunks.current, { type });
    if (stream.current) stream.current.getTracks().forEach(t => t.stop());
    stream.current = null;
    if (audioCtx.current) { audioCtx.current.close(); audioCtx.current = null; }
    setBlobUrl(URL.createObjectURL(blob.current));
    setStage("review");
    setMsg("Peržiūrėkite įrašą. Jei tinka – spauskite „Pridėti šį įrašą“.");
  }
  async function use() {
    setSending(true);
    const ext = blob.current.type.includes("mp4") ? ".mp4" : ".webm";
    const stamp = new Date().toLocaleTimeString("lt-LT", { hour: "2-digit", minute: "2-digit" }).replace(":", "-");
    const file = new File([blob.current], `irasas_${stamp}${ext}`, { type: blob.current.type });
    try {
      await onRecorded(file, script.trim());
      onClose();
    } catch (e) {
      setErr(e.message);
      setSending(false);
    }
  }
  function flip() {
    const f = facing === "user" ? "environment" : "user";
    setFacing(f);
    openCamera(f);
  }

  const mm = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
  const showPrompt = script.trim() && (stage === "live" || stage === "rec");

  return (
    <div className="modal rec-modal">
      <div className="rec-box">
        <div className="row" style={{ marginBottom: 10 }}>
          <h3 className="serif" style={{ margin: 0, fontSize: 22 }}>🎥 Filmavimas</h3>
          <span className="spacer" />
          <button className="btn small ghost" onClick={() => { stopAll(); onClose(); }}>✕ Uždaryti</button>
        </div>

        {stage === "setup" && (
          <>
            <div className="field">
              <label>Sufleris – jūsų tekstas (nebūtina)</label>
              <textarea className="input" rows={6} value={script} onChange={e => setScript(e.target.value)}
                        placeholder="Įrašykite, ką norite pasakyti. Filmuojant tekstas lėtai slinks virš kameros – skaitykite žiūrėdami į objektyvą." />
              <div className="hint">{script.trim() ? `${script.trim().split(/\s+/).length} žodž. · ~${Math.round(script.trim().split(/\s+/).length / WPS)} s` : "Galite filmuoti ir be teksto."}</div>
            </div>
            <button className="btn gold block" onClick={() => openCamera()}>📷 Įjungti kamerą</button>
          </>
        )}

        {stage !== "setup" && (
          <div className="rec-stage">
            {stage === "review"
              ? <video className="rec-video" src={blobUrl} controls playsInline autoPlay />
              : <video ref={video} className={"rec-video" + (facing === "user" ? " mirror" : "")} muted playsInline autoPlay />}
            {showPrompt && (
              <div className="prompter" ref={box}>
                <div className="ptext" ref={text} style={{ fontSize: size }}>{script}</div>
              </div>
            )}
            {stage === "rec" && <div className="rec-dot">● {mm}</div>}
          </div>
        )}

        {showPrompt && (
          <div className="row pctl">
            <button className="btn small" onClick={() => changeRate(-0.1)} title="Lėčiau">🐢</button>
            <span className="hint">{rate.toFixed(1)}×</span>
            <button className="btn small" onClick={() => changeRate(0.1)} title="Greičiau">🐇</button>
            <button className="btn small" onClick={() => setPaused(p => !p)} title="Sustabdyti">{paused ? "▶" : "⏸"}</button>
            <button className="btn small" onClick={() => changeSize(-2)}>A−</button>
            <button className="btn small" onClick={() => changeSize(2)}>A+</button>
            <button className="btn small" onClick={() => { off.current = 0; render(); }} title="Į pradžią">⤒</button>
          </div>
        )}

        {(stage === "live" || stage === "rec") && (
          <div className="bar" style={{ height: 6, margin: "8px 0" }}><i ref={meter} style={{ width: 0, transition: "none" }} /></div>
        )}
        {msg && <div className="hint" style={{ margin: "6px 0" }}>{msg}</div>}
        {err && <div className="error">{err}</div>}

        <div className="row" style={{ marginTop: 8 }}>
          {stage === "live" && (
            <>
              <button className="btn" onClick={() => { stopAll(); setStage("setup"); }}>✍️ Tekstas</button>
              <button className="btn" onClick={flip}>🔄 Kita kamera</button>
              <span className="spacer" />
              <button className="btn gold" onClick={startRec}>● Pradėti filmuoti</button>
            </>
          )}
          {stage === "rec" && <button className="btn gold block" onClick={stopRec}>■ Baigti</button>}
          {stage === "review" && (
            <>
              <button className="btn" onClick={() => openCamera()} disabled={sending}>↩️ Filmuoti iš naujo</button>
              <span className="spacer" />
              <button className="btn gold" onClick={use} disabled={sending}>{sending ? "Įkeliama…" : "✓ Pridėti šį įrašą"}</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
