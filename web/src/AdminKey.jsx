import React, { useEffect, useState } from "react";
import { api } from "./api.js";

// Administratoriui: API raktai (OpenAI – kalbos atpažinimas, AI; Pexels – nemokami video intarpai)
const KINDS = {
  openai: { title: "🔑 OpenAI raktas", placeholder: "sk-…", help: (
    <>Reikalingas kalbos atpažinimui (titrams), AI įgarsinimui, aprašymams ir efektų parinkimui pagal tai, ką sakote.
      Raktą gausite <a href="https://platform.openai.com/api-keys" target="_blank" rel="noreferrer">platform.openai.com → API keys</a>.
      Jis išsaugomas serveryje ir veikia ir senojoje studijoje.</>) },
  gemini: { title: "🇱🇹 Google (Gemini) raktas – natūralūs lietuviški balsai", placeholder: "AIza…", help: (
    <>Ta pati Google technologija kaip NotebookLM – taisyklingas lietuviškas tarimas. Raktą gausite
      <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer"> aistudio.google.com/apikey</a> →
      „Create API key“ (prisijunkite Google paskyra).</>) },
  brevo: { title: "✉️ Brevo raktas – el. laiškai (slaptažodžio atkūrimas, sveikinimai)", placeholder: "xkeysib-…", help: (
    <>Nemokamai iki 300 laiškų per dieną. Užsiregistruokite <a href="https://www.brevo.com" target="_blank" rel="noreferrer">brevo.com</a> →
      dešinėje viršuje jūsų vardas → „SMTP &amp; API“ → „API Keys“ → „Generate a new API key“. Siuntėjo el. paštą patvirtinkite
      Brevo skiltyje „Senders, Domains &amp; Dedicated IPs“.</>) },
  stripe: { title: "💳 Stripe slaptasis raktas – mokėjimai", placeholder: "sk_live_… arba sk_test_…", help: (
    <><a href="https://dashboard.stripe.com/apikeys" target="_blank" rel="noreferrer">dashboard.stripe.com → Developers → API keys</a> →
      „Secret key“. Bandymams – „sk_test_“ raktas (Test mode).</>) },
  stripe_whsec: { title: "💳 Stripe webhook raktas", placeholder: "whsec_…", help: (
    <>Stripe → Developers → Webhooks → „Add endpoint“: adresas – žemiau nurodytas, įvykiai – <code>checkout.session.completed</code>,
      {" "}<code>customer.subscription.updated</code>, <code>customer.subscription.deleted</code>. Tada „Signing secret“ (whsec_…) įklijuokite čia.</>) },
  pixabay: { title: "🎞 Pixabay raktas (nemokamas video intarpams)", placeholder: "Pixabay API raktas", help: (
    <>Nemokami, licencijuoti video intarpams. Užsiregistruokite <a href="https://pixabay.com/accounts/register/" target="_blank" rel="noreferrer">pixabay.com</a>,
      tada atidarykite <a href="https://pixabay.com/api/docs/" target="_blank" rel="noreferrer">pixabay.com/api/docs</a> – raktas matomas
      skiltyje „Parameters“ prie „key“ (žalias tekstas). Nukopijuokite jį čia.</>) },
};

export default function AdminKey({ onChange, kind = "openai" }) {
  const K = KINDS[kind];
  const [st, setSt] = useState(null);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);

  useEffect(() => { api("/admin/" + kind).then(x => { setSt(x); setOpen(!x.set); }).catch(() => {}); }, [kind]);

  async function save(e, remove = false) {
    e && e.preventDefault();
    setBusy(true); setErr(""); setMsg("");
    try {
      const r = await api("/admin/" + kind, { method: "POST", body: { key: remove ? "" : key } });
      setSt(r); setKey("");
      setMsg(remove ? "Raktas pašalintas." : "Raktas išsaugotas ir veikia ✅");
      onChange && onChange();
    } catch (e2) { setErr(e2.message); }
    finally { setBusy(false); }
  }

  if (!st) return null;
  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div className="row" style={{ cursor: "pointer" }} onClick={() => setOpen(o => !o)}>
        <b>{K.title}</b>
        <span className={st.set ? "pill" : "pill"} style={st.set ? {} : { color: "var(--danger)", borderColor: "var(--danger)" }}>
          {st.set ? `įrašytas …${st.tail}` : "neįrašytas"}
        </span>
        <span className="spacer" />
        <span className="hint">{open ? "▲" : "▼"}</span>
      </div>
      {open && (
        <form onSubmit={save} style={{ marginTop: 12 }}>
          <div className="hint" style={{ marginBottom: 10 }}>{K.help}</div>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input className="input" type="password" value={key} onChange={e => setKey(e.target.value)} placeholder={K.placeholder} autoComplete="off" />
            <button className="btn gold" disabled={busy || !key.trim()}>{busy ? "Tikrinama…" : "Išsaugoti"}</button>
          </div>
          {st.set && <button type="button" className="btn small ghost danger" style={{ marginTop: 8 }} onClick={e => save(e, true)} disabled={busy}>Pašalinti raktą</button>}
          {msg && <div className="hint" style={{ color: "var(--ok)", marginTop: 8 }}>{msg}</div>}
          {err && <div className="error">{err}</div>}
        </form>
      )}
    </div>
  );
}
