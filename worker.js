// Murga rates: serves the app (public/) and keeps the rates in Cloudflare KV.
//   GET  /rates.json  -> rates for the app (KV, or the seed file in public/ until the first save)
//   GET  /api/rates   -> same, always fresh (used by admin.html)
//   POST /api/rates   -> save rates (needs the ADMIN_PASSWORD secret)
const HDR = { "content-type": "application/json; charset=utf-8", "cache-control": "no-cache" };
const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: HDR });
const text = (x, n = 60) => String(x == null ? "" : x).trim().slice(0, n);
const price = (x) => { const v = Number(x); return v > 0 && v < 100000 ? Math.round(v * 10) / 10 : null; };
const DELHI = "दिल्ली";

async function load(env, req, fresh) {
  const s = await env.RATES.get("rates", fresh ? undefined : { cacheTtl: 60 });
  if (s) return JSON.parse(s);
  const r = await env.ASSETS.fetch(new Request(new URL("/rates.json", req.url)));  // static seed file
  return r.ok ? await r.json() : { date: "", demo: true, cities: [], parts: [] };
}

function same(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

// set today's value; on a new day push today -> yesterday -> day before
function put(o, v, K, shift) {
  if (shift) { o[K[2]] = o[K[1]]; o[K[1]] = o[K[0]]; }
  o[K[0]] = v;
}

async function save(req, env) {
  let b;
  try { b = await req.json(); } catch (e) { return json({ error: "bad request" }, 400); }
  if (!env.ADMIN_PASSWORD) return json({ error: "ADMIN_PASSWORD secret is not set" }, 500);
  if (!same(String(b.password || ""), String(env.ADMIN_PASSWORD))) return json({ error: "wrong password" }, 401);

  const data = await load(env, req, true);
  const d = String(b.date || "");
  const limit = new Date(Date.now() + 19800000 + 86400000).toISOString().slice(0, 10);  // IST tomorrow
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d) || d > limit) return json({ error: "bad date" }, 400);
  if (data.date && d < data.date) return json({ error: "date is older than the saved rates (" + data.date + ")" }, 400);
  const shift = d > (data.date || "");

  const cities = (data.cities || []).filter((c) => !(b.remove || []).some((r) => r.city === c.city && r.state === c.state));
  for (const c of (b.cities || []).slice(0, 3000)) {
    const city = text(c.city), state = text(c.state), v = price(c.today);
    if (!city || !state || v === null) continue;
    const o = cities.find((x) => x.city === city && x.state === state);
    if (o) put(o, v, ["today", "yest", "prev"], shift);
    else cities.push({ city, state, today: v, yest: v, prev: v });
  }
  const parts = data.parts || [];
  for (const p of (b.parts || []).slice(0, 300)) {
    const g = text(p.g, 80), n = text(p.n, 80), v = price(p.t);
    if (!g || !n || v === null) continue;
    const o = parts.find((x) => x.g === g && x.n === n);
    if (o) put(o, v, ["t", "y", "p"], shift);
    else parts.push({ g, n, t: v, y: v, p: v });
  }
  // the Delhi city row follows the 2000-2200 gm live rate
  const live = parts.find((p) => p.n.startsWith("2000"));
  if (live) {
    const row = { city: DELHI, state: DELHI, today: live.t, yest: live.y, prev: live.p };
    const i = cities.findIndex((c) => c.city === DELHI && c.state === DELHI);
    if (i >= 0) cities[i] = row; else cities.push(row);
  }
  const out = { date: d, demo: false, cities, parts };
  await env.RATES.put("rates", JSON.stringify(out));
  return json(out);
}

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    if (u.pathname === "/rates.json" && req.method === "GET") return json(await load(env, req, false));
    if (u.pathname === "/api/rates") {
      if (req.method === "GET") return json(await load(env, req, true));
      if (req.method === "POST") return save(req, env);
      return json({ error: "method not allowed" }, 405);
    }
    return env.ASSETS.fetch(req);
  },
};
