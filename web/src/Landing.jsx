import React, { useEffect, useState } from "react";
import { api } from "./api.js";
import Story from "./Story.jsx";

// 🌐 Viešas pristatymo puslapis (ką mato neprisijungęs lankytojas ir Stripe), kainos ir poraštė.
export function usePublic() {
  const [s, setS] = useState(null);
  useEffect(() => { api("/public/settings").then(setS).catch(() => setS({})); }, []);
  return s;
}

const go = h => { window.location.hash = h; window.scrollTo(0, 0); };

export function SiteNav({ user }) {
  return (
    <header className="site-nav">
      <div className="brand" onClick={() => go("#/home")}>
        <img src="/logo.svg" alt="" /><b>Reels montavimo studija</b>
      </div>
      <nav>
        <a href="#/home" onClick={e => { e.preventDefault(); go("#/home"); setTimeout(() => document.getElementById("kaip")?.scrollIntoView({ behavior: "smooth" }), 50); }}>Kaip veikia</a>
        <a href="#/pricing">Kainos</a>
        <a href="#/home" onClick={e => { e.preventDefault(); go("#/home"); setTimeout(() => document.getElementById("duk")?.scrollIntoView({ behavior: "smooth" }), 50); }}>DUK</a>
      </nav>
      <span className="spacer" />
      {user
        ? <button className="btn small gold" onClick={() => go("")}>Mano projektai</button>
        : <>
          <button className="btn small ghost" onClick={() => go("#/login")}>Prisijungti</button>
          <button className="btn small gold hide-sm" onClick={() => go("#/register")}>Išbandyti</button>
        </>}
    </header>
  );
}

export function SiteFooter({ s }) {
  s = s || {};
  const email = s.biz_email || s.contact;
  return (
    <footer className="site-foot">
      <div>
        <b>Reels montavimo studija</b>
        <div className="hint">
          {s.biz_name || ""}{s.biz_code ? ` · ${s.biz_code}` : ""}{s.biz_address ? ` · ${s.biz_address}` : ""}
          {email && <> · <a href={email.includes("@") ? `mailto:${email}` : undefined}>{email}</a></>}
        </div>
      </div>
      <div className="links">
        <a href="#/pricing">Kainos</a>
        <a href="#/terms">Naudojimosi taisyklės</a>
        <a href="#/privacy">Privatumo politika</a>
        <a href="#/refund">Grąžinimai ir atšaukimas</a>
      </div>
      <div className="hint">© {new Date().getFullYear()} · Duomenys saugomi ES (Vokietija) · Mokėjimai – Stripe</div>
    </footer>
  );
}

function num(n) { return Number(n || 0).toLocaleString("lt-LT"); }

export function Plans({ s, user, onBuy, busy }) {
  if (!s) return null;
  const prem = (s.limits || {}).premium || {}, trial = s.trial_days;
  const price = s.price_label;
  const cta = plan => {
    if (!user) return <button className="btn gold block" onClick={() => go("#/register")}>
      {plan === "premium" && trial ? `Išbandyti ${trial} d. nemokamai` : "Pradėti nemokamai"}</button>;
    if (plan === "premium" && user.plan === "basic" && !user.trial_until && s.billing && onBuy)
      return <button className="btn gold block" onClick={onBuy} disabled={busy}>⭐ Įsigyti Premium</button>;
    if (plan === "premium" && user.trial_until && s.billing && onBuy)
      return <button className="btn gold block" onClick={onBuy} disabled={busy}>⭐ Pasilikti Premium</button>;
    if (user.plan === plan && !user.trial_until) return <div className="pill" style={{ display: "block", textAlign: "center" }}>Jūsų planas</div>;
    return null;
  };
  return (
    <div className="plans">
      <div className="card plan">
        <div className="kicker">PAGRINDINIS</div>
        <div className="price">0 €<span> / visada</span></div>
        <div className="hint">Viskam, ką sumontuoti galima be dirbtinio intelekto.</div>
        <ul>
          <li>Filmavimas su sufleriu ir įkėlimas</li>
          <li>Šablonai, efektai, filtrai, perėjimai</li>
          <li>Titrai iš jūsų įrašyto teksto</li>
          <li>Muzikos biblioteka – ir atskira kiekvienam kadrui</li>
          <li>Karpymas ir dalinimas kaip CapCut</li>
          <li>3 formatai iš karto: Reels / TikTok, 4:5, YouTube</li>
          <li>Nemokami intarpai (Pixabay)</li>
          <li className="no">AI titrai, AI balsai ir AI kadrai</li>
        </ul>
        {cta("basic")}
      </div>
      <div className="card plan best">
        <div className="kicker">⭐ PREMIUM</div>
        <div className="price">{price || "Kaina – susisiekite"}</div>
        <div className="hint">Viskas iš Pagrindinio plano ir dirbtinis intelektas.</div>
        <ul>
          <li><b>Titrai automatiškai iš kalbos</b> (iki {num(s.minutes)} min. / mėn.)</li>
          <li><b>Natūralūs lietuviški AI balsai</b> (iki {num(prem.voice_chars)} simbolių / mėn.)</li>
          <li><b>AI sukurti video kadrai</b> (iki {num(prem.ai_clips)} / mėn.)</li>
          <li>AI įgarsinimas atskirai kiekvienam kadrui</li>
          <li>AI tekstai įgarsinimui ir idėjos</li>
          <li>Prenumeratą galite nutraukti bet kada</li>
        </ul>
        {cta("premium")}
        {trial ? <div className="hint" style={{ marginTop: 8, textAlign: "center" }}>🎁 Naujiems – {trial} d. Premium nemokamai, kortelės nereikia.</div> : null}
      </div>
    </div>
  );
}

