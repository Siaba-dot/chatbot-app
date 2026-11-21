// Ryšys su API serveriu (api/server.py). Žetonas laikomas naršyklėje.
const KEY = "reels_token";

export function getToken() {
  try { return localStorage.getItem(KEY) || ""; } catch { return ""; }
}
export function setToken(t) {
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* privatus langas */ }
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch("/api" + path, {
    method,
    headers: { ...(body ? { "Content-Type": "application/json" } : {}),
               ...(getToken() ? { Authorization: "Bearer " + getToken() } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* tuščias atsakymas */ }
  if (!res.ok) {
    if (res.status === 401 && path !== "/login") { setToken(""); window.dispatchEvent(new Event("logout")); }
    const d = data && data.detail;
    throw new ApiError(res.status, typeof d === "string" ? d : "Klaida (" + res.status + ")");
  }
  return data;
}

// Failo įkėlimas su eiga (XHR – fetch neturi įkėlimo eigos)
export function upload(path, file, { recorded = false, onProgress } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api" + path);
    xhr.setRequestHeader("Authorization", "Bearer " + getToken());
    xhr.upload.onprogress = e => e.lengthComputable && onProgress && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(xhr.status, (data && data.detail) || "Nepavyko įkelti"));
    };
    xhr.onerror = () => reject(new ApiError(0, "Nutrūko ryšys"));
    const fd = new FormData();
    fd.append("file", file, file.name || (recorded ? "irasas.webm" : "failas"));
    fd.append("recorded", recorded ? "true" : "false");
    xhr.send(fd);
  });
}

// Failų adresai (video, viršelis, plytelės) – žetonas adrese, kad veiktų <img>/<video>
export function fileUrl(path, extra = "") {
  return "/api" + path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(getToken()) + extra;
}

export function waitJob(jobId, onUpdate) {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const j = await api("/jobs/" + jobId);
        onUpdate && onUpdate(j);
        if (j.status === "done") return resolve(j);
        if (j.status === "error") return reject(new ApiError(500, j.message));
        setTimeout(tick, 1200);
      } catch (e) { reject(e); }
    };
    tick();
  });
}
