import { chromium } from 'playwright';
import { fileURLToPath } from 'url'; import path from 'path';
const dir = path.dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ viewport:{width:430,height:900}, deviceScaleFactor:2 });
await page.goto('file://'+path.join(dir,'multi-entry.html'),{waitUntil:'networkidle'});
await page.evaluate(()=>document.fonts.ready); await page.waitForTimeout(800);
await page.screenshot({ path:path.join(dir,'multi-entry.png'), fullPage:true });
console.log('done'); await browser.close();
