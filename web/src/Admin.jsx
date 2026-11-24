import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import AdminKey from "./AdminKey.jsx";

// 👑 Klientų valdymas: pridėti, keisti planą ir AI ribas, išjungti, matyti šio mėnesio naudojimą
const PLANS = { basic: "Pagrindinis", premium: "Premium", admin: "Administratorius" };
const genPassword = () => {
  const a = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from(crypto.getRandomValues(new Uint32Array(12)), x => a[x % a.length]).join("");
};
const lim = v => (v == null ? "∞" : v);

// Prisijungimo vardas iš „Vardas / įmonė“: be lietuviškų raidžių ir tarpų, unikalus
const LT = { ą: "a", č: "c", ę: "e", ė: "e", į: "i", š: "s", ų: "u", ū: "u", ž: "z" };
function slug(name, taken) {
  let base = name.toLowerCase().replace(/[ąčęėįšųūž]/g, c => LT[c]).normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "").slice(0, 30);
  if (base.length < 3) base = (base + "klientas").slice(0, 12);
  let u = base, n = 2;
  while (taken.has(u)) u = base + n++;
  return u;
}

function UserForm({ initial, isNew, defaults, taken, onCancel, onSave }) {
  const [f, setF] = useState(() => ({ username: "", name: "", plan: "premium", password: isNew ? genPassword() : "",
    minutes: "", ai_clips: "", voice_chars: "", active: true, ...initial }));
  const [manual, setManual] = useState(false);  // prisijungimo vardas įrašytas ranka – nebekeičiam
  const set = (k, v) => setF(x => ({ ...x, [k]: v,
    ...(k === "name" && isNew && !manual ? { username: v.trim() ? slug(v, taken) : "" } : {}) }));
  const d = defaults[f.plan] || {};
  const num = v => (v === "" || v == null ? null : Number(v));
  return (
    <div className="modal" onClick={onCancel}>
      <form className="card" style={{ maxWidth: 520 }} onClick={e => e.stopPropagation()}
            onSubmit={e => { e.preventDefault(); onSave({ ...f, minutes: num(f.minutes), ai_clips: num(f.ai_clips), voice_chars: num(f.voice_chars), password: f.password || null }); }}>
        <h3 className="serif" style={{ marginTop: 0, fontSize: 22 }}>{isNew ? "＋ Naujas klientas" : `✏️ ${f.username}`}</h3>
        <div className="field"><label>Vardas / įmonė</label>
          <input className="input" value={f.name} onChange={e => set("name", e.target.value)} placeholder="Grožio salonas Rūta" autoFocus={isNew} /></div>
        {isNew && (
          <div className="field"><label>Prisijungimo vardas {!manual && f.username && <span className="hint">– pasiūlytas automatiškai, galite pakeisti</span>}</label>
            <input className="input" value={f.username} required placeholder="užsipildys pagal pavadinimą"
                   onChange={e => { setManual(true); setF(x => ({ ...x, username: e.target.value.toLowerCase().replace(/\s/g, "") })); }} /></div>
        )}
        <div className="field"><label>Planas</label>
          <div className="chips">{Object.entries(PLANS).map(([k, l]) => (
            <button key={k} type="button" className={"chip" + (f.plan === k ? " on" : "")} onClick={() => set("plan", k)}>{l}</button>))}</div></div>
        <div className="field"><label>{isNew ? "Slaptažodis (perduokite klientui)" : "Naujas slaptažodis (palikite tuščią – nekeisti)"}</label>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input className="input" value={f.password} onChange={e => set("password", e.target.value)} placeholder={isNew ? "" : "nekeisti"} />
            <button type="button" className="btn small" onClick={() => set("password", genPassword())}>🎲</button>
          </div></div>
        {f.plan !== "admin" && (
          <>
            <div className="hint" style={{ marginBottom: 6 }}>Mėnesio ribos (tuščia – pagal planą):</div>
            <div className="row" style={{ flexWrap: "nowrap", gap: 8 }}>
              <div className="field" style={{ flex: 1 }}><label>🎙 Atpažinimo min.</label>
                <input className="input" type="number" min="0" value={f.minutes ?? ""} onChange={e => set("minutes", e.target.value)} placeholder="60" /></div>
              <div className="field" style={{ flex: 1 }}><label>🎬 AI kadrų</label>
                <input className="input" type="number" min="0" value={f.ai_clips ?? ""} onChange={e => set("ai_clips", e.target.value)} placeholder={String(d.ai_clips ?? 0)} /></div>
              <div className="field" style={{ flex: 1 }}><label>🗣 Įgarsinimo simb.</label>
                <input className="input" type="number" min="0" step="1000" value={f.voice_chars ?? ""} onChange={e => set("voice_chars", e.target.value)} placeholder={String(d.voice_chars ?? 0)} /></div>
            </div>
          </>
        )}
        {!isNew && (
          <div className="switch" onClick={() => set("active", !f.active)}>
            <div className="txt"><b>Aktyvus</b><span>Išjungus klientas nebegalės prisijungti (projektai lieka).</span></div>
            <div className={"toggle" + (f.active ? " on" : "")} />
          </div>
        )}
        <div className="row" style={{ marginTop: 12 }}>
          <button type="button" className="btn ghost" onClick={onCancel}>Atšaukti</button>
          <span className="spacer" />
          <button className="btn gold">{isNew ? "Sukurti" : "Išsaugoti"}</button>
        </div>
      </form>
    </div>
  );
}

