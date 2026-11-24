import React, { useEffect, useState } from "react";
import { api } from "./api.js";

// 📄 Taisyklės ir privatumo politika (šablonas, užpildomas administratorės veiklos duomenimis).
// Tai nėra teisinė konsultacija – prieš pradedant prekybą verta, kad tekstą peržiūrėtų teisininkas.
function useBiz() {
  const [s, setS] = useState(null);
  useEffect(() => { api("/public/settings").then(setS).catch(() => setS({})); }, []);
  return s;
}

function Shell({ title, children }) {
  return (
    <div className="page legal">
      <button className="btn small ghost" onClick={() => (window.history.length > 1 ? window.history.back() : (window.location.hash = "#/home"))}>← Atgal</button>
      <h2>{title}</h2>
      <div className="card">{children}</div>
    </div>
  );
}

function Who({ s }) {
  const name = s.biz_name || "[Veiklos vykdytojo vardas, pavardė / įmonės pavadinimas]";
  return (
    <p>Paslaugos teikėjas: <b>{name}</b>{s.biz_code ? `, ${s.biz_code}` : ", [įmonės kodas arba individualios veiklos pažymos Nr.]"}
      {s.biz_address ? `, ${s.biz_address}` : ", [adresas]"}. El. paštas: <b>{s.biz_email || s.contact || "[el. paštas]"}</b>.</p>
  );
}

export function Terms() {
  const s = useBiz();
  if (!s) return null;
  return (
    <Shell title="Naudojimosi taisyklės">
      <Who s={s} />
      <h3>1. Paslauga</h3>
      <p>„Reels montavimo studija“ (toliau – Studija) – internetinė programa trumpiems vaizdo įrašams (Reels, TikTok, Shorts)
        montuoti: titrai, šablonai, efektai, muzika, įgarsinimas ir kitos funkcijos.</p>
      <h3>2. Paskyra</h3>
      <p>Registruodamiesi pateikiate teisingą el. paštą ir saugote savo slaptažodį. Už veiksmus jūsų paskyroje atsakote jūs.
        Paslaugos teikėjas gali sustabdyti paskyrą, jei pažeidžiamos šios taisyklės ar įstatymai.</p>
      <h3>3. Planai ir apmokėjimas</h3>
      <p>Pagrindinis planas – be dirbtinio intelekto (AI) funkcijų. Premium planas – su AI funkcijomis pagal nurodytas mėnesio
        ribas{s.price_label ? `; kaina – ${s.price_label}` : ""}.{s.trial_days ? ` Užsiregistravę gaunate ${s.trial_days} d. nemokamą Premium bandymą (su mažesnėmis AI ribomis); jam pasibaigus paskyra automatiškai lieka su Pagrindiniu planu, mokestis neimamas.` : ""} Prenumerata atsinaujina kas mėnesį, kol ją nutrauksite;
        nutraukus – Premium galioja iki apmokėto laikotarpio pabaigos. Mokėjimus apdoroja mokėjimų paslaugų teikėjas (Stripe);
        jūsų kortelės duomenų mes nematome ir nesaugome.</p>
      <h3>4. Jūsų turinys</h3>
      <p>Jūsų įkelti vaizdo įrašai, nuotraukos ir tekstai lieka jūsų. Studijai suteikiate teisę juos apdoroti tik tam, kad
        sukurtume jūsų užsakytus vaizdo įrašus. Įkelkite tik tokį turinį, kurį turite teisę naudoti (ir žmonių, kurie
        jame matomi, sutikimą). Draudžiama kurti neteisėtą, įžeidžiantį ar kitų teises pažeidžiantį turinį.</p>
      <h3>5. AI funkcijos</h3>
      <p>AI funkcijoms (kalbos atpažinimui, įgarsinimui, vaizdo kadrams, tekstams) naudojamos trečiųjų šalių paslaugos
        (OpenAI, Google). AI rezultatai gali būti netikslūs – prieš skelbdami juos peržiūrėkite. AI sukurtuose
        kadruose gali būti nematoma žyma, kad jie sukurti AI.</p>
      <h3>6. Atsakomybė</h3>
      <p>Studija teikiama „tokia, kokia yra“. Stengiamės, kad ji veiktų be sutrikimų, bet negarantuojame nepertraukiamo
        veikimo. Pasidarykite svarbių vaizdo įrašų kopijas – atsisiųskite juos.</p>
      <h3>7. Kontaktai ir ginčai</h3>
      <p>Klausimus ir pretenzijas siųskite el. paštu {s.biz_email || s.contact || "[el. paštas]"}. Ginčai sprendžiami
        derybomis, o nepavykus – Lietuvos Respublikos teisės aktų nustatyta tvarka (vartotojai taip pat gali kreiptis į
        Valstybinę vartotojų teisių apsaugos tarnybą, www.vvtat.lt).</p>
      <p className="hint">Taisyklės gali būti atnaujintos – apie esminius pakeitimus pranešime el. paštu.</p>
    </Shell>
  );
}

