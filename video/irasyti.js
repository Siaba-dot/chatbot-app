// Įrašo canvas animaciją į MP4 (1080x1920, 30 kadrų/s).
// Naudojimas: node video/irasyti.js video/ragana.html [išvesties.mp4] [papildomi URL parametrai]
// Puslapis turi pateikti window.ready, window.DURATION ir window.renderAt(t).
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path");

const FPS = 30;
const html = path.resolve(process.argv[2]);
const out = process.argv[3] || html.replace(/\.html$/, ".mp4");
const extra = process.argv[4] ? "&" + process.argv[4] : "";

(async () => {
  // Leidžia canvas eksportuoti vietines nuotraukas (file://)
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ["--allow-file-access-from-files"],
  });
  const page = await browser.newPage();
  await page.goto("file://" + html + "?video=1" + extra);
  const duration = await page.evaluate(() => window.ready.then(() => window.DURATION));

  const ffmpeg = spawn("ffmpeg", [
    "-y", "-v", "error", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow",
    "-movflags", "+faststart", out,
  ], { stdio: ["pipe", "inherit", "inherit"] });

  const frames = Math.round(duration * FPS);
  for (let f = 0; f < frames; f++) {
    const data = await page.evaluate(t => {
      window.renderAt(t);
      return document.querySelector("canvas").toDataURL("image/jpeg", 0.95).split(",")[1];
    }, f / FPS);
    if (!ffmpeg.stdin.write(Buffer.from(data, "base64"))) await new Promise(r => ffmpeg.stdin.once("drain", r));
  }
  ffmpeg.stdin.end();
  await new Promise(r => ffmpeg.on("close", r));
  await browser.close();
  console.log("Įrašyta:", out);
})();