function TextFields({ st, fields, onSave }) {
  const [v, setV] = useState(() => Object.fromEntries(fields.map(([k]) => [k, st[k] || ""])));
  const dirty = fields.some(([k]) => (v[k] || "") !== (st[k] || ""));
  return (
    <>
      {fields.map(([k, label, ph]) => (
        <div className="field" key={k}><label>{label}</label>
          <input className="input" value={v[k]} placeholder={ph} onChange={e => setV({ ...v, [k]: e.target.value })} /></div>
      ))}
      <button className="btn" disabled={!dirty} onClick={() => onSave(v)}>Išsaugoti</button>
    </>
  );
}

function Section({ id, title, ok, children, open, setOpen }) {
  return (
    <div className="card section">
      <div className="row" style={{ cursor: "pointer" }} onClick={() => setOpen(open === id ? "" : id)}>
        <b>{title}</b><span className="pill" style={ok ? {} : { color: "var(--danger)", borderColor: "var(--danger)" }}>{ok ? "įjungta" : "neįjungta"}</span>
        <span className="spacer" /><span className="hint">{open === id ? "▲" : "▼"}</span>
      </div>
      {open === id && <div style={{ marginTop: 12 }}>{children}</div>}
    </div>
  );
}

function Business({ st, save, onError }) {
  const [open, setOpen] = useState("");
  const [msg, setMsg] = useState("");
  const webhook = `${window.location.origin}/api/billing/webhook`;
  async function test() {
    setMsg("");
    try { const r = await api("/admin/test_mail", { method: "POST" }); setMsg(`✅ Išsiųsta į ${r.to}`); }
    catch (e) { onError(e.message); }
  }
  return (
    <>
      <Section open={open} setOpen={setOpen} id="biz" title="📄 Veiklos duomenys (taisyklėms ir privatumo politikai)" ok={!!st.biz_name}>
        <div className="error" style={{ marginBottom: 8 }}>⚠ Šie duomenys rodomi VIEŠAI – juos mato visi, net neprisijungę. Asmens kodo ir namų adreso nerašykite.</div>
        <div className="hint" style={{ marginBottom: 10 }}>Įrašomi į <a href="#/terms" target="_blank" rel="noreferrer">taisykles</a> ir{" "}
          <a href="#/privacy" target="_blank" rel="noreferrer">privatumo politiką</a>. Tai šablonai – prieš prekybą verta, kad juos peržiūrėtų teisininkas.</div>
        <TextFields st={st} onSave={save} fields={[["biz_name", "Vardas, pavardė / įmonė", "pvz. Vardenė Pavardenė, individuali veikla"],
          ["biz_code", "Įmonės kodas arba individualios veiklos pažymos / verslo liudijimo Nr. (NE asmens kodas!)", "pvz. 306123456 arba IV pažymos Nr. 1234567"], ["biz_address", "Veiklos adresas (užtenka miesto)", "pvz. Vilnius, Lietuva"],
          ["biz_email", "El. paštas klientams (ir pranešimams jums)", "info@…"]]} />
      </Section>
      <Section open={open} setOpen={setOpen} id="mail" title="✉️ El. laiškai (Brevo)" ok={st.mail}>
        <AdminKey kind="brevo" />
        <TextFields st={st} onSave={save} fields={[["mail_from", "Siuntėjo el. paštas (patvirtintas Brevo)", "pvz. info@…"],
          ["mail_name", "Siuntėjo vardas", "Reels montavimo studija"]]} />
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn small" onClick={test} disabled={!st.mail}>✉️ Siųsti bandomąjį laišką</button>
          {msg && <span className="hint" style={{ color: "var(--ok)" }}>{msg}</span>}
        </div>
      </Section>
      <Section open={open} setOpen={setOpen} id="pay" title="💳 Mokėjimai (Stripe prenumerata)" ok={st.billing}>
        <ol className="hint" style={{ paddingLeft: 18 }}>
          <li>Stripe → <b>Product catalog → Add product</b> „Premium“, kaina pvz. 19 € / mėn. (<b>Recurring, Monthly</b>) → nukopijuokite <b>Price ID</b> (price_…).</li>
          <li>Įklijuokite žemiau slaptąjį raktą, Price ID ir webhook raktą.</li>
          <li>Webhook adresas: <code style={{ userSelect: "all" }}>{webhook}</code></li>
          <li>Stripe → <b>Settings → Billing → Customer portal</b> – įjunkite, kad klientai galėtų patys nutraukti prenumeratą.</li>
        </ol>
        <AdminKey kind="stripe" />
        <AdminKey kind="stripe_whsec" />
        <TextFields st={st} onSave={save} fields={[["stripe_price", "Premium Price ID", "price_…"], ["price_label", "Kaina klientams (rodoma)", "19 € / mėn."]]} />
      </Section>
    </>
  );
}

