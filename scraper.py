"""Daily murga rate scraper -> public/rates.json (the format the PWA reads).

Sources (get permission from the sites before commercial use):
  * Poultry Bazaar state pages  -> state / city rates, Delhi lollipop
  * poultrysite.in Ghazipur     -> Delhi weight-wise rates, parts, vehicle count
Run:  pip install requests beautifulsoup4 && python scraper.py
If a source fails, that part keeps the previous rates; if everything fails the
script exits with an error and rates.json is left untouched.
"""
import json, os, re, sys, time, datetime
import requests
from bs4 import BeautifulSoup

TODAY = datetime.date.today()
OUT = os.environ.get("RATES_OUT", "public/rates.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (murga-rate-app; contact: you@example.com)"}
PB = "https://www.poultrybazaar.net/daily-rate-sheet/"
STATES = {  # english key: (hindi name, page slug)
    "Karnataka": ("कर्नाटक", "Broiler-Rates-Karnataka"),
    "Tamil Nadu": ("तमिलनाडु", "Broiler-Rates-Tamil-Nadu"),
    "Andhra Pradesh": ("आंध्र प्रदेश", "broiler-rates-andhra-pradesh"),
    "Orissa": ("ओडिशा", "broiler-rates-orissa"),
    "Maharashtra": ("महाराष्ट्र", "Broiler-Rates-Maharashtra"),
}
CITY_HI = {  # extend freely; unknown cities keep their english name
    "bangalore": "बेंगलुरु", "bengaluru": "बेंगलुरु", "mysore": "मैसूर", "shimoga": "शिवमोगा",
    "hubli": "हुबली", "mangalore": "मंगलुरु", "chennai": "चेन्नई", "namakkal": "नामक्कल",
    "coimbatore": "कोयंबटूर", "madurai": "मदुरै", "salem": "सेलम", "hyderabad": "हैदराबाद",
    "vijayawada": "विजयवाड़ा", "vizag": "विशाखापत्तनम", "visakhapatnam": "विशाखापत्तनम",
    "guntur": "गुंटूर", "bhubaneswar": "भुवनेश्वर", "cuttack": "कटक", "mumbai": "मुंबई",
    "pune": "पुणे", "nagpur": "नागपुर", "nashik": "नासिक",
}
L, P, V = "लाइव मुर्गा (वज़न अनुसार)", "पार्ट और प्रोसेस्ड", "आवक (गाड़ियों की गिनती)"
GH = [  # normalized poultrysite name -> (hindi name, group), in display order
    ("2200-2600gm", "2200–2600 ग्राम", L), ("2000-2200gm", "2000–2200 ग्राम", L),
    ("1600-1800gm", "1600–1800 ग्राम", L), ("1400-1500gm", "1400–1500 ग्राम", L),
    ("1300-1400gm", "1300–1400 ग्राम", L), ("tandoori1200-1300gm", "तंदूरी 1200–1300 ग्राम", L),
    ("parent", "पेरेंट", P), ("thigh", "थाई (जांघ)", P), ("chest", "चेस्ट", P),
    ("tangrino12", "टांगड़ी नं. 12", P), ("tangrino10", "टांगड़ी नं. 10", P),
    ("tangrino8", "टांगड़ी नं. 8", P), ("wing", "विंग", P),
    ("LOLLIPOP", "लॉलीपॉप", P),  # comes from Poultry Bazaar
    ("dressedchicken", "ड्रेस्ड चिकन", P), ("vehicle", "वेहिकल (आई गाड़ियाँ)", V),
]


