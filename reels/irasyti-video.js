// Įrašo reelsą į MP4 (1080x1920, 30 kadrų/s) Facebook / Instagram reelsams.
// Naudojimas: node reels/irasyti-video.js [išvesties.mp4]
// Reikia: playwright ir ffmpeg.
const { chromium } = require("playwright");
const { spawn } = require("child_process");
const path = require("path");

const FPS = 30;
const SLIDES = 7;
const SLIDE_MS = 6500;
const TOTAL_MS = SLIDES * SLIDE_MS;
const out = process.argv[2] || path.join(__dirname, "di-naujienos-reels.mp4");

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  const page = await browser.newPage({ viewport: { width: 405, height: 720 }, deviceScaleFactor: 1080 / 405 });

  await page.goto("file://" + path.join(__dirname, "index.html") + "?video=1");
  await page.evaluate(() => document.fonts.ready);

  const ffmpeg = spawn("ffmpeg", [
    "-y", "-f", "image2pipe", "-framerate", String(FPS), "-i", "-",
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow",
    "-movflags", "+faststart", out,
  ], { stdio: ["pipe", "inherit", "inherit"] });

  const step = 1000 / FPS;
  const frames = Math.round(TOTAL_MS / step);
  for (let f = 0; f < frames; f++) {
    // Laiką ir CSS animacijas pastumiame tiksliai vienu kadru
    await page.evaluate(dt => window.renderFrame(dt), f === 0 ? 0 : step);
    const img = await page.screenshot({ type: "jpeg", quality: 95 });
    if (!ffmpeg.stdin.write(img)) await new Promise(r => ffmpeg.stdin.once("drain", r));
    if (f % 150 === 0) console.log(`kadras ${f}/${frames}`);
  }
  ffmpeg.stdin.end();
  await new Promise(r => ffmpeg.on("close", r));
  await browser.close();
  console.log("Įrašyta:", out);
})();
