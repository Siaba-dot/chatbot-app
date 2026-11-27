import React from "react";

// Balsų sąrašas pasirinkimo laukui: Google (natūralus lietuviškas tarimas) atskirai nuo OpenAI (su akcentu)
export default function VoiceOptions({ opts, google, openai }) {
  return (
    <>
      {google && (
        <optgroup label="🇱🇹 Google – natūralus lietuviškas tarimas">
          {Object.entries(opts.gemini_voices || {}).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </optgroup>
      )}
      {openai && (
        <optgroup label="OpenAI – lietuviškai su akcentu">
          {Object.entries(opts.voices || {}).map(([v, l]) => <option key={v} value={v}>{l} (su akcentu)</option>)}
        </optgroup>
      )}
    </>
  );
}
