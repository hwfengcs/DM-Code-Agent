/** Capture the real generated exhibit. Requires Playwright and ffmpeg; see docs/demo-site.md. */
import assert from "node:assert/strict";
import { mkdir, copyFile, writeFile } from "node:fs/promises";
import { resolve, isAbsolute } from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

const moduleName = process.env.PLAYWRIGHT_MODULE || "playwright";
const { chromium } = await import(
  isAbsolute(moduleName) ? pathToFileURL(moduleName).href : moduleName
);
const base = process.env.DEMO_URL || "http://127.0.0.1:8876/";
const media = resolve("docs/media");
const capture = resolve("build/media-capture");
await mkdir(media, { recursive: true });
await mkdir(capture, { recursive: true });
const browser = await chromium.launch({
  channel: process.env.BROWSER_CHANNEL || "chrome",
  headless: true,
});
const errors = [];
const checked = [];

async function validate(page) {
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400)
      errors.push(`${response.status()} ${response.url()}`);
  });
  await page.goto(base);
  await page.evaluate(() => document.fonts.ready);
  const report = page.frameLocator("#report-frame");
  await report.getByText("Exit 0", { exact: true }).waitFor();
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    true,
  );
  await page.locator('[data-report="unverified"]').click();
  await report.getByText("Verification gap:", { exact: false }).waitFor();
  assert.equal(
    await page.locator("#open-report").getAttribute("href"),
    "unverified.html",
  );
  await page.locator('[data-report="verified"]').click();
  await report.getByText("Exit 0", { exact: true }).waitFor();
  assert.equal(
    await page.locator('[data-report="verified"]').getAttribute("aria-pressed"),
    "true",
  );
  checked.push({
    viewport: page.viewportSize(),
    checks: "layout, both reports, link and selected state",
  });
}

try {
  const desktop = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    reducedMotion: "reduce",
  });
  await validate(desktop);
  await desktop.evaluate(() => scrollTo(0, 0));
  await desktop.screenshot({
    path: resolve(capture, "desktop.png"),
    fullPage: true,
  });
  await desktop.screenshot({
    path: resolve(media, "social-preview.png"),
    clip: { x: 0, y: 0, width: 1440, height: 756 },
  });
  await desktop.locator("#demo").scrollIntoViewIfNeeded();
  await desktop.screenshot({ path: resolve(media, "demo-preview.png") });
  const mobile = await browser.newPage({
    viewport: { width: 390, height: 844 },
    reducedMotion: "reduce",
  });
  await validate(mobile);
  await mobile.evaluate(() => scrollTo(0, 0));
  await mobile.screenshot({
    path: resolve(capture, "mobile.png"),
    fullPage: true,
  });
  // A standalone report must load without requesting fonts, scripts, images, or remote APIs.
  const standalone = await browser.newPage();
  const requests = [];
  standalone.on("request", (request) => requests.push(request.url()));
  await standalone.goto(new URL("verified.html", base).href);
  await standalone.getByText("Exit 0", { exact: true }).waitFor();
  assert.equal(requests.length, 1, `Report made extra requests: ${requests}`);
  assert.deepEqual(errors, []);
  await writeFile(
    resolve(capture, "qa.json"),
    JSON.stringify(
      { checked, errors, standaloneRequests: requests.length },
      null,
      2,
    ),
  );

  if (process.argv.includes("--record")) {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
      reducedMotion: "reduce",
      recordVideo: { dir: capture, size: { width: 1280, height: 900 } },
    });
    const page = await context.newPage();
    await page.goto(base);
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => {
      const caption = document.createElement("div");
      caption.id = "walkthrough-caption";
      caption.style.cssText =
        "position:fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:100;padding:15px 25px;border-radius:10px;background:#17211ff2;color:white;font:500 18px/1.5 Geist,sans-serif;box-shadow:0 4px 20px #0002;text-align:center;width:max-content;max-width:95%;pointer-events:none";
      document.body.append(caption);
    });
    const caption = async (text) =>
      page.locator("#walkthrough-caption").evaluate((el, text) => {
        el.textContent = text;
      }, text);
    const pause = (ms) => page.waitForTimeout(ms);
    const scrollReport = async (selector) => {
      const frame = page.frameLocator("#report-frame");
      await frame
        .locator(selector)
        .first()
        .evaluate((el) => el.scrollIntoView({ block: "start" }));
    };
    await caption(
      "Inspect the run behind the answer. Scripted decisions. Real tools and tests.",
    );
    await pause(6500);
    await page
      .locator("#demo")
      .evaluate((el) => el.scrollIntoView({ block: "start" }));
    await scrollReport("section.section");
    await caption(
      "The repair runs four local checks: first failing, then passing.",
    );
    await pause(7500);
    await scrollReport(".timeline");
    await caption(
      "Read the execution trail and the exact replacement excerpt.",
    );
    await pause(8000);
    await page.locator('[data-report="unverified"]').click();
    await page.frameLocator("#report-frame").locator(".notice").waitFor();
    await scrollReport(".notice");
    await caption(
      "Same edit. No test run. The report flags the verification gap.",
    );
    await pause(8000);
    await page
      .locator("#start")
      .evaluate((el) => el.scrollIntoView({ block: "start" }));
    await caption(
      "Run it locally without an API key. Export one HTML file to share.",
    );
    await pause(7500);
    const video = page.video();
    await context.close();
    const recorded = await video.path();
    await copyFile(recorded, resolve(capture, "walkthrough.webm"));
    const encode = (args) => {
      const result = spawnSync(
        "ffmpeg",
        ["-hide_banner", "-loglevel", "error", "-y", "-i", recorded, ...args],
        { encoding: "utf8" },
      );
      if (result.error) throw result.error;
      assert.equal(result.status, 0, result.stderr);
    };
    encode([
      "-c:v",
      "libx264",
      "-crf",
      "23",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      "-an",
      resolve(media, "demo-walkthrough.mp4"),
    ]);
    encode([
      "-filter_complex",
      "[0:v]fps=8,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3",
      "-loop",
      "0",
      resolve(media, "demo-walkthrough.gif"),
    ]);
  }
  console.log(`Browser checks passed. Screenshots: ${media}. QA: ${capture}.`);
} finally {
  await browser.close();
}
