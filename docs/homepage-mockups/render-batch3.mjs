import { chromium } from 'playwright';
import { fileURLToPath } from 'url'; import path from 'path';
const dir = path.dirname(fileURLToPath(import.meta.url));
const shots = [
  // remaining new screens — dark mobile
  ['dashboard-v3.html','dashboard-v3-mobile.png',430,false],
  ['state-early.html','state-early-mobile.png',430,false],
  ['results-myround.html','results-myround-mobile.png',430,false], // re-render w/ filter bar
  // light (hybrid) variants of key screens
  ['dashboard-v3.html','dashboard-v3-light.png',430,true],
  ['state-early.html','state-early-light.png',430,true],
  ['results-myround.html','results-myround-light.png',430,true],
  ['results-match.html','results-match-light.png',430,true],
  ['results-knockout.html','results-knockout-light.png',430,true],
  ['leaderboard.html','leaderboard-light.png',430,true],
  ['landing-pretournament.html','landing-pretournament-light.png',430,true],
  // desktop (dark) for wide screens
  ['leaderboard.html','leaderboard-desktop.png',1100,false],
  ['results-season.html','results-season-desktop.png',1000,false],
  ['entry-detail.html','entry-detail-desktop.png',1000,false],
];
const browser = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
for (const [file,name,w,hybrid] of shots){
  const page = await browser.newPage({ viewport:{width:w,height:900}, deviceScaleFactor:2 });
  await page.goto('file://'+path.join(dir,file),{waitUntil:'networkidle'});
  if(hybrid) await page.evaluate(()=>document.body.classList.add('hybrid'));
  await page.evaluate(()=>document.fonts.ready); await page.waitForTimeout(700);
  await page.screenshot({ path:path.join(dir,name), fullPage:true });
  console.log('wrote',name); await page.close();
}
await browser.close();
