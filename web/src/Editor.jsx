import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, fileUrl, upload, waitJob } from "./api.js";
import Recorder from "./Recorder.jsx";
import Broll from "./Broll.jsx";
import Voice from "./Voice.jsx";
import Trimmer from "./Trimmer.jsx";
import ClipSound from "./ClipSound.jsx";
import ScriptGen from "./ScriptGen.jsx";
import Director from "./Director.jsx";

const TABS = [
  ["media", "🎬 Medžiaga"], ["style", "🎨 Stilius"], ["subs", "💬 Titrai"], ["texts", "✍️ Tekstai"],
  ["broll", "🎞 Intarpai"], ["voice", "🎙 Įgarsinimas"], ["anims", "✨ Animacijos ir grafika"], ["sound", "🎵 Garsas"],
  ["pace", "⏱ Tempas"],
];
// Bendrinis / tuščias pavadinimas – rodom pasiūlymą įrašyti savo (o ne „Naujas Reels“)
const GENERIC_TITLE = /^\s*(naujas reels|be pavadinimo|untitled)?\s*$/i;
// Įrankiai sugrupuoti: vienu metu matoma 4 grupės ir tik pasirinktos grupės skirtukai (ne 9 iš karto)
const GROUPS = [
  ["media", "🎬 Medžiaga", ["media"]],
  ["look", "🎨 Išvaizda", ["style", "subs", "anims"]],
  ["sound", "🎙 Garsas", ["voice", "sound", "texts"]],
  ["edit", "✂ Montažas", ["broll", "pace"]],
];
const TAB_LABEL = Object.fromEntries(TABS);
const groupOf = t => (GROUPS.find(g => g[2].includes(t)) || GROUPS[0]);
const PHONE = { "9:16": "", "16:9": "f169", "1:1": "f11", "4:5": "f45" };

function Tile({ src, label, on, onClick, multi, small }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <button className={"tile" + (on ? " on" : "")} onClick={onClick} title={label} type="button">
      <div className="img">
        {!loaded && <div className="shimmer" />}
        <img src={src} alt="" loading="lazy" onLoad={() => setLoaded(true)} style={{ opacity: loaded ? 1 : 0 }} />
        {multi && <span className="tick">✓</span>}
      </div>
      <div className="name">{label}</div>
    </button>
  );
}

function Switch({ on, onChange, title, desc, disabled }) {
  return (
    <div className="switch" onClick={() => !disabled && onChange(!on)} style={disabled ? { opacity: .5 } : {}}>
      <div className="txt"><b>{title}</b>{desc && <span>{desc}</span>}</div>
      <div className={"toggle" + (on ? " on" : "")} />
    </div>
  );
}

function Chips({ items, value, onChange }) {
  return (
    <div className="chips">
      {items.map(([k, label]) => (
        <button key={k} type="button" className={"chip" + (value === k ? " on" : "")} onClick={() => onChange(k)}>
          {label}
        </button>
      ))}
    </div>
  );
}