export function Privacy() {
  const s = useBiz();
  if (!s) return null;
  return (
    <Shell title="Privatumo politika">
      <Who s={s} />
      <h3>Kokius duomenis tvarkome</h3>
      <ul>
        <li>Paskyros duomenys: vardas / įmonės pavadinimas, el. paštas, slaptažodžio maiša (paties slaptažodžio nesaugome).</li>
        <li>Jūsų turinys: įkelti ir nufilmuoti vaizdo įrašai, nuotraukos, tekstai, įgarsinimai ir sukurti vaizdo įrašai.</li>
        <li>Naudojimo duomenys: kiek panaudota AI funkcijų (minutės, kadrai, simboliai) – planų riboms.</li>
        <li>Mokėjimai: prenumeratos būsena; kortelės duomenis tvarko Stripe.</li>
      </ul>
      <h3>Kodėl (teisinis pagrindas)</h3>
      <p>Paslaugos teikimui pagal sutartį (BDAR 6 str. 1 d. b p.) ir teisėtam interesui užtikrinti saugumą bei sąskaitų
        apskaitai (BDAR 6 str. 1 d. c, f p.).</p>
      <h3>Kam perduodame</h3>
      <ul>
        <li>Serverio paslaugos – Hetzner Online GmbH (Vokietija, ES).</li>
        <li>AI funkcijos – OpenAI (JAV) ir Google (JAV / ES): tik tai, ko reikia funkcijai (pvz. garsas titrams, tekstas įgarsinimui).</li>
        <li>El. laiškai – Brevo (Prancūzija, ES). Mokėjimai – Stripe (ES / JAV).</li>
      </ul>
      <p>Duomenų neparduodame ir nenaudojame reklamai.</p>
      <h3>Kiek saugome</h3>
      <p>Kol turite paskyrą. Ištrynus projektą – jo failai ištrinami iš karto; uždarius paskyrą – duomenys ištrinami per 30 dienų,
        išskyrus tai, ką privalome saugoti pagal įstatymus (pvz. apskaitos dokumentus).</p>
      <h3>Jūsų teisės</h3>
      <p>Galite prašyti susipažinti su savo duomenimis, juos ištaisyti, ištrinti, apriboti tvarkymą ar perkelti, taip pat
        nesutikti su tvarkymu. Rašykite: {s.biz_email || s.contact || "[el. paštas]"}. Skundą galite pateikti Valstybinei
        duomenų apsaugos inspekcijai (www.vdai.lrv.lt).</p>
      <h3>Slapukai</h3>
      <p>Naudojame tik būtiną naršyklės saugyklą prisijungimui ir nustatymams; reklaminių ar sekimo slapukų nenaudojame.</p>
    </Shell>
  );
}

export function Refund() {
  const s = useBiz();
  if (!s) return null;
  const email = s.biz_email || s.contact || "[el. paštas]";
  return (
    <Shell title="Grąžinimai ir atšaukimas">
      <Who s={s} />
      <h3>Nemokamas planas ir bandymas</h3>
      <p>Pagrindinis planas – nemokamas. {s.trial_days ? `Nemokamas ${s.trial_days} d. Premium bandymas kortelės nereikalauja; jam pasibaigus paskyra automatiškai lieka su Pagrindiniu planu ir jokie mokesčiai neimami.` : ""}</p>
      <h3>Premium prenumerata</h3>
      <p>Premium{s.price_label ? ` (${s.price_label})` : ""} mokama kas mėnesį iš anksto kortele per „Stripe“. Prenumerata
        atsinaujina automatiškai kiekvieną mėnesį, kol ją nutrauksite. Sąskaitos (kvitai) siunčiamos el. paštu ir pasiekiamos
        skiltyje „Valdyti prenumeratą“.</p>
      <h3>Kaip atšaukti prenumeratą</h3>
      <ul>
        <li>Bet kada patys: „Mano projektai“ → „Valdyti prenumeratą / sąskaitas“ → „Atšaukti“.</li>
        <li>Arba parašykite el. paštu {email} – atšauksime per 1 darbo dieną.</li>
      </ul>
      <p>Atšaukus Premium galioja iki apmokėto laikotarpio pabaigos, vėliau mokestis nebeimamas, o paskyra lieka su
        Pagrindiniu planu. Jūsų projektai ir video neištrinami.</p>
      <h3>14 dienų atsisakymo teisė</h3>
      <p>Jei esate vartotojas, per 14 dienų nuo pirmojo Premium apmokėjimo galite atsisakyti sutarties be priežasties –
        parašykite {email}. Jei per šį laiką AI funkcijomis dar nesinaudojote – grąžiname visą sumą. Jei jau naudojotės,
        pagal Lietuvos Respublikos civilinį kodeksą grąžiname sumą, atskaičius proporcingą dalį už jau suteiktas paslaugas
        (panaudotą laikotarpį).</p>
      <h3>Kiti atvejai</h3>
      <ul>
        <li>Jei dėl mūsų kaltės Studija ilgiau nei 48 val. neveikė ar AI funkcijos nebuvo suteiktos – parašykite, ir
          grąžinsime proporcingą sumą arba pratęsime prenumeratą.</li>
        <li>Klaidingai ar dvigubai nuskaičiuoti pinigai grąžinami visada.</li>
        <li>Kitais atvejais jau prasidėjusio mėnesio mokestis negrąžinamas, bet prenumeratą galite nutraukti, kad kitas
          mėnuo nebūtų apmokestintas.</li>
      </ul>
      <h3>Kaip grąžinami pinigai</h3>
      <p>Pinigus grąžiname per 14 dienų nuo prašymo patvirtinimo – į tą pačią kortelę, kuria mokėjote. Bankui pervesti
        lėšas gali prireikti dar 5–10 darbo dienų.</p>
      <p className="hint">Ginčai sprendžiami derybomis, o nepavykus – Lietuvos Respublikos teisės aktų nustatyta tvarka;
        vartotojai gali kreiptis į Valstybinę vartotojų teisių apsaugos tarnybą (www.vvtat.lt).</p>
    </Shell>
  );
}
