// 逐帧导出：playwright 驱动本机页面，帧号驱动而非真实时间（确定性）
// 用法: node export-frames.mjs <工程目录> [--fps 30] [--scale 1]
// 依赖: playwright（npm i playwright && npx playwright install chromium 或 channel:'chrome'）
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';

const dir = path.resolve(process.argv[2] || '.');
const FPS = 30;
const args = process.argv.slice(3);
const scale = args.includes('--scale') ? Number(args[args.indexOf('--scale') + 1]) : 1;

const browser = await chromium.launch({ channel: 'chrome', args: ['--force-color-profile=srgb'] });
const page = await browser.newPage({ viewport: { width: 1920 * scale, height: 1080 * scale }, deviceScaleFactor: scale });
await page.goto('file://' + path.join(dir, 'index.html'));
await page.waitForFunction('window.READY === true', null, { timeout: 60_000 });  // 字体没就绪=挂起，不许静默
const dur = await page.evaluate('window.TL.DUR');
const total = Math.round(dur * FPS);
const outDir = path.join(dir, 'frames');
fs.mkdirSync(outDir, { recursive: true });
for (let f = 0; f < total; f++) {
  const t = f / FPS;
  await page.evaluate(tt => window.render(tt), t);
  await page.screenshot({ path: path.join(outDir, `f${String(f).padStart(5, '0')}.png`) });
  if (f % 150 === 0) console.log(`frame ${f}/${total}`);
}
await browser.close();
console.log(`OK ${total} frames -> ${outDir}`);
