#!/usr/bin/env node
import { createServer } from 'node:http';
import { mkdir, readFile } from 'node:fs/promises';
import { dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const APP = join(dirname(fileURLToPath(import.meta.url)), '..');
const ROOT = join(APP, 'www');
const OUT = join(APP, 'app-store/screenshots/iphone-6.9');
const VIEWPORT = { width: 430, height: 932 };
const SCALE = 3;
const MIME = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'text/javascript',
  '.png': 'image/png',
  '.json': 'application/json',
};

await mkdir(OUT, { recursive: true });

const server = createServer(async (req, res) => {
  try {
    const path = req.url === '/' ? 'index.html' : decodeURIComponent(req.url.split('?')[0].replace(/^\//, ''));
    const body = await readFile(join(ROOT, path));
    res.writeHead(200, { 'content-type': MIME[extname(path)] || 'application/octet-stream' });
    res.end(body);
  } catch {
    res.writeHead(404);
    res.end();
  }
});

await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
const url = `http://127.0.0.1:${server.address().port}/`;

function addCaption(page, kicker, headline) {
  return page.evaluate(({ kicker, headline }) => {
    document.querySelector('[data-shot-caption]')?.remove();
    const el = document.createElement('div');
    el.dataset.shotCaption = 'true';
    el.innerHTML = `<span>${kicker}</span><strong>${headline}</strong>`;
    Object.assign(el.style, {
      position: 'fixed',
      left: '20px',
      right: '20px',
      bottom: '30px',
      zIndex: '9999',
      padding: '14px 16px 15px',
      borderRadius: '18px',
      background: 'rgba(255,253,248,0.96)',
      border: '1px solid rgba(230,225,214,0.9)',
      boxShadow: '0 18px 42px rgba(43,39,34,0.16)',
      color: '#2b2722',
      fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif',
      pointerEvents: 'none',
    });
    const label = el.querySelector('span');
    Object.assign(label.style, {
      display: 'block',
      marginBottom: '4px',
      color: '#6b645b',
      fontSize: '11px',
      fontWeight: '800',
      letterSpacing: '0.08em',
      textTransform: 'uppercase',
    });
    const strong = el.querySelector('strong');
    Object.assign(strong.style, {
      display: 'block',
      fontSize: '19px',
      lineHeight: '1.12',
      letterSpacing: '0',
    });
    document.body.appendChild(el);
  }, { kicker, headline });
}

async function reset(page) {
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.evaluate(() => {
    localStorage.clear();
    document.querySelectorAll('[data-shot-caption]').forEach((el) => el.remove());
  });
  await page.reload({ waitUntil: 'networkidle' });
}

async function setCards(page, state) {
  await page.evaluate((state) => {
    const byId = (id) => document.getElementById(id);
    ['auto-card', 'reconnect-card', 'connect-card'].forEach((id) => {
      const el = byId(id);
      if (el) el.hidden = true;
    });
    if (state.auto) {
      byId('auto-card').hidden = false;
      byId('auto-target').textContent = state.url || 'https://clawed.macxlabs.app';
    }
    if (state.reconnect) {
      byId('reconnect-card').hidden = false;
      byId('reconnect-url').textContent = state.url || 'http://192.168.1.42:8000';
    }
    if (state.connect) {
      byId('connect-card').hidden = false;
    }
    if (state.input !== undefined) {
      byId('server-url').value = state.input;
    }
    if (state.error) {
      const err = byId('connect-error');
      err.hidden = false;
      err.textContent = state.error;
      byId('server-url').setAttribute('aria-invalid', 'true');
    }
  }, state);
}

async function screenshot(page, fileName, kicker, headline) {
  await addCaption(page, kicker, headline);
  await page.waitForTimeout(120);
  await page.screenshot({ path: join(OUT, fileName), fullPage: false });
}

let browser;
try {
  browser = await chromium.launch();
  const ctx = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: SCALE,
    isMobile: true,
    hasTouch: true,
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (err) => errors.push(String(err)));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });

  await reset(page);
  await setCards(page, { connect: true });
  await screenshot(page, '01-pair-from-mac.png', 'Phone companion', 'Scan the Mac QR code and open your classroom workspace.');

  await reset(page);
  await setCards(page, { connect: true, input: 'http://192.168.1.42:8000' });
  await screenshot(page, '02-type-local-address.png', 'Local-first setup', 'Prefer typing? Paste the address shown by the Mac app.');

  await reset(page);
  await setCards(page, { reconnect: true, connect: true, url: 'http://192.168.1.42:8000' });
  await screenshot(page, '03-reconnect.png', 'One-tap return', 'After pairing, Claw-ED remembers your trusted server.');

  await reset(page);
  await setCards(page, { auto: true, url: 'https://clawed.macxlabs.app' });
  await screenshot(page, '04-opening-classroom.png', 'Fast relaunch', 'Open straight back into your Claw-ED workspace.');

  await reset(page);
  await setCards(page, {
    connect: true,
    input: 'teacher-mac.local:8000',
    error: 'Use the iPhone Camera to scan the Mac QR code, or type the address shown in the Mac menu-bar app.',
  });
  await screenshot(page, '05-camera-or-address.png', 'No account required', 'Your lessons stay between this device and your Mac.');

  await ctx.close();
  if (errors.length) throw new Error(`console errors: ${errors.slice(0, 3).join(' | ')}`);
  console.log(JSON.stringify({ ok: true, outDir: OUT, screenshots: 5, size: '1290x2796' }, null, 2));
} finally {
  if (browser) await browser.close();
  server.close();
}
