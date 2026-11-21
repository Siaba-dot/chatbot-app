import React, { useState } from "react";

// „Gintaro istorija“ – kaip senojoje studijoje (išskleidžiama)
export default function Story() {
  const [open, setOpen] = useState(false);
  return (
    <div className="story">
      <button type="button" className="story-head" onClick={() => setOpen(o => !o)} aria-expanded={open}>
        <span>{open ? "▾" : "▸"}</span> ✦ Gintaro istorija
      </button>
      {open && (
        <div className="story-body">
          <p>Senovėje Baltijos jūros dugne stovėjo gintaro rūmai. Juose gyveno jūrų deivė <b>Jūratė</b>. Ji pamilo
            paprastą žvejį <b>Kastytį</b>, tačiau griaustinio dievas, supykęs dėl tos meilės, sudaužė jos rūmus. Nuo
            tada audros į Lietuvos krantą išmeta gintaro gabalėlius – tos meilės nuolaužas.</p>
          <p>Bet gintaras slepia dar vieną paslaptį. Prieš milijonus metų lašas sakų sustabdė akimirką – lapelį, oro
            burbuliuką, saulės spindulį – ir išsaugojo ją amžinai. Todėl kiekvienas gintaro gabalėlis yra laiko
            sustabdyta istorija.</p>
          <p>Šiandien mūsų akimirkos gyvena trumpuose video. Jos greitai prabėga ekrane, nors kiekviena verta būti
            išsaugota gražiai.</p>
          <p>Taip gimė <b>Reels montavimo studija</b> – lietuviška studija su Baltijos gintaro dvasia. Ji iš jūsų
            video išsaugo tai, kas vertingiausia: iškerpa tuščias pauzes, nušveičia garsą, suteikia vaizdui šiltą
            gintaro šviesą ir paverčia kasdienį įrašą žibančia istorija.</p>
          <p>Kaip jūra išneša gintarą į krantą, taip studija iškelia į šviesą geriausias jūsų akimirkas.</p>
          <p className="story-end">Jūsų akimirkos – kaip gintaras: išsaugotos gražiausios.</p>
        </div>
      )}
    </div>
  );
}
