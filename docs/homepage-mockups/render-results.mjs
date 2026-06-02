import { chromium } from 'playwright';
import { fileURLToPath } from 'url'; import path from 'path';
const dir = path.dirname(fileURLToPath(import.meta.url));
const shots = [
  { file:'results-myround.html', name:'results-myround-mobile.png', width:390 },
  { file:'results-myround.html', name:'results-myround-desktop.png', width:900 },
  { file:'results-match.html',   name:'results-match-mobile.png',   width:390 },
  { file:'results-match.html',   name:'results-match-desktop.png',  width:900 },
];
const browser = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
for (const s of shots){
  const page = await browser.newPage({ viewport:{width:s.width,height:900}, deviceScaleFactor:2 });
  await page.goto('file://'+path.join(dir,s.file),{waitUntil:'networkidle'});
  await page.waitForTimeout(500);
  await page.screenshot({ path:path.join(dir,s.name), fullPage:true });
  console.log('wrote',s.name); await page.close();
}
await browser.close();