def num(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def fmt(x):
    return None if x is None else (int(x) if x == int(x) else round(x, 1))


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    return r if r.status_code == 200 else None


def render(url):
    """Open the page in a real headless browser: the rate table is filled in by JavaScript."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(user_agent=HEADERS["User-Agent"])
            pg.goto(url, wait_until="networkidle", timeout=60000)
            try:
                pg.wait_for_selector("table tr td", timeout=20000)
            except Exception:
                pass
            html = pg.content()
            b.close()
            return html
    except Exception as e:
        print("render failed:", e)
        return ""


def parse_pb(html):
    """Poultry Bazaar table: [name, desc, day1..day31, avg]. -> [(name, desc, t, y, p)]"""
    out = []
    for tr in BeautifulSoup(html, "html.parser").select("table tr"):
        c = [td.get_text(strip=True) for td in tr.select("td")]
        if len(c) < 3:
            continue
        vals = [num(x) for x in c[2:2 + TODAY.day]]  # days 1..today
        vals = [v for v in vals if v and 20 <= v <= 1000]  # skips empty days
        if not vals:
            continue
        y = vals[-2] if len(vals) > 1 else vals[-1]
        out.append((c[0], c[1], vals[-1], y, vals[-3] if len(vals) > 2 else y))
    return out


def pb_rows(slug):
    try:
        r = get(PB + slug)
    except requests.RequestException:
        r = None
    rows = parse_pb(r.text) if r else []
    if not rows:  # table empty in the plain HTML -> use the browser
        rows = parse_pb(render(PB + slug))
    print(slug, "->", len(rows), "rows")
    return rows


def state_cities(slug, state_hi):
    seen, cities = set(), []
    for name, desc, t, y, p in pb_rows(slug):
        if "piece" in desc.lower():
            continue
        name = re.sub(r"(\s*\([^)]*\))+\s*$", "", name).strip()  # drop "(Vencobb)" etc
        key = name.lower()
        if not key or key in seen:
            continue  # first row per city
        seen.add(key)
        cities.append({"city": CITY_HI.get(key, name.title()), "state": state_hi,
                       "today": fmt(t), "yest": fmt(y), "prev": fmt(p)})
    return cities


def norm(s):
    return re.sub(r"\s", "", s.lower().replace("no.", "no").replace("_", "-"))


def ghazipur_posts():
    """Last 3 daily posts (one per day, skipping days with no post)."""
    posts = []
    for back in range(9):
        d = TODAY - datetime.timedelta(days=back)
        url = "https://poultrysite.in/delhi-ghazipur-murga-mandi-%02d-%s-%d" % (d.day, d.strftime("%B").lower(), d.year)
        try:
            r = get(url)
        except requests.RequestException:
            r = None
        time.sleep(1)
        if not r:
            continue
        rows = {}
        for tr in BeautifulSoup(r.text, "html.parser").select("table tr"):
            c = [td.get_text(strip=True) for td in tr.select("td")]
            if len(c) >= 3 and num(c[1]) is not None:
                rows[norm(c[0])] = (num(c[1]), num(c[2]) or 0)
        if rows:
            posts.append((d, rows))
        if len(posts) == 3:
            break
    return posts


def delhi_parts(posts, lolly):
    parts = []
    for key, hi, g in GH:
        if key == "LOLLIPOP":
            vals = lolly
        else:
            vals = [rows[key][0] for _, rows in posts if key in rows]
            if len(vals) == 1:  # only one post: derive yesterday from its change column
                vals.append(vals[0] - posts[0][1][key][1])
        if not vals:
            continue
        y = vals[1] if len(vals) > 1 else vals[0]
        parts.append({"g": g, "n": hi, "t": fmt(vals[0]), "y": fmt(y), "p": fmt(vals[2] if len(vals) > 2 else y)})
    return parts


def main():
    try:
        old = json.load(open(OUT, encoding="utf-8"))
    except (OSError, ValueError):
        old = {"cities": [], "parts": []}
    if old.get("demo"):  # never keep demo rows as if they were real
        old = {"cities": [], "parts": []}
    cities, got = [], 0
    for en, (hi, slug) in STATES.items():
        try:
            rows = state_cities(slug, hi)
        except Exception as e:
            print("FAILED", en, e)
            rows = []
        if rows:
            got += len(rows)
        else:  # keep previous rates for this state
            rows = [c for c in old["cities"] if c["state"] == hi]
        cities += rows
    # Delhi
    lolly = []
    try:
        for name, desc, t, y, p in pb_rows("Delhi-Murga-Market"):
            if norm(name).startswith("lolypop") or norm(name).startswith("lollipop"):
                lolly = [t, y, p]
                break
    except Exception as e:
        print("FAILED Delhi (Poultry Bazaar)", e)
    posts = []
    try:
        posts = ghazipur_posts()
    except Exception as e:
        print("FAILED Delhi (Ghazipur)", e)
    parts = delhi_parts(posts, lolly) if posts else []
    if parts:
        got += len(parts)
        live = next((p for p in parts if p["n"].startswith("2000")), parts[0])
        cities.append({"city": "दिल्ली", "state": "दिल्ली", "today": live["t"], "yest": live["y"], "prev": live["p"]})
        if posts[0][0] != TODAY:
            print("WARNING: latest Ghazipur post is from", posts[0][0])
    else:
        parts = old["parts"]
        cities += [c for c in old["cities"] if c["state"] == "दिल्ली"]
    if not got:
        sys.exit("Nothing scraped - rates.json left unchanged.")
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    json.dump({"date": str(TODAY), "demo": False, "cities": cities, "parts": parts},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("Saved", len(cities), "cities,", len(parts), "parts")


if __name__ == "__main__":
    main()
