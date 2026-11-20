// Renders reel.html to reel.mp4 (1080x1920, 30fps) without audio (voice-over is recorded separately). Usage: node render.js
const {chromium}=require('playwright'); const {spawn}=require('child_process'); const path=require('path');
const FPS=30, DUR=32, dir=__dirname;
(async()=>{
  const b=await chromium.launch(); const p=await b.newPage({viewport:{width:1080,height:1920}});
  await p.goto('file://'+path.join(dir,'reel.html')); await p.evaluate(()=>document.fonts.ready);
  const ff=spawn('ffmpeg',['-v','error','-y','-f','image2pipe','-framerate',String(FPS),'-i','-',
    '-t',String(DUR),
    '-c:v','libx264','-pix_fmt','yuv420p','-crf','18','-preset','medium','-an','-movflags','+faststart',
    path.join(dir,'reel.mp4')],{stdio:['pipe','inherit','inherit']});
  for(let i=0;i<FPS*DUR;i++){ await p.evaluate(t=>render(t),i/FPS); ff.stdin.write(await p.screenshot({type:'jpeg',quality:92})); }
  ff.stdin.end(); await new Promise(r=>ff.on('close',r)); await b.close();
})();