const STEPS = [
  ["🎬", "Nufilmuokite arba įkelkite", "Filmuokite telefonu ar kompiuteriu – tekstas slenka ekrane kaip suflerio. Arba įkelkite turimus video ir nuotraukas."],
  ["✨", "Pasirinkite stilių", "Šablonas, titrų stilius, muzika, efektai. Pauzės iškerpamos ir titrai sudedami automatiškai."],
  ["📲", "Atsisiųskite ir skelbkite", "Gausite Reels / TikTok, Instagram 4:5 ir YouTube versijas, viršelį ir aprašymą su grotažymėmis."],
];
const FEATURES = [
  ["🇱🇹", "Lietuviški titrai", "AI atpažįsta lietuvišką kalbą ir sudeda modernius, animuotus titrus."],
  ["🎙", "Natūralūs AI balsai", "Lietuviškas įgarsinimas visam video arba atskirai kiekvienam kadrui."],
  ["📜", "Suflerius", "Kalbėkite drąsiai – tekstas slenka ekrane, kol filmuojate."],
  ["✂", "Karpymas", "Patogus karpymas ir dalinimas telefone – lyg CapCut ar Instagram."],
  ["🎞", "Intarpai ir AI kadrai", "Vaizdai iš bibliotekos ar sukurti AI – parenkami taip, kad neuždengtų veido."],
  ["🎵", "Muzika be rūpesčių", "17 melodijų be autorių teisių problemų: nuo lo-fi iki phonk ir kalėdinės."],
  ["📐", "3 formatai iš karto", "Vienas mygtukas – video Instagram, TikTok ir YouTube."],
  ["🔒", "Duomenys ES", "Serveris Vokietijoje, jūsų video matote tik jūs."],
];
const WHO = ["Kirpyklos ir grožio salonai", "Kavinės ir restoranai", "Nekilnojamasis turtas", "Treneriai ir sporto klubai",
  "Rankų darbo gaminiai ir e. parduotuvės", "Renginiai, fotografai, kūrėjai"];

function faq(s) {
  const email = s.biz_email || s.contact || "el. paštu";
  return [
    ["Ar reikia mokėti montuoti?", "Ne. Studija pati iškerpa pauzes, sudeda titrus, muziką ir efektus – jūs tik pasirenkate stilių. Norint – galima viską pakeisti ranka."],
    ["Ar veikia telefone?", "Taip – naršyklėje (Safari, Chrome) iPhone ir Android telefonuose, taip pat kompiuteryje. Nieko diegti nereikia."],
    [`Kas nutinka pasibaigus ${s.trial_days || 7} d. bandymui?`, "Paskyra automatiškai lieka su nemokamu Pagrindiniu planu. Niekas nenuskaičiuojama – kortelės bandymui nereikia."],
    ["Kaip atšaukti Premium prenumeratą?", "Bet kada: „Mano projektai“ → „Valdyti prenumeratą“. Premium galios iki apmokėto laikotarpio pabaigos, toliau mokestis nebeimamas."],
    ["Ar galiu naudoti muziką Instagram ir TikTok?", "Taip. Studijos melodijos sukurtos specialiai šiai studijai – jas laisvai naudokite savo video, taip pat ir komerciniams tikslams. Populiarias dainas galite pridėti pačiame Instagram ar TikTok – ten jos licencijuotos."],
    ["Kur saugomi mano video?", "ES serveryje (Vokietijoje). Jūsų projektus matote tik jūs. Ištrynus projektą – jo failai ištrinami."],
    ["Ar galiu susigrąžinti pinigus?", <>Taip – žr. <a href="#/refund">Grąžinimai ir atšaukimas</a>. Klausimus rašykite: {email}.</>],
  ];
}

