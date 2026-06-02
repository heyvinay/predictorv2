import { chromium } from 'playwright';
import { fileURLToPath } from 'url'; import path from 'path';
const dir = path.dirname(fileURLToPath(import.meta.url));
const shots = [
  ['results-match.html','results-match-mobile.png',390],
  ['match-upcoming.html','match-upcoming-mobile.png',390],
  ['results-myround.html','results-myround-mobile.png',390],
];
const browser = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
for (const [file,name,width] of shots){
  const page = await browser.newPage({ viewport:{width,height:900}, deviceScaleFactor:2 });
  await page.goto('file://'+path.join(dir,file),{waitUntil:'networkidle'});
  await page.evaluate(()=>document.fonts.ready); await page.waitForTimeout(1200);
  await page.screenshot({ path:path.join(dir,name), fullPage:true });
  console.log('wrote',name); await page.close();
}
await browser.close();
