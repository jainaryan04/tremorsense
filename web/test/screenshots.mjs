// Captures app screenshots for the docs in several states.
//   (cd web && python3 -m http.server 8765 &) ; node web/test/screenshots.mjs
// Needs Playwright with Chromium installed.
import { mkdirSync } from "node:fs";

const PW = process.env.PLAYWRIGHT_MODULE || "playwright";
const pw = await import(PW);
const { chromium } = pw.default ?? pw;
const URL_ = process.env.APP_URL || "http://localhost:8765/";
const OUT = new URL("../../docs/screenshots/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();

async function phone(scheme = "light") {
  const p = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, colorScheme: scheme });
  await p.goto(URL_);
  await p.evaluate(() => localStorage.clear());
  await p.reload();
  await p.waitForTimeout(500);
  return p;
}

const card = (p, n) => p.locator("main > section:visible").nth(n);
const wait = (p, s) => p.waitForTimeout(s * 1000);

let p = await phone();
await p.screenshot({ path: OUT + "01_home.png" });

await p.click('[data-grade="2"]');
await p.click("#start");
await wait(p, 8);
await p.screenshot({ path: OUT + "02_live_grade2.png" });
await card(p, 1).screenshot({ path: OUT + "03_card_grade2_pd.png" });

await p.click('[data-grade="4"]');
await wait(p, 7);
await card(p, 1).screenshot({ path: OUT + "04_card_grade4_pd.png" });

await p.click('[data-type="essential"]');
await p.click('[data-grade="3"]');
await wait(p, 8);
await card(p, 1).screenshot({ path: OUT + "05_card_grade3_et.png" });

await p.click('[data-grade="0"]');
await wait(p, 7);
await card(p, 1).screenshot({ path: OUT + "06_card_grade0.png" });

await p.click('[data-type="parkinsonian"]');
await p.click('[data-grade="3"]');
await p.click('[data-activity="gait"]');
await wait(p, 7);
await card(p, 1).screenshot({ path: OUT + "07_card_walking.png" });

await p.click('[data-activity="vehicle"]');
await wait(p, 7);
await card(p, 1).screenshot({ path: OUT + "08_card_vehicle.png" });

await p.click('[data-activity="voluntary"]');
await wait(p, 7);
await card(p, 1).screenshot({ path: OUT + "09_card_using_hand.png" });

await p.click('[data-activity="still"]');
await wait(p, 6);
await card(p, 2).screenshot({ path: OUT + "10_demo_controls.png" });
await p.click("#calibrate");
await wait(p, 9);
await card(p, 3).screenshot({ path: OUT + "11_calibrating.png" });

await p.click("#demo-data");
await wait(p, 4);
await card(p, 4).screenshot({ path: OUT + "12_medication.png" });
await p.screenshot({ path: OUT + "13_full_page.png", fullPage: true });
await p.close();

p = await phone("dark");
await p.click('[data-grade="3"]');
await p.click("#start");
await wait(p, 8);
await p.screenshot({ path: OUT + "14_dark_live.png" });
await p.click("#demo-data");
await wait(p, 4);
await card(p, 4).screenshot({ path: OUT + "15_dark_medication.png" });
await p.close();

const d = await browser.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
await d.goto(URL_);
await d.click('[data-grade="2"]');
await d.click("#start");
await d.waitForTimeout(8000);
await d.screenshot({ path: OUT + "16_desktop.png" });

// Test cases (app only, no Arduino), run on a fast-forwarded clock. Each case
// shows for 6 s, runs for 14 s (the last one 20 s) and shows its result for 6 s.
const t = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });
await t.clock.install();
await t.goto(URL_);
await t.evaluate(() => localStorage.clear());
await t.reload();
await t.waitForTimeout(300);
await t.addStyleTag({ content: "#flash { display: none }" });
await t.click('[data-source="tests"]');
await t.uncheck("#tests-uno");
await t.click("#start");
await t.waitForTimeout(300);
const CASE_S = 26;
async function at(sec) {
  const now = await t.evaluate(() => performance.now());
  await t.clock.runFor(Math.max(0, sec * 1000 - now + 300));
}
// Every case near its end, once cues have settled, then its result (shown for
// 6 s after the case). Case 7 also while still cueing, before walking at 12 s.
for (let i = 0; i < 7; i++) {
  const start = i * CASE_S + 6, len = i === 6 ? 20 : 14;
  if (i === 6) {
    await at(start + 10);
    await card(t, 1).screenshot({ path: OUT + "tc7a_card.png" });
  }
  await at(start + len - 2);
  await card(t, 1).screenshot({ path: OUT + `tc${i + 1}_card.png` });
  await at(start + len + 2);
  await t.locator(".tc-now").screenshot({ path: OUT + `tc${i + 1}_case.png` });
}
for (let k = 0; k < 6; k++) await t.clock.runFor(10000);
await t.locator("#tests-panel").screenshot({ path: OUT + "18_test_cases.png" });
await t.locator("#tc-list").screenshot({ path: OUT + "21_test_results.png" });
await t.close();

await browser.close();
console.log("screenshots in", OUT);
