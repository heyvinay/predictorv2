import { chromium } from 'playwright';
import { fileURLToPath } from 'url'; import path from 'path';
const dir = path.dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
for (const [file,name] of [['leaderboard.html','leaderboard-mobile.png'],['entry-detail.html','entry-detail-mobile.png']]){
  const page = await browser.newPage({ viewport:{width:430,height:900}, deviceScaleFactor:2 });
  await page.goto('file://'+path.join(dir,file),{waitUntil:'networkidle'});
  await page.evaluate(()=>document.fonts.ready); await page.waitForTimeout(800);
  await page.screenshot({ path:path.join(dir,name), fullPage:true });
  console.log('wrote',name); await page.close();
}
await browser.close();
