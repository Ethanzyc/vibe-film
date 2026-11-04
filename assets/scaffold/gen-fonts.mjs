// Google Fonts css2 子集下载：只拉用到的字形（&text=），自托管防渲染中途加载
// 用法: node gen-fonts.mjs "本片全部中英文字幕+微文案" <输出目录> [字体族]
// 如需代理: export https_proxy=http://127.0.0.1:<port>
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';

const text = process.argv[2];
const out = process.argv[3] || 'fonts';
const family = process.argv[4] || 'Noto+Serif+SC:wght@600;900';
if (!text) { console.error('usage: node gen-fonts.mjs <text> <outdir> [family]'); process.exit(1); }
fs.mkdirSync(out, { recursive: true });
const url = `https://fonts.googleapis.com/css2?family=${family}&text=${encodeURIComponent(text)}`;
const css = execFileSync('curl', ['-s', '-L', url,
  '-H', 'User-Agent: Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36'], { encoding: 'utf8' });
let i = 0;
for (const m of css.matchAll(/src:\s*url\((https:[^)]+)\)\s*format\('woff2'\)/g)) {
  const file = `${out}/f${i++}.woff2`;
  execFileSync('curl', ['-s', '-L', '-o', file, m[1]]);
  console.log('woff2 ->', file);
}
fs.writeFileSync(`${out}/fonts.css`, css.replace(/https:[^)]+/g, u => `local`)); // 提示：改写为本地引用
console.log('DONE（fonts.css 里的 URL 需替换为本地文件路径后引入 index.html）');
