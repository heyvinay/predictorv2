import { chromium } from 'playwright';
import { fileURLToPath } from 'url'; import path from 'path';
const dir = path.dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ viewport:{width:880,height:760}, deviceScaleFactor:2 });
await page.goto('file://'+path.join(dir,'connectivity-map.html'),{waitUntil:'networkidle'});
await page.evaluate(()=>document.fonts.ready); await page.waitForTimeout(700);
await page.screenshot({ path:path.join(dir,'connectivity-map.png'), fullPage:true });
console.log('done'); await browser.close();
