import { chromium } from 'playwright';
import { fileURLToPath } from 'url'; import path from 'path';
const dir = path.dirname(fileURLToPath(import.meta.url));
const url = 'file://' + path.join(dir, 'dashboard-v2.html');
const shots = [
  { name:'dashboard-v2-dark.png', width:1280, theme:'premium-night' },
  { name:'dashboard-v2-mobile.png', width:390, theme:'premium-night' },
];
const browser = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
for (const s of shots){
  const page = await browser.newPage({ viewport:{width:s.width,height:900}, deviceScaleFactor:2 });
  await page.goto(url,{waitUntil:'networkidle'});
  if(s.theme==='hybrid') await page.evaluate(()=>document.body.classList.add('hybrid'));
  await page.waitForTimeout(600);
  await page.screenshot({ path:path.join(dir,s.name), fullPage:true });
  console.log('wrote',s.name); await page.close();
}
await browser.close();
