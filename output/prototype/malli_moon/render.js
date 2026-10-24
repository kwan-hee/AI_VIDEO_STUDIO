const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');
const [,, html, mode, out, fpsArg] = process.argv;
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto('file://' + path.resolve(html) + '?capture');
  await page.evaluate(() => document.fonts.ready);
  if (mode === 'stills') {
    for (const t of [3, 9, 13.5, 18, 22.3]) {
      await page.evaluate(t => render(t), t);
      await page.screenshot({ path: `${out}/still_${String(t).replace('.', '_')}.jpg`, quality: 85 });
    }
  } else {
    const fps = +fpsArg || 24;
    const dur = await page.evaluate(() => DURATION);
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', '-',
      '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-preset', 'medium', out], { stdio: ['pipe', 'inherit', 'inherit'] });
    const n = Math.round(dur * fps);
    const t0 = Date.now();
    for (let i = 0; i < n; i++) {
      await page.evaluate(t => render(t), i / fps);
      const buf = await page.screenshot({ type: 'jpeg', quality: 92 });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
      if (i % 96 === 0) console.log(`frame ${i}/${n} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    }
    ff.stdin.end();
    await new Promise(r => ff.on('close', r));
  }
  await browser.close();
})();