export default function Landing({ user }) {
  const s = usePublic();
  const [open, setOpen] = useState(-1);
  if (!s) return null;
  const canReg = s.registration !== false;
  return (
    <div className="site">
      <SiteNav user={user} />
      <section className="hero">
        <img className="logo" src="/logo.svg" alt="" />
        <div className="kicker">LIETUVIŠKA REELS STUDIJA SMULKIAM VERSLUI</div>
        <h1 className="goldtext">Jūs nufilmuojate –<br />studija sumontuoja Reels.</h1>
        <p className="lead">Lietuviški titrai, natūralūs AI balsai, muzika ir trys formatai – Instagram, TikTok ir YouTube –
          per kelias minutes, be montavimo žinių.</p>
        <div className="row" style={{ justifyContent: "center", gap: 10 }}>
          {user ? <button className="btn gold" onClick={() => go("")}>Į mano projektus</button>
            : canReg ? <button className="btn gold" onClick={() => go("#/register")}>
              {s.trial_days ? `Išbandyti ${s.trial_days} d. nemokamai` : "Pradėti nemokamai"}</button>
              : <button className="btn gold" onClick={() => go("#/login")}>Prisijungti</button>}
          <button className="btn ghost" onClick={() => go("#/pricing")}>Kainos</button>
        </div>
        {!user && canReg && <div className="hint" style={{ marginTop: 10 }}>Kortelės nereikia · Pagrindinis planas – nemokamas visada</div>}
        <div className="quote">Jūsų akimirkos – kaip gintaras: išsaugotos gražiausios.</div>
      </section>

      <section id="kaip">
        <h2>Kaip tai veikia</h2>
        <div className="steps3">
          {STEPS.map(([i, t, d], k) => (
            <div className="card" key={t}><div className="big">{i}</div><b>{k + 1}. {t}</b><p className="hint">{d}</p></div>
          ))}
        </div>
      </section>

      <section>
        <h2>Ką moka studija</h2>
        <div className="features">
          {FEATURES.map(([i, t, d]) => (
            <div className="card" key={t}><span className="big">{i}</span><b>{t}</b><p className="hint">{d}</p></div>
          ))}
        </div>
      </section>

      <section>
        <h2>Kam tinka</h2>
        <div className="chips" style={{ justifyContent: "center" }}>{WHO.map(w => <span className="chip" key={w}>{w}</span>)}</div>
      </section>

      <section id="kainos">
        <h2>Kainos</h2>
        <Plans s={s} user={user} />
      </section>

      <section id="duk">
        <h2>Dažni klausimai</h2>
        <div className="faq">
          {faq(s).map(([q, a], k) => (
            <div className={"card" + (open === k ? " open" : "")} key={k} onClick={() => setOpen(open === k ? -1 : k)}>
              <b>{open === k ? "▾" : "▸"} {q}</b>
              {open === k && <p className="hint" style={{ fontSize: 14 }}>{a}</p>}
            </div>
          ))}
        </div>
      </section>

      <section style={{ maxWidth: 640 }}>
        <Story />
      </section>

      {(s.biz_email || s.contact) && (
        <section className="center">
          <h2>Turite klausimų?</h2>
          <p className="hint" style={{ fontSize: 15 }}>Parašykite – atsakysime per 1 darbo dieną:{" "}
            <b style={{ color: "var(--honey)" }}>{s.biz_email || s.contact}</b></p>
        </section>
      )}
      <SiteFooter s={s} />
    </div>
  );
}

export function Pricing({ user }) {
  const s = usePublic();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  async function buy() {
    setBusy(true);
    try { window.location.href = (await api("/billing/checkout", { method: "POST" })).url; }
    catch (e) { setErr(e.message); setBusy(false); }
  }
  if (!s) return null;
  return (
    <div className="site">
      <SiteNav user={user} />
      <section>
        <div className="kicker" style={{ textAlign: "center" }}>KAINOS</div>
        <h2>Paprasti planai be įsipareigojimų</h2>
        <p className="hint center" style={{ fontSize: 15, marginTop: -6 }}>Pradėkite nemokamai. Premium – kai prireiks dirbtinio intelekto.</p>
        {err && <div className="error">{err}</div>}
        <Plans s={s} user={user} onBuy={buy} busy={busy} />
        <div className="card" style={{ marginTop: 18 }}>
          <b>Kaip vyksta apmokėjimas</b>
          <ul className="hint" style={{ fontSize: 14, paddingLeft: 18 }}>
            <li>Mokama kortele per saugią „Stripe“ apmokėjimo sistemą – kortelės duomenų mes nematome.</li>
            <li>Premium prenumerata mokama kas mėnesį iš anksto ir atsinaujina automatiškai, kol ją nutrauksite.</li>
            <li>Nutraukti galite bet kada – „Mano projektai“ → „Valdyti prenumeratą“. Sąskaitas rasite ten pat.</li>
            <li>AI ribos (minutės, simboliai, kadrai) atsinaujina kiekvieno mėnesio pradžioje; nepanaudotos neperkeliamos.</li>
            <li>Pinigų grąžinimas – pagal <a href="#/refund">grąžinimo ir atšaukimo tvarką</a>.</li>
          </ul>
        </div>
      </section>
      <SiteFooter s={s} />
    </div>
  );
}
