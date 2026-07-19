import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';

const dir = path.dirname(fileURLToPath(import.meta.url));
const url = 'file://' + path.join(dir, 'dashboard.html');

const shots = [
  { name: 'dashboard-dark.png',   width: 1280, theme: 'premium-night', full: true },
  { name: 'dashboard-light.png',  width: 1280, theme: 'hybrid',        full: true },
  { name: 'dashboard-mobile.png', width: 390,  theme: 'premium-night', full: true },
];

const browser = await chromium.launch({
  executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
});
for (const s of shots) {
  const page = await browser.newPage({ viewport: { width: s.width, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'networkidle' });
  if (s.theme === 'hybrid') await page.evaluate(() => document.body.classList.add('hybrid'));
  await page.waitForTimeout(600); // let fonts + flags settle
  await page.screenshot({ path: path.join(dir, s.name), fullPage: s.full });
  console.log('wrote', s.name);
  await page.close();
}
await browser.close();
