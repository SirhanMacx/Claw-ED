// Claw-ED App Store Connect helper.
// Mirrors the Cascade ASC JWT auth pattern (ES256 over the .p8 read from disk).
// NEVER prints the key contents — the .p8 is only fed to crypto.sign by path.
//
// Subcommands:
//   check-app    — does an app record exist for com.macxlabs.clawed? does the bundleId exist?
//   create-app   — attempt to register bundleId + create the app record (non-interactive)
//   verify-build — poll builds for a given --version (CFBundleVersion) under the app
//
// Env overrides: ASC_KEY_ID, ASC_ISSUER_ID, ASC_KEY_PATH, ASC_BUNDLE_ID
import { createSign } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { homedir } from 'node:os';

const BUNDLE_ID = process.env.ASC_BUNDLE_ID || 'com.macxlabs.clawed';
const APP_NAME = process.env.ASC_APP_NAME || 'Claw-ED';
const KEY_ID = process.env.ASC_KEY_ID || 'K5RKF383QT';
const ISSUER_ID = process.env.ASC_ISSUER_ID || '6a02d8d5-4d1e-4f92-9936-18d05e663ff2';
const KEY_PATH = (process.env.ASC_KEY_PATH || `~/.appstoreconnect/private_keys/AuthKey_${KEY_ID}.p8`).replace(/^~\//, `${homedir()}/`);
const PRIMARY_LOCALE = process.env.ASC_PRIMARY_LOCALE || 'en-US';
const SKU = process.env.ASC_SKU || 'CLAWED001';

function b64(value) { return Buffer.from(value).toString('base64url'); }

async function token() {
  const key = await readFile(KEY_PATH, 'utf8'); // read-only; never logged
  const now = Math.floor(Date.now() / 1000);
  const input = [
    b64(JSON.stringify({ alg: 'ES256', kid: KEY_ID, typ: 'JWT' })),
    b64(JSON.stringify({ iss: ISSUER_ID, iat: now, exp: now + 1200, aud: 'appstoreconnect-v1' })),
  ].join('.');
  const sig = createSign('SHA256').update(input).end().sign({ key, dsaEncoding: 'ieee-p1363' }).toString('base64url');
  return `${input}.${sig}`;
}

async function api(jwt, path, options = {}) {
  const res = await fetch(`https://api.appstoreconnect.apple.com${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${jwt}`, 'content-type': 'application/json', ...(options.headers || {}) },
  });
  const body = await res.json().catch(async () => ({ raw: await res.text() }));
  return { ok: res.ok, status: res.status, body };
}

async function findApp(jwt) {
  const r = await api(jwt, `/v1/apps?filter[bundleId]=${encodeURIComponent(BUNDLE_ID)}&fields[apps]=name,bundleId,sku,primaryLocale`);
  if (!r.ok) throw new Error(`apps query ${r.status} ${JSON.stringify(r.body).slice(0, 600)}`);
  return r.body.data?.[0] || null;
}

async function findBundleId(jwt) {
  const r = await api(jwt, `/v1/bundleIds?filter[identifier]=${encodeURIComponent(BUNDLE_ID)}&filter[platform]=IOS&fields[bundleIds]=identifier,name,platform,seedId`);
  if (!r.ok) throw new Error(`bundleIds query ${r.status} ${JSON.stringify(r.body).slice(0, 600)}`);
  return r.body.data?.[0] || null;
}

async function cmdCheckApp() {
  const jwt = await token();
  const app = await findApp(jwt);
  let bundle = null;
  try { bundle = await findBundleId(jwt); } catch (e) { bundle = { error: e.message }; }
  console.log(JSON.stringify({
    ok: true,
    bundleId: BUNDLE_ID,
    appRecordExists: !!app,
    app: app ? { id: app.id, ...app.attributes } : null,
    bundleIdRegistered: bundle && bundle.id ? true : false,
    bundle: bundle && bundle.id ? { id: bundle.id, ...bundle.attributes } : bundle,
  }, null, 2));
}

async function cmdCreateApp() {
  const jwt = await token();
  const out = { bundleId: BUNDLE_ID, steps: [] };

  // 1) ensure bundleId exists
  let bundle = await findBundleId(jwt);
  if (!bundle) {
    const r = await api(jwt, '/v1/bundleIds', {
      method: 'POST',
      body: JSON.stringify({ data: { type: 'bundleIds', attributes: { identifier: BUNDLE_ID, name: APP_NAME.replace(/[^A-Za-z0-9 ]/g, ''), platform: 'IOS', seedId: 'Y8MX8Q77B2' } } }),
    });
    out.steps.push({ step: 'create-bundleId', ok: r.ok, status: r.status, body: r.body });
    if (r.ok) bundle = r.body.data;
  } else {
    out.steps.push({ step: 'create-bundleId', ok: true, status: 'exists', id: bundle.id });
  }

  // 2) create the app record
  let app = await findApp(jwt);
  if (!app && bundle && bundle.id) {
    const r = await api(jwt, '/v1/apps', {
      method: 'POST',
      body: JSON.stringify({
        data: {
          type: 'apps',
          attributes: { bundleId: BUNDLE_ID, name: APP_NAME, primaryLocale: PRIMARY_LOCALE, sku: SKU },
          relationships: { bundleId: { data: { type: 'bundleIds', id: bundle.id } } },
        },
      }),
    });
    out.steps.push({ step: 'create-app', ok: r.ok, status: r.status, body: r.body });
    if (r.ok) app = r.body.data;
  } else if (app) {
    out.steps.push({ step: 'create-app', ok: true, status: 'exists', id: app.id });
  }

  out.ok = !!app;
  out.app = app ? { id: app.id, ...app.attributes } : null;
  console.log(JSON.stringify(out, null, 2));
  if (!out.ok) process.exitCode = 1;
}

async function cmdVerifyBuild(version) {
  const jwt = await token();
  const app = await findApp(jwt);
  if (!app) { console.log(JSON.stringify({ ok: false, reason: 'no app record', bundleId: BUNDLE_ID }, null, 2)); process.exitCode = 1; return; }
  const r = await api(jwt, `/v1/builds?filter[app]=${app.id}&sort=-uploadedDate&limit=30&fields[builds]=version,uploadedDate,processingState,expired,usesNonExemptEncryption`);
  if (!r.ok) throw new Error(`builds query ${r.status} ${JSON.stringify(r.body).slice(0, 600)}`);
  const builds = r.body.data || [];
  const match = version ? builds.find((b) => b.attributes?.version === String(version)) : builds[0];
  console.log(JSON.stringify({
    ok: !!match,
    bundleId: BUNDLE_ID,
    app: { id: app.id, ...app.attributes },
    requestedVersion: version || '(latest)',
    matchedBuild: match ? { id: match.id, ...match.attributes } : null,
    recentBuilds: builds.slice(0, 8).map((b) => ({ id: b.id, ...b.attributes })),
  }, null, 2));
  if (!match) process.exitCode = 1;
}

const [cmd, ...rest] = process.argv.slice(2);
const versionArg = (() => { const i = rest.indexOf('--version'); return i >= 0 ? rest[i + 1] : undefined; })();
try {
  if (cmd === 'check-app') await cmdCheckApp();
  else if (cmd === 'create-app') await cmdCreateApp();
  else if (cmd === 'verify-build') await cmdVerifyBuild(versionArg);
  else { console.error('usage: node scripts/asc.mjs <check-app|create-app|verify-build [--version N]>'); process.exit(2); }
} catch (e) {
  console.error(JSON.stringify({ ok: false, error: e.message }, null, 2));
  process.exit(1);
}
