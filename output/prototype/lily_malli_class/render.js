// 사용법: node render.js scene.html stills <출력폴더> "1,4.5,..."
//        node render.js scene.html video <출력.mp4> [fps]
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');
const [,, html, mode, out, arg] = process.argv;
const W = 720, H = 1280, SCALE = 1.5; // 1080x1920 출력
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: SCALE });
  page.on('pageerror', e => console.error('PAGE ERROR', e.message));
  await page.goto('file://' + path.resolve(html) + '?capture');
  await page.evaluate(() => document.fonts.ready);
  if (mode === 'stills') {
    for (const t of (arg || '1,5,9,12,16,21').split(',').map(Number)) {
      await page.evaluate(t => render(t), t);
      await page.screenshot({ path: `${out}/still_${String(t).replace('.', '_')}.jpg`, quality: 80 });
    }
  } else {
    const fps = +arg || 24;
    const dur = await page.evaluate(() => DURATION);
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium', out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const n = Math.round(dur * fps);
    for (let i = 0; i < n; i++) {
      await page.evaluate(t => render(t), i / fps);
      const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if (i % 120 === 0) console.log(`frame ${i}/${n}`);
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
  }
  await browser.close();
})();