function Settings({ onError }) {
  const [st, setSt] = useState(null);
  const [contact, setContact] = useState("");
  useEffect(() => { api("/public/settings").then(x => { setSt(x); setContact(x.contact || ""); }).catch(() => {}); }, []);
  async function save(patch) {
    try { const x = await api("/admin/settings", { method: "PUT", body: patch }); setSt(x); setContact(x.contact || ""); }
    catch (e) { onError(e.message); }
  }
  if (!st) return null;
  return (
    <>
    <Business st={st} save={save} onError={onError} />
    <div className="card section">
      <div className="switch" onClick={() => save({ registration: !st.registration })}>
        <div className="txt"><b>📝 Klientai gali registruotis patys</b>
          <span>Prisijungimo puslapyje – „Registruotis“. Naujas klientas gauna Pagrindinį planą; sumokėjusį perkelkite į ⭐ Premium.</span></div>
        <div className={"toggle" + (st.registration ? " on" : "")} />
      </div>
      <div className="field" style={{ marginTop: 10, marginBottom: 0 }}>
        <label>Kontaktas Premium planui (rodomas Pagrindinio plano klientams)</label>
        <div className="row" style={{ flexWrap: "nowrap" }}>
          <input className="input" value={contact} onChange={e => setContact(e.target.value)} placeholder="pvz. info@jusu.lt arba +370 600 00000" />
          <button className="btn" onClick={() => save({ contact })} disabled={contact === (st.contact || "")}>Išsaugoti</button>
        </div>
      </div>
    </div>
    </>
  );
}