function fmtTime(t) {
  const m = Math.floor(t / 60), s = Math.floor(t % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

// 📲 Ar naršyklė moka dalintis video failu (telefonuose – taip; daugumoje kompiuterių – ne)
// 💻 Kompiuteryje – tiesioginės nuorodos į platformų įkėlimo puslapius (ir kuris formatas joms tinka)
const PUBLISH = [
  ["Instagram", "https://www.instagram.com/", "9:16"],
  ["TikTok", "https://www.tiktok.com/upload", "9:16"],
  ["Facebook", "https://www.facebook.com/reels/create", "9:16"],
  ["YouTube Shorts", "https://studio.youtube.com/", "9:16"],
  ["YouTube (16:9)", "https://studio.youtube.com/", "16:9"],
];

// Telefone „Dalintis“ rodomas visada; jei naršyklė neleidžia dalintis failu (pvz. Instagram / Facebook vidinė
// naršyklė) – video atsisiunčiamas ir paaiškinama, ką daryti toliau.
const CAN_SHARE = (() => {
  try {
    return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent + (navigator.maxTouchPoints > 1 ? " iPad" : ""));
  } catch (e) { return false; }
})();

// 🧊 3D efektai rodomi atskirame bloke
const FX3D = ["gold3d", "shatter3d", "phone3d", "laptop3d", "frame3d"];

export default function Editor({ id, user }) {
  const [proj, setProj] = useState(null);
  const [opts, setOpts] = useState(null);
  const [s, setS] = useState(null);           // nustatymai (vietinė kopija)
  const [saved, setSaved] = useState(0);      // išsaugojimų skaitiklis – plytelių atnaujinimui
  const [tab, setTab] = useState("media");
  const [cat, setCat] = useState("Visi");
  const [job, setJob] = useState(null);
  const [uploads, setUploads] = useState([]);
  const [error, setError] = useState("");
  const [show, setShow] = useState("live");   // live | preview | final
  const [toast, setToast] = useState("");
  const [lines, setLines] = useState(null);
  const saveTimer = useRef(null);
  const fileInput = useRef(null);
  const camInput = useRef(null);
  const [over, setOver] = useState(false);
  const [recording, setRecording] = useState(false);
  const [trimming, setTrimming] = useState(null);  // karpomas įrašas
  const [sounding, setSounding] = useState(null);  // kadras, kuriam renkamas garsas
  const shareBlobs = useRef({});                    // 📲 dalinimuisi paruošti video failai
  const [sharing, setSharing] = useState("");
  const [autoplay, setAutoplay] = useState(false);  // groti tik ką tik sukurtą peržiūrą

  useEffect(() => {
    Promise.all([api("/projects/" + id), api("/options")]).then(([p, o]) => {
      setProj(p);
      setS(p.settings);
      setOpts(o);
      setLines(p.line_texts || (p.lines || []).map(l => l[2]));
      if (p.outputs && p.outputs.final) setShow("final");
      if (!p.clips.length) setTab("media");
    }).catch(e => setError(e.message));
  }, [id]);

  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(""), 2600); return () => clearTimeout(t); } }, [toast]);

  // ---------- nustatymai: keičiam vietoje, į serverį – po akimirkos ----------
  function set(patch) {
    setS(prev => {
      const next = { ...prev, ...patch };
      clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(async () => {
        try {
          const p = await api(`/projects/${id}/settings`, { method: "PUT", body: { settings: patch } });
          setProj(p);
          if (!p.prepared) setLines(null);
          setSaved(n => n + 1);
        } catch (e) { setError(e.message); }
      }, 450);
      return next;
    });
    setShow("live");
  }
  const setAnim = (k, v) => set({ anims: { ...s.anims, [k]: v } });

  async function rename(title) {
    if (!title.trim() || title === proj.title) return;
    const p = await api(`/projects/${id}/settings`, { method: "PUT", body: { settings: {}, title } });
    setProj(p);
    setToast("Pavadinimas išsaugotas ✓");
  }

  async function removeProject() {
    if (!window.confirm(`Ištrinti „${proj.title}“? Video ir įrašai bus pašalinti.`)) return;
    await api("/projects/" + id, { method: "DELETE" });
    window.location.hash = "";
  }

  // ---------- medžiaga ----------
  async function addFiles(files, recorded = false) {
    setError("");  // sena klaida nebeaktuali
    for (const f of files) {
      const key = Math.random().toString(36).slice(2);
      setUploads(u => [...u, { key, name: f.name, p: 0 }]);
      try {
        const p = await upload(`/projects/${id}/clips`, f, {
          recorded, onProgress: x => setUploads(u => u.map(o => (o.key === key ? { ...o, p: x } : o))),
        });
        setProj(p);
        setLines(null);
        setSaved(n => n + 1);
      } catch (e) {
        setError(`„${f.name}“: ${e.message}`);
      } finally {
        setUploads(u => u.filter(o => o.key !== key));
      }
    }
  }
  async function onRecorded(file, script) {
    await addFiles([file], true);
    if (script && !s.subtitle_text) set({ subtitle_text: script });  // be AI – titrai iš suflerio teksto
  }
  async function removeClip(cid) {
    setProj(await api(`/projects/${id}/clips/${cid}`, { method: "DELETE" }));
    setLines(null);
    setSaved(n => n + 1);
  }
  async function move(i, d) {
    const order = proj.clips.map(c => c.id);
    const j = i + d;
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j], order[i]];
    setProj(await api(`/projects/${id}/clips/order`, { method: "PUT", body: { order } }));
    setLines(null);
  }

  // ---------- darbai ----------
  async function run(kind, settingsNow) {
    setError("");
    try {
      if (kind === "prepare") {
        setAutoplay(false);
        const j = await api(`/projects/${id}/prepare`, { method: "POST" });
        setJob(j);
        const done = await waitJob(j.id, setJob);
        const r = done.result || {};
        setToast(r.note || `Titrai paruošti: ${(r.words || []).length} žodž. ✓`);
        setTab("subs");
      } else {
        await api(`/projects/${id}/settings`, { method: "PUT", body: { settings: settingsNow || s } });
        const j = await api(`/projects/${id}/render`, { method: "POST", body: { quick: kind === "preview" } });
        setJob(j);
        await waitJob(j.id, setJob);
        setAutoplay(kind === "preview");
        setShow(kind === "preview" ? "preview" : "final");
        if (kind === "final") setToast("Video paruoštas! 🎉");
      }
      const p = await api("/projects/" + id);
      setProj(p);
      setLines(p.line_texts || (p.lines || []).map(l => l[2]));
    } catch (e) {
      if (e.status === 499) setToast("Sustabdyta ■");
      else setError(e.message);
    } finally {
      setJob(null);
    }
  }

  async function afterAuto() {
    const p = await api("/projects/" + id);
    setProj(p); setS(p.settings); setLines(null);
    run("preview", p.settings);
  }

  async function autoFromText(text, voice) {  // 🎙 įgarsinimo tekstas -> automatiškai parinkti vaizdai
    setError("");
    try {
      await api(`/projects/${id}/settings`, { method: "PUT", body: { settings: s } });
      let sector = "kita";
      try { sector = localStorage.getItem("sg_sector") || "kita"; } catch (e) { /* */ }
      const j = await api(`/projects/${id}/auto_video`, { method: "POST", body: { sector, text, scenes: [], voice } });
      setJob(j);
      await waitJob(j.id, setJob);
      setJob(null);
      setToast("Vaizdai sudėti – kuriu peržiūrą 🎬");
      afterAuto();
    } catch (e) { setJob(null); setError(e.message); }
  }

  async function aiScene(c, promptOverride) {  // ✨ scenos vaizdas -> AI sukurtas kadras (Google Veo)
    const left = user.ai_clips_left;
    if (!window.confirm(`AI sukurs šios scenos vaizdą pagal aprašymą (užtrunka 1–3 min., kadras iki 4 s).\n` +
      `Bus panaudotas 1 AI kadras${left != null ? ` (šį mėnesį liko ${left})` : ""}. Tęsti?`)) return;
    setError("");
    try {
      const j = await api(`/projects/${id}/broll/veo`, { method: "POST", body: {
        prompt: promptOverride || c.visual || c.scene || c.query || c.name, replace: c.id } });
      setJob(j);
      await waitJob(j.id, setJob);
      setJob(null);
      setToast("AI kadras sukurtas ✨ – kuriu peržiūrą");
      afterAuto();
    } catch (e) { setJob(null); setError(e.message); }
  }

  async function reshuffle() {  // 🔄 kiti vaizdai tam pačiam tekstui
    setError("");
    try {
      const j = await api(`/projects/${id}/auto_video/reshuffle`, { method: "POST" });
      setJob(j);
      await waitJob(j.id, setJob);
      setJob(null);
      setToast("Parinkti kiti vaizdai – kuriu peržiūrą 🎬");
      afterAuto();
    } catch (e) { setJob(null); setError(e.message); }
  }

  async function stopJob() {
    if (!job) return;
    try { setJob(await api(`/jobs/${job.id}/cancel`, { method: "POST" })); } catch (e) { setError(e.message); }
  }

  async function saveLines(next) {
    setLines(next);
    try { setProj(await api(`/projects/${id}/lines`, { method: "PUT", body: { lines: next } })); }
    catch (e) { setError(e.message); }
  }

  const live = useMemo(() => fileUrl(`/projects/${id}/tile/live`, "&v=" + saved), [id, saved]);
  if (error && !proj) return <div className="page"><div className="error">{error}</div></div>;
  const out0 = (proj && proj.outputs) || {};
  const finalAt = out0.final && out0.final.at;
  useEffect(() => {  // telefone iš anksto parsisiunčiam pagrindinį video – kad „Dalintis“ atsidarytų iškart
    if (!finalAt || !CAN_SHARE || !navigator.share) return;
    const f = (out0.final.formats || [{ file: "reels.mp4" }])[0];
    prefetch(f.file, finalAt).catch(() => {});
  }, [finalAt]);  // eslint-disable-line

  async function prefetch(file, at) {
    const k = file + "@" + at;
    if (!shareBlobs.current[k]) {
      shareBlobs.current[k] = fetch(fileUrl(`/projects/${id}/files/${file}`, "&v=" + at))
        .then(r => { if (!r.ok) throw new Error("Nepavyko gauti video"); return r.blob(); })
        .then(b => new File([b], `${(proj.title || "reels").replace(/[^\wąčęėįšųūž -]/gi, "").trim() || "reels"}.mp4`, { type: "video/mp4" }));
      shareBlobs.current[k].catch(() => { delete shareBlobs.current[k]; });
    }
    return shareBlobs.current[k];
  }

  function publishTo(url, fmt) {  // 💻 kompiuteryje: atsisiųsti + nukopijuoti aprašymą + atidaryti įkėlimo puslapį
    window.open(url, "_blank", "noopener");
    const fs = out0.final.formats || [{ fmt: s.format, file: "reels.mp4" }];
    const f = fs.find(x => x.fmt === fmt) || fs[0];
    const a = document.createElement("a");
    a.href = fileUrl(`/projects/${id}/files/${f.file}`, "&download=1");
    document.body.appendChild(a); a.click(); a.remove();
    const cap = out0.final.caption;
    if (cap && navigator.clipboard) navigator.clipboard.writeText(cap.caption + "\n\n" + (cap.hashtags || []).join(" ")).catch(() => {});
    setToast(`Video ${f.fmt} atsisiunčiamas, aprašymas nukopijuotas 📋`);
  }

  async function shareVideo(f) {
    const cap = out0.final.caption;
    if (cap && navigator.clipboard) {  // aprašymą nukopijuojam – programėlėje tereikės įklijuoti
      navigator.clipboard.writeText(cap.caption + "\n\n" + (cap.hashtags || []).join(" ")).catch(() => {});
    }
    const k = f.file + "@" + finalAt;
    setSharing(f.file);
    const fallback = () => {
      window.location.href = fileUrl(`/projects/${id}/files/${f.file}`, "&download=1");
      setToast("Ši naršyklė neleidžia dalintis tiesiai – video atsisiunčiamas. Įkelkite jį programėlėje (aprašymas nukopijuotas).");
    };
    if (!navigator.share) { setSharing(""); fallback(); return; }
    try {
      const file = await prefetch(f.file, finalAt);
      if (navigator.canShare && !navigator.canShare({ files: [file] })) { fallback(); return; }
      await navigator.share({ files: [file] });
      setToast(cap ? "Aprašymas nukopijuotas – programėlėje jį įklijuokite 📋" : "Pasidalinta ✅");
    } catch (e) {
      if (e && e.name === "AbortError") { /* naudotoja uždarė langą */ }
      else if (e && e.name === "NotAllowedError" && shareBlobs.current[k]) setToast("Video paruoštas – paspauskite „Dalintis“ dar kartą");
      else setError("Nepavyko pasidalinti: " + ((e && e.message) || "nežinoma klaida") + ". Atsisiųskite video ir įkelkite ranka.");
    } finally { setSharing(""); }
  }

  if (!proj || !opts || !s) return <div className="page hint">Kraunama…</div>;

  const tileUrl = (kind, name) => fileUrl(`/projects/${id}/tile/${kind}?name=${encodeURIComponent(name)}`,
    "&b=" + (proj.clips[0] ? proj.clips[0].id : "s") + (kind === "look" || kind === "effect" ? "&v=" + saved : ""));
  const hasClips = proj.clips.length > 0;
  const out = proj.outputs || {};
  const busy = !!job;
  const cats = ["Visi", ...opts.template_categories];
  const templates = Object.entries(opts.templates).filter(([, t]) => cat === "Visi" || t.category === cat);
  const stamp = x => (x ? "&v=" + x.at : "");

  const steps = [
    ["Medžiaga", "Įkelkite ar nufilmuokite", hasClips],
    ["Stilius", "Šablonas, titrai, efektai", hasClips && proj.prepared],
    ["Peržiūra", "Pažiūrėkite prieš kuriant", !!out.preview || !!out.final],
    ["Atsisiųsti", "Video + viršelis + aprašymas", !!out.final],
  ];
  const now = steps.findIndex(x => !x[2]);

  return (
    <div className="editor">
      {/* ---------- centre: telefonas (peržiūra) ---------- */}
      <div className="stage">
        <div className={"phone " + PHONE[s.format]}>
          <div className="screen">
            {busy ? (
              <div className="empty">
                <div className="progress">
                  <div className="bar"><i style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /></div>
                  <div className="msg">{job.message} {Math.round((job.progress || 0) * 100)}%</div>
                  <button className="btn small" style={{ marginTop: 10 }} onClick={stopJob}>■ Sustabdyti</button>
                </div>
              </div>
            ) : show === "final" && out.final ? (
              <video key={"f" + out.final.at} src={fileUrl(`/projects/${id}/files/reels.mp4`, stamp(out.final))}
                     controls playsInline poster={out.final.cover ? fileUrl(`/projects/${id}/files/cover.jpg`, stamp(out.final)) : undefined} />
            ) : show === "preview" && out.preview ? (
              <video key={"p" + out.preview.at} src={fileUrl(`/projects/${id}/files/preview.mp4`, stamp(out.preview))}
                     controls autoPlay={autoplay} playsInline />
            ) : (
              <>
                <img src={live} alt="Peržiūra" />
                {!hasClips && <span className="pill tag">Pavyzdys</span>}
              </>
            )}
          </div>
        </div>
        <div className="stage-actions">
          <button className="btn" disabled={busy || !hasClips} onClick={() => run("preview")}>▶ Peržiūra</button>
          <button className="btn gold" disabled={busy || !hasClips} onClick={() => run("final")}>Kurti video</button>
        </div>
        {/* telefone – pagrindiniai veiksmai visada matomi apačioje */}
        <div className="mobile-actions">
          {busy ? (
            <div className="mobile-progress"><div className="bar"><i style={{ width: `${Math.round((job.progress || 0) * 100)}%` }} /></div>
              <span>{job.message} {Math.round((job.progress || 0) * 100)}%</span>
              <button className="btn small ghost" onClick={stopJob}>■</button></div>
          ) : (
            <>
              <button className="btn" disabled={!hasClips} onClick={() => { run("preview"); window.scrollTo({ top: 0, behavior: "smooth" }); }}>▶ Peržiūra</button>
              <button className="btn gold" disabled={!hasClips} onClick={() => { run("final"); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Kurti video</button>
            </>
          )}
        </div>
        <div className="row" style={{ justifyContent: "center" }}>
          {out.preview && <button className={"chip" + (show === "preview" ? " on" : "")} onClick={() => setShow("preview")}>Peržiūra</button>}
          {out.final && <button className={"chip" + (show === "final" ? " on" : "")} onClick={() => setShow("final")}>Galutinis</button>}
          {(out.preview || out.final) && <button className={"chip" + (show === "live" ? " on" : "")} onClick={() => setShow("live")}>Stilius</button>}
        </div>
        {!hasClips && <div className="hint" style={{ textAlign: "center", maxWidth: 300 }}>Kol neįkėlėte video, stilius rodomas ant pavyzdinio kadro.</div>}
      </div>

      {/* ---------- kairė (plačiame ekrane): projektas, rezultatas, AI režisierius ---------- */}
      <div className="ed-left">
        <div className="row" style={{ gap: 8, flexWrap: "nowrap" }}>
          <label className="title-wrap" title="Spustelėkite, kad pervadintumėte">
            <input className="title-input" key={proj.title} defaultValue={GENERIC_TITLE.test(proj.title) ? "" : proj.title}
                   placeholder="Pavadinkite projektą, pvz. „Kalėdinė akcija“" onBlur={e => rename(e.target.value)}
                   onKeyDown={e => e.key === "Enter" && e.target.blur()} aria-label="Projekto pavadinimas" maxLength={80} />
            <span className="pen">✏️</span>
          </label>
          <button className="btn small ghost danger" onClick={removeProject} title="Ištrinti projektą">🗑 Ištrinti</button>
        </div>
        <div className="steps">
          {steps.map(([t, d, done], i) => (
            <div key={t} className={"step" + (done ? " done" : i === now ? " now" : "")}><b>{i + 1}. {t}</b>{d}</div>
          ))}
        </div>
        {error && (
          <div className="error row" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
            <span style={{ flex: 1 }}>⚠ {error}</span>
            <button className="btn small ghost" onClick={() => setError("")} aria-label="Uždaryti">✕</button>
          </div>
        )}

        {out.final && (
          <div className="card section result">
            <div className="row">
              <h3 style={{ margin: 0 }}>🎉 Jūsų video paruoštas</h3>
              <span className="spacer" />
              {(out.final.formats || []).length > 1 && (
                <a className="btn ghost small" href={fileUrl(`/projects/${id}/files/visi_formatai.zip`, "&download=1&v=" + out.final.at)}>📦 Visi (ZIP)</a>
              )}
            </div>
            <div className="formats">
              {(out.final.formats || [{ fmt: s.format, file: "reels.mp4", cover: out.final.cover }]).map(f => (
                <div className="fmt" key={f.fmt}>
                  <div className="fmt-img">{f.cover && <img src={fileUrl(`/projects/${id}/files/${f.cover}`, "&v=" + out.final.at)} alt="" />}</div>
                  <b>{f.fmt}</b>
                  <span className="hint">{{ "9:16": "Reels, TikTok, Shorts", "16:9": "YouTube", "4:5": "Instagram įrašas", "1:1": "Kvadratas" }[f.fmt]}</span>
                  {CAN_SHARE && <button className="btn small gold" onClick={() => shareVideo(f)} disabled={!!sharing}>
                    {sharing === f.file ? "Ruošiama…" : "📲 Dalintis"}</button>}
                  <a className="btn small" href={fileUrl(`/projects/${id}/files/${f.file}`, "&download=1")}>⬇ Video</a>
                  {f.cover && <a className="btn small ghost" href={fileUrl(`/projects/${id}/files/${f.cover}`, "&download=1")}>⬇ Viršelis</a>}
                </div>
              ))}
            </div>
            {!CAN_SHARE && (
              <div className="publish">
                <b>📤 Įkelti į socialinius tinklus</b>
                <div className="hint" style={{ margin: "2px 0 8px" }}>Paspaudus: video atsisiunčia, aprašymas su grotažymėmis nukopijuojamas ir atsidaro
                  įkėlimo puslapis – nutempkite video į jį ir įklijuokite aprašymą (Ctrl+V).</div>
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  {PUBLISH.map(([name, url, fmt]) => (
                    <button key={name} className="btn small" onClick={() => publishTo(url, fmt)}>{name}</button>
                  ))}
                </div>
              </div>
            )}
            {CAN_SHARE && <div className="hint" style={{ margin: "8px 0" }}>📲 „Dalintis“ – pasirinkite Instagram, TikTok ar Facebook. Aprašymas su grotažymėmis nukopijuojamas automatiškai – programėlėje tiesiog įklijuokite.</div>}
            {out.final.caption && (
              <>
                <div className="caption">{out.final.caption.caption}
                  <div className="tags">{(out.final.caption.hashtags || []).join(" ")}</div>
                </div>
                <button className="btn small" onClick={() => {
                  navigator.clipboard.writeText(out.final.caption.caption + "\n\n" + (out.final.caption.hashtags || []).join(" "));
                  setToast("Aprašymas nukopijuotas 📋");
                }}>📋 Kopijuoti aprašymą su grotažymėmis</button>
              </>
            )}
          </div>
        )}

        {proj.clips.length > 0 && (
          <Director id={id} user={user} busyJob={!!job} setError={setError} setJob={setJob}
            onChanged={p => { setProj(p); setS(p.settings); setLines(null); setSaved(n => n + 1); run("preview", p.settings); }}
            onAiScene={(cid, prompt) => { const c = proj.clips.find(x => x.id === cid); if (c) aiScene(c, prompt); }} />
        )}

      </div>

      {/* ---------- dešinė: nustatymai (skirtukai) ---------- */}
      <div className="ed-right">
        <div className="tool-nav">
          <div className="groups" role="tablist">
            {GROUPS.map(([g, label, tabs]) => (
              <button key={g} className={"group" + (groupOf(tab)[0] === g ? " on" : "")}
                      onClick={() => { if (groupOf(tab)[0] !== g) setTab(tabs[0]); setError(""); }}>{label}</button>
            ))}
          </div>
          {groupOf(tab)[2].length > 1 && (
            <div className="tabs">
              {groupOf(tab)[2].map(k => (
                <button key={k} className={"tab" + (tab === k ? " on" : "")} onClick={() => { setTab(k); setError(""); }}>{TAB_LABEL[k]}</button>
              ))}
            </div>
          )}
        </div>

        {tab === "media" && (
          <div className="section">
            <ScriptGen id={id} user={user} opts={opts} s={s} setError={setError} setToast={setToast} setJob={setJob}
              onPrompter={text => { try { localStorage.setItem("script_" + id, text); } catch (e) { /* */ } setRecording(true); }}
              onVoice={(text, voice) => { set({ voiceover: { ...(s.voiceover || {}), on: true, text, ...(voice ? { voice } : {}) } }); setTab("voice"); setToast("Tekstas įkeltas į įgarsinimą 🎙"); }}
              onAutoDone={afterAuto} />
            <div className="section">
              <h3>Formatas</h3>
              <Chips items={Object.entries(opts.formats)} value={s.format} onChange={v => set({ format: v })} />
              {opts.fits && (
                <>
                  <div className="hint" style={{ margin: "4px 0 6px" }}>Kai įrašas kitos formos (pvz. gulsčias video stačiame Reels):</div>
                  <Chips items={Object.entries(opts.fits)} value={s.fit || "fill"} onChange={v => set({ fit: v })} />
                </>
              )}
            </div>
            {proj.auto_src && proj.clips.some(c => c.auto) && (
              <div className="row" style={{ margin: "10px 0" }}>
                <button className="btn small" onClick={reshuffle} disabled={!!job}>🔄 Kiti vaizdai</button>
                <span className="hint">Tas pats tekstas ir balsas – kiti automatiškai parinkti vaizdai (🎞).</span>
              </div>
            )}
            {proj.clips.length > 0 && (
              <div className="clips">
                {proj.clips.map((c, i) => (
                  <div className="clip" key={c.id}>
                    <img src={fileUrl(`/projects/${id}/clips/${c.id}/thumb`)} alt="" />
                    <div className="info">
                      <b>{c.name}</b>
                      <span>{c.image ? "Nuotrauka" : c.trim ? `✂ ${fmtTime(c.trim[0])}–${fmtTime(c.trim[1])} (${(c.trim[1] - c.trim[0]).toFixed(1)} s)` : fmtTime(c.duration)} · {c.audio === "speech" ? "🎙 kalba" : c.audio === "silent" ? "🔇 be kalbos" : "be garso"}</span>
                      {c.sound && <span style={{ color: "var(--honey)" }}>{c.sound.kind === "music" ? `🎵 ${c.sound.track}` : c.sound.kind === "file" ? `${c.sound.voice ? "🎙" : "🎵"} ${c.sound.name}` : `🎙 „${c.sound.text.slice(0, 40)}${c.sound.text.length > 40 ? "…" : ""}“`}</span>}
                    </div>
                    {(c.auto || c.ai_scene) && user.veo && (
                      <button className="btn small" onClick={() => aiScene(c)} disabled={!!job} title="Sukurti šios scenos vaizdą su AI">✨</button>
                    )}
                    {!c.image && <button className="btn small" onClick={() => setTrimming(c)} title="Karpyti">✂</button>}
                    <button className={"btn small" + (c.sound ? " accent" : "")} onClick={() => setSounding(c)} title="Muzika ar įgarsinimas šiam kadrui" aria-label="Kadro garsas">🎵</button>
                    <button className="btn small ghost" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Aukštyn">↑</button>
                    <button className="btn small ghost" onClick={() => move(i, 1)} disabled={i === proj.clips.length - 1} aria-label="Žemyn">↓</button>
                    <button className="btn small ghost danger" onClick={() => removeClip(c.id)} aria-label="Pašalinti">✕</button>
                  </div>
                ))}
              </div>
            )}
            {uploads.map(u => (
              <div className="clip" key={u.key}>
                <div className="info"><b>{u.name}</b>
                  <div className="bar" style={{ marginTop: 6 }}><i style={{ width: `${Math.round(u.p * 100)}%` }} /></div>
                  <span>{u.p < 1 ? `Įkeliama ${Math.round(u.p * 100)}%` : "Tikrinama…"}</span>
                </div>
              </div>
            ))}
            <div className={"drop" + (over ? " over" : "")} onClick={() => fileInput.current.click()}
                 onDragOver={e => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
                 onDrop={e => { e.preventDefault(); setOver(false); addFiles([...e.dataTransfer.files]); }}>
              <b>＋ Įkelkite video ar nuotraukas</b>
              <span className="hint">Nutempkite failus čia arba spauskite. MP4, MOV, JPG, PNG – iki 450 MB.</span>
            </div>
            <input ref={fileInput} type="file" accept="video/*,image/*" multiple hidden
                   onChange={e => { addFiles([...e.target.files]); e.target.value = ""; }} />
            <input ref={camInput} type="file" accept="video/*" capture="user" hidden
                   onChange={e => { addFiles([...e.target.files], true); e.target.value = ""; }} />
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn accent" onClick={() => setRecording(true)}>🎥 Filmuoti dabar (su sufleriu)</button>
              <button className="btn" onClick={() => camInput.current.click()}>📱 Telefono kamera</button>
            </div>
            <div className="hint" style={{ marginTop: 6 }}>„Filmuoti dabar“ – kamera čia pat naršyklėje, virš jos lėtai slenka jūsų tekstas.</div>
            <div className="section" style={{ marginTop: 18 }}>
              <h3>Perėjimai tarp įrašų</h3>
              <select className="input" value={s.transition} onChange={e => set({ transition: e.target.value })}>
                {opts.transitions.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
          </div>
        )}

        {tab === "style" && (
          <>
            <div className="section">
              <h3>Šablonas</h3>
              <div className="hint">Šrifto, spalvų ir filtro derinys vienu paspaudimu.</div>
              <Chips items={cats.map(c => [c, c])} value={cat} onChange={setCat} />
              <div className="tiles">
                {templates.map(([name, t]) => (
                  <Tile key={name} src={tileUrl("template", name)} label={name} on={s.template === name}
                        onClick={() => set({ template: name, accent: t.accent, color: t.color, ...(t.look ? { look: t.look } : {}),
                          ...(t.effects ? { effects: [...new Set([...(s.effects || []), ...t.effects])] } : {}) })} />
                ))}
              </div>
            </div>
            <div className="section">
              <h3>Akcento spalva</h3>
              <div className="chips">
                {Object.entries(opts.accents).map(([name, hex]) => (
                  <button key={name} type="button" className={"chip" + (s.accent === name ? " on" : "")} onClick={() => set({ accent: name })}>
                    <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: 5, background: hex, marginRight: 6 }} />{name}
                  </button>
                ))}
              </div>
            </div>
            <div className="section">
              <h3>Filtras</h3>
              <div className="tiles small">
                {opts.colors.map(name => (
                  <Tile key={name} small src={tileUrl("color", name)} label={name} on={s.color === name} onClick={() => set({ color: name })} />
                ))}
              </div>
            </div>
            <div className="section">
              <h3>Efektai</h3>
              <div className="hint">Galima rinktis kelis.</div>
              <div className="tiles small">
                {Object.entries(opts.effects).map(([name]) => (
                  <Tile key={name} small multi src={tileUrl("effect", name)} label={name} on={s.effects.includes(name)}
                        onClick={() => set({ effects: s.effects.includes(name) ? s.effects.filter(x => x !== name) : [...s.effects, name] })} />
                ))}
              </div>
            </div>
          </>
        )}

        {tab === "subs" && (
          <>
            <div className="section card">
              <Switch on={s.subtitles} onChange={v => set({ subtitles: v })} title="Titrai iš kalbos"
                      desc={user.ai ? "Kalba atpažįstama automatiškai." : user.plan === "admin"
                        ? "Automatinis atpažinimas neveikia – „Mano projektuose“ įrašykite OpenAI raktą."
                        : "Automatinis atpažinimas – Premium plane."} />
              <div className="field" style={{ marginTop: 10 }}>
                <label>Titrų kalba</label>
                <select className="input" value={s.subtitle_language} onChange={e => set({ subtitle_language: e.target.value })}>
                  {Object.entries(opts.subtitle_languages).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </div>
              {!user.ai && (
                <div className="field">
                  <label>Titrų tekstas (kai nėra automatinio atpažinimo)</label>
                  <textarea className="input" rows={3} value={s.subtitle_text} placeholder="Tekstas bus išdėliotas per video pagal kalbą."
                            onChange={e => set({ subtitle_text: e.target.value })} />
                </div>
              )}
              <Switch on={s.key_words} onChange={v => set({ key_words: v })} title="✦ Svarbiausi žodžiai – didesni ir spalvoti" />
              <Switch on={s.punch} disabled={!s.key_words} onChange={v => set({ punch: v })} title="✦ Akcentų priartėjimas" desc="Vaizdas trumpam priartėja ties svarbiu žodžiu." />
              <Switch on={s.bubbles} onChange={v => set({ bubbles: v })} title="💭 Debesėliai (?, !, WOW)" desc="Komiksų debesėliai iššoka tam tikrose vietose." />
            </div>
            <div className="section">
              <h3>Titrų stilius</h3>
              <div className="tiles">
                {Object.entries(opts.subtitle_looks).map(([k, title]) => (
                  <Tile key={k} src={tileUrl("look", k)} label={title} on={s.look === k} onClick={() => set({ look: k })} />
                ))}
              </div>
            </div>
            <div className="section">
              <h3>Vieta ir dydis</h3>
              <Chips items={opts.subtitle_positions.map(x => [x, x])} value={s.subs_pos} onChange={v => set({ subs_pos: v })} />
              <input className="range" type="range" min="70" max="140" step="5" value={s.subs_size}
                     onChange={e => setS({ ...s, subs_size: +e.target.value })} onMouseUp={e => set({ subs_size: +e.target.value })}
                     onTouchEnd={e => set({ subs_size: +e.target.value })} />
              <div className="hint">Dydis: {s.subs_size}%</div>
            </div>
            <div className="section">
              <div className="row"><h3 style={{ margin: 0 }}>Titrų tekstas</h3><span className="spacer" />
                <button className="btn small" disabled={busy || !hasClips} onClick={() => run("prepare")}>
                  🎙 {proj.prepared ? "Atpažinti iš naujo" : "Paruošti titrus"}</button>
              </div>
              <div className="hint">Pataisykite klaidas. *Žvaigždutėmis* pažymėti žodžiai bus paryškinti. Ištrynus eilutę – ji dings.</div>
              {proj.prepared && lines && lines.length > 0 ? (
                <div className="lines" style={{ marginTop: 10 }}>
                  {proj.lines.map((l, i) => (
                    <div className="line" key={i}>
                      <span>{fmtTime(l[0])}</span>
                      <input className="input" defaultValue={lines[i]} onBlur={e => {
                        if (e.target.value !== lines[i]) { const n = [...lines]; n[i] = e.target.value; saveLines(n); }
                      }} />
                    </div>
                  ))}
                </div>
              ) : proj.prepared ? <p className="hint">Kalbos neaptikta – titrų nebus.</p> : null}
            </div>
          </>
        )}

        {tab === "texts" && (
          <div className="section card">
            <div className="field">
              <label>Kabliukas – pirmos 3 sekundės</label>
              <input className="input" value={s.hook} maxLength={80} placeholder="Pvz.: 3 klaidos, kurias daro visi"
                     onChange={e => set({ hook: e.target.value })} />
            </div>
            <Chips items={opts.hook_positions.map(x => [x, x])} value={s.hook_pos} onChange={v => set({ hook_pos: v })} />
            <div className="field">
              <label>Kvietimas pabaigoje (CTA)</label>
              <input className="input" value={s.cta} maxLength={60} placeholder="Pvz.: Sekite daugiau patarimų"
                     onChange={e => set({ cta: e.target.value })} />
            </div>
            <div className="field">
              <label>Jūsų paskyra</label>
              <input className="input" value={s.handle} maxLength={40} placeholder="@jusu_paskyra"
                     onChange={e => set({ handle: e.target.value })} />
            </div>
            <div className="field">
              <label>Teksto dydis: {s.text_size}%</label>
              <input className="range" type="range" min="70" max="140" step="5" value={s.text_size}
                     onChange={e => setS({ ...s, text_size: +e.target.value })} onMouseUp={e => set({ text_size: +e.target.value })}
                     onTouchEnd={e => set({ text_size: +e.target.value })} />
            </div>
          </div>
        )}

        {tab === "anims" && (
          <>
            <div className="section card">
              <Switch on={s.anims.stickers} onChange={v => setAnim("stickers", v)} title="✨ Animuoti lipdukai" desc="Širdelės, žvaigždutės, konfeti, liepsnelės – pagal tai, ką sakote." />
              <Switch on={s.anims.marks} onChange={v => setAnim("marks", v)} title="✏️ Ranka piešti žymėjimai" desc="Apvedamas ar parodomas svarbus pasakytas žodis." />
              <Switch on={s.anims.cards} onChange={v => setAnim("cards", v)} title="🃏 Iššokančios kortelės" desc="Kai vardijate „pirma…, antra…“." />
              <Switch on={s.anims.phone} onChange={v => setAnim("phone", v)} title="📱 Nuotraukos skrenda į telefoną" desc="Tik kai kalbate apie nuotraukas, galeriją, turinį." />
              <Switch on={s.anims.fx} onChange={v => setAnim("fx", v)} title="🎆 Efektų mozaika" desc="Byrančios kaladėlės, glitch, blyksnis – vis kitas." />
              <Switch on={s.anims.intro} onChange={v => setAnim("intro", v)} title="🎬 Įžanga" desc="Logotipas ir paskyra įskrenda pradžioje." />
              <Switch on={s.anims.outro} onChange={v => setAnim("outro", v)} title="🙏 Pabaiga" desc="Padėka ir paskyra po video." />
            </div>
            <div className="section">
              <h3>🧊 3D efektai</h3>
              <div className="hint">Vaizdas virsta telefonu, kompiuteriu ar paveikslu, kuris sukasi erdvėje. Titrai lieka viršuje.</div>
              <div className="chips">
                {Object.entries(opts.gfx).filter(([k]) => FX3D.includes(k)).map(([k, label]) => (
                  <button key={k} type="button" className={"chip" + (s.gfx_kinds.includes(k) ? " on" : "")}
                          onClick={() => set({ gfx_kinds: s.gfx_kinds.includes(k) ? s.gfx_kinds.filter(x => x !== k) : [...s.gfx_kinds, k] })}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="section">
              <h3>🎁 Grafikos efektai</h3>
              <div className="hint">Parenkami pagal tai, ką sakote: skaičiai – grafikas, klausimas – žinutės ir pan.</div>
              <div className="chips">
                {Object.entries(opts.gfx).filter(([k]) => !FX3D.includes(k)).map(([k, label]) => (
                  <button key={k} type="button" className={"chip" + (s.gfx_kinds.includes(k) ? " on" : "")}
                          onClick={() => set({ gfx_kinds: s.gfx_kinds.includes(k) ? s.gfx_kinds.filter(x => x !== k) : [...s.gfx_kinds, k] })}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {tab === "broll" && (
          <Broll id={id} proj={proj} setProj={setProj} s={s} user={user} setToast={setToast} setError={setError} />
        )}

        {tab === "voice" && (
          <Voice id={id} s={s} set={set} setS={setS} opts={opts} user={user} setToast={setToast} setError={setError}
                 clipsCount={proj.clips.length} busyJob={!!job} onAuto={autoFromText} />
        )}

        {tab === "sound" && (
          <>
            <div className="section">
              <h3>Muzika</h3>
              <div className="clips">
                <div className={"clip"} style={{ cursor: "pointer", borderColor: !s.music ? "var(--amber)" : undefined }} onClick={() => set({ music: null })}>
                  <div className="info"><b>Be muzikos</b><span>Tik jūsų balsas</span></div>
                </div>
                {Object.entries(opts.music).map(([name, desc]) => (
                  <div key={name} className="clip" style={{ cursor: "pointer", borderColor: s.music === name ? "var(--amber)" : undefined }}
                       onClick={() => set({ music: name })}>
                    <div className="info"><b>{name}</b><span>{desc}</span></div>
                    <audio controls preload="none" src={"/api/music/" + encodeURIComponent(name)} style={{ height: 32, maxWidth: 160 }}
                           onClick={e => e.stopPropagation()} />
                  </div>
                ))}
              </div>
              <div className="field">
                <label>Muzikos garsumas: {s.music_volume}%</label>
                <input className="range" type="range" min="0" max="100" value={s.music_volume}
                       onChange={e => setS({ ...s, music_volume: +e.target.value })} onMouseUp={e => set({ music_volume: +e.target.value })}
                       onTouchEnd={e => set({ music_volume: +e.target.value })} />
              </div>
            </div>
            <div className="section card">
              <Switch on={s.ducking} onChange={v => set({ ducking: v })} title="Muzika patyli, kai kalbate" />
              <Switch on={s.remove_silence} onChange={v => set({ remove_silence: v })} title="Iškirpti pauzes" desc="Tylos tarp sakinių iškerpamos – video tampa gyvesnis." />
              <Switch on={s.denoise} onChange={v => set({ denoise: v })} title="Išvalyti foninį triukšmą" />
            </div>
          </>
        )}

        {tab === "pace" && (
          <div className="section card">
            <Switch on={s.all_formats !== false} onChange={v => set({ all_formats: v })} title="📐 Kartu sukurti 3 formatus"
                    desc="Kuriant video – dar 2 formatai: 9:16 (Reels, TikTok), 16:9 (YouTube), 4:5 (Instagram). Kūrimas trunka ilgiau." />
            <div className="field">
              <label>Ilgiausia trukmė</label>
              <Chips items={opts.lengths.map(x => [x, x])} value={s.length} onChange={v => set({ length: v })} />
            </div>
            <div className="field">
              <label>Greitis</label>
              <Chips items={[0.75, 1, 1.1, 1.25, 1.5, 2].map(x => [x, x + "×"])} value={s.speed} onChange={v => set({ speed: v })} />
            </div>
            <div className="field">
              <label>Progreso juostelė</label>
              <Chips items={["Viršuje", "Apačioje", "Nėra"].map(x => [x, x])} value={s.progress_bar} onChange={v => set({ progress_bar: v })} />
            </div>
          </div>
        )}
      </div>
      {toast && <div className="toast">{toast}</div>}
      {trimming && <Trimmer id={id} clip={trimming} onClose={() => setTrimming(null)} setError={setError}
                            opts={opts} projLines={proj.prepared ? proj.lines : null} lineTexts={lines}
                            span={(proj.clip_spans || {})[trimming.id]} onSaveLines={saveLines}
                            onSoundSaved={(p, k) => { setProj(p); setLines(null); setSaved(n => n + 1);
                              setToast(k === "none" ? "Garsas pašalintas" : k === "upvoice" ? "Balso įrašas pridėtas 🎙" : k === "upmusic" ? "Jūsų muzika pridėta 🎵" : "Kadrui parinkta muzika 🎵"); }}
                            onSaved={p => { setProj(p); setLines(null); setSaved(n => n + 1); setToast("Įrašas apkarpytas ✂"); }} />}
      {sounding && <ClipSound id={id} clip={sounding} opts={opts} user={user} globalMusic={s.music} setError={setError}
                              onClose={() => setSounding(null)}
                              onSaved={(p, k) => { setProj(p); setLines(null); setSaved(n => n + 1);
                                setToast(k === "none" ? "Kadro garsas pašalintas" : k === "voice" ? "Kadro įgarsinimas paruoštas 🎙" : k === "upvoice" ? "Balso įrašas pridėtas 🎙" : k === "upmusic" ? "Jūsų muzika pridėta 🎵" : k === "file" ? "Garsumas išsaugotas" : "Kadrui parinkta muzika 🎵"); }} />}
      {recording && <Recorder projectId={id} format={s.format} fit={s.fit || "fill"} onFitChange={v => set({ fit: v })} onClose={() => setRecording(false)} onRecorded={onRecorded} />}
    </div>
  );
}