export default function Admin({ me }) {
  const [data, setData] = useState(null);
  const [edit, setEdit] = useState(null);   // {user} | {new:true}
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);  // naujo kliento prisijungimo duomenys (parodomi vieną kartą)
  const load = () => api("/admin/users").then(setData).catch(e => setError(e.message));
  useEffect(() => { load(); }, []);

  async function save(f) {
    setError("");
    try {
      if (edit.new) {
        await api("/admin/users", { method: "POST", body: f });
        setCreated({ username: f.username, password: f.password });
      } else {
        const { username, ...rest } = f;
        await api(`/admin/users/${encodeURIComponent(edit.user.username)}`, { method: "PUT", body: rest });
      }
      setEdit(null);
      load();
    } catch (e) { setError(e.message); }
  }
  async function upgrade(u) {
    if (!window.confirm(`Perkelti „${u.name}“ į Premium? AI funkcijos jam atsivers iškart.`)) return;
    try { await api(`/admin/users/${encodeURIComponent(u.username)}`, { method: "PUT", body: { plan: "premium" } }); load(); }
    catch (e) { setError(e.message); }
  }
  async function remove(u) {
    if (!window.confirm(`Pašalinti klientą „${u.username}“? Jo projektai serveryje liks.`)) return;
    try { await api(`/admin/users/${encodeURIComponent(u.username)}`, { method: "DELETE" }); load(); }
    catch (e) { setError(e.message); }
  }

  if (!data) return <div className="page hint">{error || "Kraunama…"}</div>;
  const link = window.location.origin;
  return (
    <div className="page">
      <div className="kicker">ADMINISTRAVIMAS</div>
      <div className="row"><h2 style={{ margin: 0 }}>👑 Klientai</h2><span className="spacer" />
        <button className="btn gold" onClick={() => setEdit({ new: true })}>＋ Naujas klientas</button></div>
      <div className="hint" style={{ margin: "4px 0 14px" }}>
        Ribos – per mėnesį. Numatyta: Premium – {data.defaults.premium.ai_clips} AI kadrų ir {data.defaults.premium.voice_chars} įgarsinimo
        simbolių, Pagrindinis – AI nėra. Kadrai iš „📚 Mano AI kadrai“ – nemokami.
      </div>
      {error && <div className="error">⚠ {error}</div>}
      <Settings onError={setError} />
      {created && (
        <div className="card section">
          <b>✅ Klientas sukurtas.</b> Perduokite jam:
          <div className="caption" style={{ marginTop: 8 }}>{`Studija: ${link}\nPrisijungimo vardas: ${created.username}\nSlaptažodis: ${created.password}`}</div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn small" onClick={() => navigator.clipboard.writeText(`Studija: ${link}\nPrisijungimo vardas: ${created.username}\nSlaptažodis: ${created.password}`)}>📋 Kopijuoti</button>
            <button className="btn small ghost" onClick={() => setCreated(null)}>Uždaryti</button>
            <span className="hint">Slaptažodis daugiau nebus rodomas.</span>
          </div>
        </div>
      )}
      <div className="users">
        {data.users.map(u => (
          <div key={u.username} className={"user" + (u.active ? "" : " off")}>
            <div className="info">
              <b>{u.name}</b>
              <span>{u.username} · <span className="pill">{PLANS[u.plan]}</span>{!u.active && " · išjungtas"}{u.source === "secrets" && " · secrets.toml"}
                {u.self_registered && " · 📝 užsiregistravo pats"}{u.subscribed && " · 💳 prenumerata"}{u.created ? ` · ${new Date(u.created * 1000).toLocaleDateString("lt-LT")}` : ""}</span>
            </div>
            <div className="use">
              <span title="Kalbos atpažinimas">🎙 {u.used.minutes}/{lim(u.minutes)} min</span>
              <span title="AI kadrai">🎬 {u.used.ai_clips}/{lim(u.ai_clips)}</span>
              <span title="AI įgarsinimo simboliai">🗣 {u.used.voice_chars}/{lim(u.voice_chars)}</span>
            </div>
            {u.source === "managed" ? (
              <div className="row" style={{ gap: 4 }}>
                {u.plan === "basic" && <button className="btn small gold" onClick={() => upgrade(u)} title="Perkelti į Premium (sumokėjo)">⭐ Premium</button>}
                <button className="btn small ghost icon" onClick={() => setEdit({ user: u })} title="Keisti">✏️</button>
                {u.username !== me.username && <button className="btn small ghost danger icon" onClick={() => remove(u)} title="Pašalinti">🗑</button>}
              </div>
            ) : <span className="hint" title="Keičiama serverio secrets.toml">🔒</span>}
          </div>
        ))}
      </div>
      {edit && <UserForm isNew={!!edit.new} defaults={data.defaults} taken={new Set(data.users.map(u => u.username))} onCancel={() => setEdit(null)} onSave={save}
                         initial={edit.user ? { username: edit.user.username, name: edit.user.name, plan: edit.user.plan, active: edit.user.active,
                           minutes: edit.user.minutes ?? "", ai_clips: edit.user.ai_clips ?? "", voice_chars: edit.user.voice_chars ?? "" } : {}} />}
    </div>
  );
}
