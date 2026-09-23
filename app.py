"""
MP-Dashboard-PEA — PEA M. PORTA MATTHIEU (n° 017703412016)
Positions : export courtier du 21/09/2026 (données dans le bloc DONNÉES ci-dessous)
Cours : Yahoo Finance (query1 / query2), repli sur le cours de l'export si indisponible.
"""
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, date

import requests
from flask import Flask, jsonify

app = Flask(__name__)

# --------------------------------------------------------------------------
# DONNÉES — à mettre à jour à chaque nouvel export courtier
# --------------------------------------------------------------------------
EXPORT_DATE = "21/09/2026"

# Produit de la vente de 75 titres PE500 (21/09/2026), en attente pour L'Oréal (montant estimé).
CASH_PENDING = 4155.0
CONCENTRATION_ALERT = 25.0

# Secteurs : nom -> couleur. Un secteur absent de cette liste prend une couleur de réserve.
SECTORS = {
    "Semi-conducteurs":   "#5aa9f0",
    "Gaz industriels":    "#3fb98a",
    "ETF géographiques":  "#b58cf0",
    "Hôtellerie":         "#e8a23b",
    "Défense":            "#ef6b5b",
    "GNL":                "#4dc2c9",
    "Beauté":             "#d98ec4",
    "Cloud":              "#7c8cf0",
}
SPARE_COLORS = ["#c9b458", "#8fb85a", "#e07fa0", "#6fc0e8", "#b0916b", "#9aa3b0"]

POSITIONS = [
    {"code": "ASML",  "name": "ASML Holding",       "yahoo": "ASML.AS",  "qty": 19,  "pru": 613.5011, "fallback": 1491.60,
     "sector": "Semi-conducteurs", "action": "Surveiller", "tone": "watch",
     "note": "Ne pas renforcer · export controls US"},
    {"code": "AI",    "name": "Air Liquide",        "yahoo": "AI.PA",    "qty": 98,  "pru": 170.1012, "fallback": 164.76,
     "sector": "Gaz industriels", "action": "Tenir", "tone": "hold",
     "note": "Pas de renforcement prévu · long terme"},
    {"code": "PAASI", "name": "ETF Asie émergente", "yahoo": "PAASI.PA", "qty": 357, "pru": 26.3803,  "fallback": 40.425,
     "sector": "ETF géographiques", "action": "Tenir", "tone": "hold",
     "note": "Amundi PEA MSCI Emerging Asia"},
    {"code": "AC",    "name": "Accor",              "yahoo": "AC.PA",    "qty": 132, "pru": 38.277,   "fallback": 45.99,
     "sector": "Hôtellerie", "action": "Vendre à 50 €", "tone": "sell",
     "note": "Ordre limite actif · 132 titres"},
    {"code": "PE500", "name": "ETF S&P 500",        "yahoo": "PE500.PA", "qty": 75,  "pru": 41.5128,  "fallback": 55.43,
     "sector": "ETF géographiques", "action": "Tenir (allégé)", "tone": "hold",
     "note": "50 % vendu le 21/09 (150 → 75 titres)"},
    {"code": "GUARD", "name": "GUARD Défense EU",   "yahoo": "GUARD.PA", "qty": 427, "pru": 11.9511,  "fallback": 11.178,
     "sector": "Défense", "action": "Tenir", "tone": "hold",
     "note": "BNP Paribas Easy Bloomberg Europe Defense"},
    {"code": "PINR",  "name": "ETF Inde",           "yahoo": "PINR.PA",  "qty": 154, "pru": 26.1556,  "fallback": 22.275,
     "sector": "ETF géographiques", "action": "Tenir", "tone": "hold",
     "note": "Amundi PEA MSCI India"},
    {"code": "GTT",   "name": "GTT",                "yahoo": "GTT.PA",   "qty": 13,  "pru": 191.14,   "fallback": 224.20,
     "sector": "GNL", "action": "Tenir", "tone": "hold",
     "note": "Conviction intacte · entrée à 175 € trop éloignée"},
    {"code": "OR",    "name": "L'Oréal",            "yahoo": "OR.PA",    "qty": 5,   "pru": 378.146,  "fallback": 382.05,
     "sector": "Beauté", "action": "Renforcer 370–380 €", "tone": "buy", "new_2026": True,
     "note": "Avant le 22 oct. · produit PE500"},
    {"code": "OVH",   "name": "OVHcloud",           "yahoo": "OVH.PA",   "qty": 23,  "pru": 9.6109,   "fallback": 18.39,
     "sector": "Cloud", "action": "Renforcer à 10 €", "tone": "buy",
     "note": "Uniquement après le plan Step Ahead"},
]

# Mouvements planifiés. kind : sell | buy | watch | candidate
MOVES = [
    {"code": "AC", "kind": "sell", "verb": "Vendre", "target": 50.0,
     "text": "Ordre limite actif sur les 132 titres. Le produit sera à répartir ensuite, L'Oréal en priorité."},
    {"code": "OR", "kind": "buy", "verb": "Renforcer", "target": 380.0, "budget": CASH_PENDING,
     "text": "Zone 370–380 € avant le T3 du 22 octobre, avec le produit du PE500. Le produit d'Accor viendra ensuite."},
    {"code": "OVH", "kind": "buy", "verb": "Renforcer", "target": 10.0, "when": "Après le 20 oct.",
     "text": "Seulement si le plan Step Ahead convainc. Le cours reste très au-dessus du consensus."},
    {"code": "ASML", "kind": "watch", "verb": "Ne pas toucher",
     "text": "Ligne dominante du PEA. On surveille les restrictions d'export vers la Chine."},
    {"code": "ESL", "name": "EssilorLuxottica", "kind": "candidate", "verb": "Candidate",
     "levels": [("1re tranche", "~155 €"), ("Renfort", "~145 €"), ("Thèse à revoir", "< 133 €")],
     "text": "Pas en portefeuille. Résultats FY2026 le 20 octobre."},
]

AGENDA = [
    {"date": "2026-10-22", "label": "22 oct.", "code": "OR", "title": "L'Oréal — chiffre d'affaires T3",
     "text": "18 h. Décide de l'usage du produit Accor."},
    {"date": "2026-10-20", "label": "20 oct.", "code": "OVH", "title": "OVHcloud — résultats FY2026",
     "text": "Plan Step Ahead : déclencheur possible du renfort à 10 €."},
    {"date": "2026-10-23", "label": "23 oct.", "code": "GTT", "title": "GTT — chiffre d'affaires T3",
     "text": "Nouvelles commandes de méthaniers."},
    {"date": "2026-11-15", "label": "Automne", "code": "AI", "title": "Air Liquide — chiffres T3",
     "text": "Confirmation de la trajectoire."},
    {"date": "2026-12-10", "label": "10 déc.", "code": "GTT", "title": "GTT — acompte sur dividende",
     "text": "4,30 € par titre, soit 55,90 € sur 13 titres."},
]


# Bloc « Pour actions » affiché au-dessus des positions
ACTION_PLAN = {
    "code": "OR",
    "deadline": "2026-10-22", "deadline_label": "22 octobre", "event": "Chiffre d'affaires T3 de L'Oréal, 18 h",
    "budget": CASH_PENDING,
    "zones": [
        {"phase": "before", "title": "D'ici le 22 octobre", "low": 370.0, "high": 380.0,
         "text": "Point d'entrée avec le produit du PE500."},
        {"phase": "after", "title": "Si la publication est bonne", "low": 390.0, "high": 395.0,
         "text": "Achat sur repli vers l'ancienne résistance. Ne pas courir après au-delà."},
    ],
}

DEFAULT_DATA = {"positions": POSITIONS, "moves": MOVES, "agenda": AGENDA, "export_date": EXPORT_DATE,
                "cash_pending": CASH_PENDING, "concentration_alert": CONCENTRATION_ALERT}

# --------------------------------------------------------------------------
# COURS TEMPS RÉEL
# --------------------------------------------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}
CACHE_TTL = 120        # secondes
CACHE_TTL_FAIL = 30    # on réessaie plus vite si Yahoo n'a rien répondu
_cache = {"ts": 0, "payload": None, "ttl": CACHE_TTL}


YTD_TTL = 12 * 3600    # la clôture du 31/12 ne bouge pas : une mise à jour toutes les 12 h suffit
_ytd_cache = {}        # symbole -> (horodatage, clôture 31/12)


def _chart(symbol, params, log):
    """Appel brut à l'API chart de Yahoo (query1 puis query2). Retourne 'result[0]' ou None."""
    for host in ("query1", "query2"):
        try:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                log.append(f"{host}: HTTP {r.status_code}")
                continue
            return r.json()["chart"]["result"][0]
        except Exception as e:
            log.append(f"{host}: {type(e).__name__}")
    return None


def _daily_series(res):
    """Barres journalières d'une réponse chart, datées au fuseau de la place de cotation."""
    meta = res.get("meta", {})
    off = meta.get("gmtoffset") or 0
    closes = res.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    stamps = res.get("timestamp") or []
    return [(datetime.fromtimestamp(t + off, timezone.utc).date(), float(c))
            for t, c in zip(stamps, closes) if c is not None]


def fetch_quote(symbol):
    """PRIORITÉ : cours et variation du jour exacts.
    Retourne un dict {price, prev, day, source} (valeurs None si échec) et le journal des tentatives.

    1) Requête intraday sur la seule séance en cours (range=1d, bougies 5 min) : dans ce cas précis,
       meta.chartPreviousClose EST la clôture de la séance précédente. C'est la référence la plus sûre.
    2) Si ce champ manque : 5 dernières séances en journalier, référence = dernière clôture datée
       strictement avant la séance du cours.
    3) Dernier recours : yfinance, même logique sur 5 jours."""
    log = []
    out = {"price": None, "prev": None, "day": None, "source": None}

    res = _chart(symbol, "range=1d&interval=5m", log)
    if res:
        meta = res.get("meta", {})
        price, prev = meta.get("regularMarketPrice"), meta.get("chartPreviousClose")
        if price and prev:
            out.update(price=float(price), prev=float(prev), source="intraday 1j")
        elif price:
            out["price"] = float(price)
            log.append("intraday: pas de clôture veille")
        else:
            log.append("intraday: réponse sans cours")

    if out["prev"] is None:
        res = _chart(symbol, "range=5d&interval=1d", log)
        if res:
            meta = res.get("meta", {})
            series = _daily_series(res)
            off = meta.get("gmtoffset") or 0
            rmt = meta.get("regularMarketTime")
            price = out["price"] or meta.get("regularMarketPrice") or (series[-1][1] if series else None)
            pdate = (datetime.fromtimestamp(rmt + off, timezone.utc).date() if rmt
                     else (series[-1][0] if series else None))
            prev = next((c for d, c in reversed(series) if pdate and d < pdate), None)
            if price:
                out.update(price=float(price), prev=prev, source="journalier 5j")

    if out["price"] is None or out["prev"] is None:
        try:
            import yfinance as yf
            hist = yf.Ticker(symbol).history(period="5d", interval="1d")["Close"].dropna()
            if len(hist) >= 2:
                out.update(price=float(hist.iloc[-1]), prev=float(hist.iloc[-2]), source="yfinance 5j")
            else:
                log.append("yfinance: données insuffisantes")
        except ImportError:
            log.append("yfinance: non installé")
        except Exception as e:
            log.append(f"yfinance: {type(e).__name__}")

    if out["price"] and out["prev"]:
        out["day"] = (out["price"] / out["prev"] - 1) * 100
    return out, log


def get_ytd_ref(symbol):
    """INDICATIF : clôture du 31/12 de l'année précédente. Appel séparé, mis en cache 12 h ;
    un échec ici n'affecte jamais le cours ni la variation du jour."""
    hit = _ytd_cache.get(symbol)
    if hit and time.time() - hit[0] < YTD_TTL:
        return hit[1]
    year = datetime.now().year
    p1 = int(datetime(year - 1, 12, 15, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(year, 1, 10, tzinfo=timezone.utc).timestamp())
    ref_date = datetime(year - 1, 12, 31).date()
    ref = None
    res = _chart(symbol, f"interval=1d&period1={p1}&period2={p2}", [])
    if res:
        ref = next((c for d, c in reversed(_daily_series(res)) if d <= ref_date), None)
    if ref is not None:
        _ytd_cache[symbol] = (time.time(), ref)
    return ref


def fetch_price(symbol):
    """Retourne (cours, variation_jour_%, clôture 31/12 année précédente, journal des tentatives)."""
    q, log = fetch_quote(symbol)
    if q["price"] is None:
        return None, None, None, log
    return q["price"], q["day"], get_ytd_ref(symbol), log


def build_moves(rows, moves):
    by_code = {r["code"]: r for r in rows}
    out = []
    for m in moves:
        item = {"code": m["code"], "kind": m["kind"], "verb": m["verb"], "text": m["text"],
                "when": m.get("when"), "levels": m.get("levels")}
        r = by_code.get(m["code"])
        item["name"] = r["name"] if r else (m.get("name") or m["code"])
        if r:
            item["price"] = r["price"]
            item["weight"] = r["weight"]
        target = m.get("target")
        if target and r:
            price = r["price"]
            item["target"] = target
            item["gap"] = (target / price - 1) * 100
            # progression vers la cible : 100 % = cible atteinte
            item["progress"] = round(min(price / target, 1) * 100 if m["kind"] == "sell"
                                     else min(target / price, 1) * 100)
            if m["kind"] == "sell":
                item["amount"] = r["qty"] * target
                item["shares"] = r["qty"]
            elif m.get("budget"):
                item["amount"] = m["budget"]
                item["shares"] = math.floor(m["budget"] / target)
        out.append(item)
    return out


def build_plan(rows):
    r = next((x for x in rows if x["code"] == ACTION_PLAN["code"]), None)
    if not r:
        return None
    return dict(ACTION_PLAN, name=r["name"], price=r["price"], live=r["live"], color=r["color"])


def build_payload():
    data = DEFAULT_DATA
    positions = data["positions"]
    colors, spare = dict(SECTORS), iter(SPARE_COLORS * 5)
    for p in positions:
        if p["sector"] not in colors:
            colors[p["sector"]] = next(spare)
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda p: fetch_price(p["yahoo"]), positions))

    rows, live_count, failed = [], 0, {}
    for p, (price, day, ytd_ref, log) in zip(positions, results):
        if price is None:
            failed[p["yahoo"]] = log
        live = price is not None
        live_count += live
        price = price if live else p["fallback"]
        if p.get("new_2026"):
            ytd_ref = p["pru"]      # ligne achetée cette année : le gain court depuis l'achat
        if not live:
            ytd_ref = None          # cours de l'export : pas de base de comparaison fiable
        value = price * p["qty"]
        cost = p["pru"] * p["qty"]
        rows.append({
            "code": p["code"], "name": p["name"], "qty": p["qty"], "pru": p["pru"],
            "price": price, "live": live, "day": day, "ytd_ref": ytd_ref,
            "export_price": p["fallback"], "live_price": price if live else None,
            "value": value, "cost": cost, "pv": value - cost, "pv_pct": (value / cost - 1) * 100,
            "sector": p["sector"], "color": colors[p["sector"]],
            "action": p["action"], "tone": p["tone"], "note": p["note"],
        })

    total = sum(r["value"] for r in rows)
    cost_total = sum(r["cost"] for r in rows)
    for r in rows:
        r["weight"] = r["value"] / total * 100
    rows.sort(key=lambda r: r["value"], reverse=True)

    # Gain depuis le 31/12 de l'année précédente, sur les quantités actuellement détenues
    ytd_rows = [r for r in rows if r["ytd_ref"]]
    ytd_gain = sum(r["qty"] * (r["price"] - r["ytd_ref"]) for r in ytd_rows)
    ytd_base = sum(r["qty"] * r["ytd_ref"] for r in ytd_rows)

    sectors = []
    for name in dict.fromkeys(r["sector"] for r in rows):
        color = colors[name]
        members = [r for r in rows if r["sector"] == name]
        if not members:
            continue
        value = sum(r["value"] for r in members)
        cost = sum(r["cost"] for r in members)
        sectors.append({
            "name": name, "color": color, "value": value, "weight": value / total * 100,
            "pv": value - cost, "pv_pct": (value / cost - 1) * 100,
            "members": [{"code": r["code"], "name": r["name"], "weight": r["weight"]} for r in members],
        })
    sectors.sort(key=lambda s: s["value"], reverse=True)

    return {
        "rows": rows,
        "sectors": sectors,
        "total": total,
        "cost": cost_total,
        "pv": total - cost_total,
        "pv_pct": (total / cost_total - 1) * 100,
        "cash_pending": data["cash_pending"],
        "total_with_cash": total + data["cash_pending"],
        "ytd_gain": ytd_gain if ytd_rows else None,
        "ytd_pct": (ytd_gain / ytd_base * 100) if ytd_base else None,
        "ytd_count": len(ytd_rows),
        "ytd_year": datetime.now().year,
        "live_count": live_count,
        "n": len(rows),
        "yahoo_errors": (" | ".join(next(iter(failed.values()))) if failed else ""),
        "export_date": data["export_date"],
        "concentration_alert": data["concentration_alert"],
        "moves": build_moves(rows, data["moves"]),
        "plan": build_plan(rows),
        "agenda": sorted(
            [dict(a, color=next((r["color"] for r in rows if r["code"] == a["code"]), "#6b7684"))
             for a in data["agenda"] if a["date"] >= date.today().isoformat()],
            key=lambda a: a["date"]),
        "updated": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }


@app.route("/api/data")
def api_data():
    force = os.environ.get("NO_CACHE") == "1"
    if force or not _cache["payload"] or time.time() - _cache["ts"] > _cache["ttl"]:
        _cache["payload"] = build_payload()
        _cache["ts"] = time.time()
        _cache["ttl"] = CACHE_TTL if _cache["payload"]["live_count"] else CACHE_TTL_FAIL
    return jsonify(_cache["payload"])


@app.route("/api/refresh")
def api_refresh():
    _cache["ts"] = 0
    return api_data()


@app.route("/api/debug")
def api_debug():
    """Diagnostic : pour chaque ticker, le cours obtenu ou la raison de l'échec."""
    out = {}
    for p in POSITIONS:
        q, log = fetch_quote(p["yahoo"])
        out[p["yahoo"]] = {"cours": q["price"], "cloture_veille": q["prev"], "var_jour_pct": q["day"],
                           "source_variation": q["source"], "ytd_ref_31_12": get_ytd_ref(p["yahoo"]),
                           "tentatives_echouees": log}
    return jsonify(out)


@app.route("/health")
def health():
    return "ok"


# --------------------------------------------------------------------------
# FRONT (mode sombre)
# --------------------------------------------------------------------------
PAGE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard PEA M PORTA</title>
<style>
  :root{
    --bg:#0d1015; --panel:#151a21; --panel2:#1b222b; --line:#252d38;
    --text:#e8ebf0; --muted:#8a94a3; --pos:#3fb98a; --neg:#ef6b5b;
    --sell:#e8a23b; --buy:#5aa9f0; --watch:#b58cf0; --hold:#6b7684;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;-webkit-font-smoothing:antialiased}
  .wrap{max-width:1180px;margin:0 auto;padding:28px 20px 60px}
  header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:22px}
  h1{font-size:22px;margin:0;font-weight:650;letter-spacing:-.01em}
  .sub{color:var(--muted);font-size:13px;margin-top:2px}
  button{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:8px;
         padding:8px 14px;font:inherit;font-size:13px;cursor:pointer}
  button:hover{border-color:#3a4554}
  button:focus-visible{outline:2px solid var(--buy);outline-offset:2px}
  .pos{color:var(--pos)} .neg{color:var(--neg)}
  section{margin-bottom:30px}
  h2{font-size:16px;font-weight:650;margin:0 0 12px;letter-spacing:-.005em}
  h2 small{color:var(--muted);font-weight:400;font-size:13px;margin-left:8px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:12px}

  /* KPIs */
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:30px}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 17px}
  .kpi .l{color:var(--muted);font-size:12.5px}
  .kpi .v{font-size:25px;font-weight:650;margin-top:4px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
  .kpi .s{color:var(--muted);font-size:12.5px;margin-top:2px}

  /* Mouvements planifiés */
  .moves{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}
  .mv{--c:var(--hold);background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 18px 16px;
      position:relative;overflow:hidden;display:flex;flex-direction:column;gap:12px}
  .mv::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--c)}
  .mv.sell{--c:var(--sell)} .mv.buy{--c:var(--buy)} .mv.watch{--c:var(--watch)}
  .mv.candidate{--c:var(--hold);border-style:dashed;background:transparent}
  .mv.sell,.mv.buy{background:linear-gradient(180deg,color-mix(in srgb,var(--c) 9%,var(--panel)),var(--panel) 60%)}
  .mv-top{display:flex;justify-content:space-between;align-items:center;gap:10px}
  .verb{font-size:19px;font-weight:700;color:var(--c);letter-spacing:-.01em}
  .when{font-size:12px;padding:3px 9px;border-radius:99px;border:1px solid var(--line);color:var(--muted)}
  .mv-name{font-size:14.5px;font-weight:600;margin-top:-6px}
  .mv-name span{color:var(--muted);font-weight:400}
  .lv{display:flex;align-items:baseline;gap:10px;font-variant-numeric:tabular-nums}
  .lv .now{font-size:13px;color:var(--muted)}
  .lv .arrow{color:var(--muted)}
  .lv .tgt{font-size:26px;font-weight:700;letter-spacing:-.02em}
  .bar{height:8px;border-radius:99px;background:var(--panel2);overflow:hidden}
  .bar i{display:block;height:100%;border-radius:99px;background:var(--c)}
  .barlbl{display:flex;justify-content:space-between;font-size:12.5px;color:var(--muted);margin-top:-6px;font-variant-numeric:tabular-nums}
  .barlbl b{color:var(--text);font-weight:600}
  .amount{display:flex;gap:8px;flex-wrap:wrap}
  .pill{font-size:12.5px;padding:4px 10px;border-radius:8px;background:var(--panel2);border:1px solid var(--line);font-variant-numeric:tabular-nums}
  .pill b{font-weight:650}
  .mv p{margin:0;color:var(--muted);font-size:13.5px}
  .levels{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
  .levels div{background:var(--panel2);border-radius:8px;padding:8px 10px;font-size:12px;color:var(--muted)}
  .levels b{display:block;color:var(--text);font-size:15px;margin-top:2px}

  /* Positions */
  .tablewrap{overflow-x:auto}
  table{width:100%;border-collapse:separate;border-spacing:0;min-width:980px;font-variant-numeric:tabular-nums}
  th,td{padding:14px 14px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}
  th{color:var(--muted);font-weight:500;font-size:12.5px;background:var(--panel2);padding:11px 14px}
  th:first-child{border-top-left-radius:12px} th:last-child{border-top-right-radius:12px}
  th:first-child,td:first-child,th:last-child,td:last-child{text-align:left}
  tbody tr{transition:background .12s}
  tbody tr:hover{background:rgba(255,255,255,.025)}
  tbody tr:last-child td{border-bottom:0}
  .who{display:flex;align-items:center;gap:12px}
  .av{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;font-size:11px;font-weight:700;
      color:#0d1015;flex:none}
  .who b{font-weight:600;display:block;font-size:14.5px}
  .who small{display:block;color:var(--muted);font-size:12px;white-space:normal;max-width:230px;line-height:1.3;margin-top:1px}
  .px{font-weight:600}
  .xp{color:var(--muted)}
  .live{display:inline-flex;align-items:center;gap:7px}
  .ldot{width:7px;height:7px;border-radius:50%;background:var(--pos);display:inline-block}
  .dpill{display:inline-block;padding:3px 9px;border-radius:8px;font-weight:600;font-size:13px;background:var(--panel2);color:var(--muted)}
  .dpill.pos{background:rgba(63,185,138,.13);color:var(--pos)} .dpill.neg{background:rgba(239,107,91,.13);color:var(--neg)}
  .val{font-weight:650;font-size:15px}
  .pvpill{display:inline-block;padding:4px 10px;border-radius:8px;font-weight:600;font-size:13px}
  .pvpill.pos{background:rgba(63,185,138,.13)} .pvpill.neg{background:rgba(239,107,91,.13)}
  .pvamt{display:block;font-size:12px;margin-top:3px}
  .wt{min-width:110px}
  .wt span{font-weight:600}
  .wt .bar{height:5px;margin-top:6px}
  .wt .bar i{background:var(--buy)}
  .tag{display:inline-block;padding:4px 10px;border-radius:99px;font-size:12px;border:1px solid}
  .tag.hold{color:var(--hold);border-color:#3a4351}
  .tag.sell{color:var(--sell);border-color:rgba(232,162,59,.5);background:rgba(232,162,59,.09)}
  .tag.buy{color:var(--buy);border-color:rgba(90,169,240,.5);background:rgba(90,169,240,.09)}
  .tag.watch{color:var(--watch);border-color:rgba(181,140,240,.5);background:rgba(181,140,240,.09)}
  .est{color:var(--muted);font-size:11px;margin-left:4px;font-weight:400}

  /* Mobile : la colonne « Valeur » reste fixe, le reste défile horizontalement */
  @media (max-width:720px){
    .tablewrap th:first-child,.tablewrap td:first-child{
      position:sticky;left:0;z-index:1;background:var(--panel);
      padding-left:12px;padding-right:12px;
      box-shadow:1px 0 0 var(--line),8px 0 10px -6px rgba(0,0,0,.6)}
    .tablewrap th:first-child{background:var(--panel2);z-index:2}
    .tablewrap tbody tr:hover td:first-child{background:color-mix(in srgb,#fff 2.5%,var(--panel))}
    .who{gap:9px}
    .av{width:32px;height:32px;font-size:10px;border-radius:9px}
    .who b{font-size:14px}
    .who small{display:none}
  }

  /* Agenda */
  .ag{display:flex;gap:16px;align-items:center;padding:14px 18px;border-bottom:1px solid var(--line)}
  .ag:last-child{border-bottom:0}
  .ag .d{min-width:74px;text-align:center}
  .ag .d b{display:block;font-size:15px;font-weight:650}
  .ag .d span{font-size:12px;color:var(--muted)}
  .ag .dot{width:4px;align-self:stretch;border-radius:4px;flex:none}
  .ag .t b{display:block;font-weight:600}
  .ag .t span{color:var(--muted);font-size:13.5px}

  /* Répartition */
  .stack{display:flex;height:20px;border-radius:7px;overflow:hidden;margin:16px 18px 12px;background:var(--panel2);gap:2px}
  .stack div{height:100%}
  .legend{display:flex;flex-wrap:wrap;gap:6px 16px;padding:0 18px 16px;font-size:12.5px;color:var(--muted)}
  .legend i{display:inline-block;width:9px;height:9px;border-radius:3px;margin-right:6px}
  .alert{margin:0 18px 16px;padding:9px 12px;border-radius:8px;background:rgba(232,162,59,.1);
         border:1px solid rgba(232,162,59,.35);font-size:13px}
  .sectors{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}
  .sec{--c:var(--hold);background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 16px 14px;
       border-top:3px solid var(--c)}
  .sec-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
  .sec-top b{font-weight:600;font-size:14.5px}
  .sec-w{font-size:24px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums;margin:6px 0 8px}
  .sec .bar i{background:var(--c)}
  .sec-meta{display:flex;justify-content:space-between;font-size:12.5px;color:var(--muted);margin-top:8px;font-variant-numeric:tabular-nums}
  .mem{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
  .mem span{font-size:12px;padding:3px 9px;border-radius:99px;background:var(--panel2);border:1px solid var(--line)}
  .mem em{font-style:normal;color:var(--muted);margin-left:4px}

  /* Pour actions */
  .plan{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px;display:grid;
        grid-template-columns:minmax(200px,.8fr) 1fr 1fr;gap:14px;align-items:stretch}
  .dl{display:flex;flex-direction:column;justify-content:center;gap:4px;padding-right:14px;border-right:1px solid var(--line)}
  .dl .k{color:var(--muted);font-size:12.5px}
  .dl .big{font-size:30px;font-weight:700;letter-spacing:-.02em;font-variant-numeric:tabular-nums;color:var(--sell)}
  .dl .ev{font-size:14px;font-weight:600}
  .dl .px{font-size:13px;color:var(--muted);margin-top:6px;font-variant-numeric:tabular-nums}
  .dl .px b{color:var(--text)}
  .zone{--c:var(--buy);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:8px;
        background:color-mix(in srgb,var(--c) 7%,var(--panel))}
  .zone.off{--c:var(--hold);background:transparent;border-style:dashed}
  .zone .zt{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
  .zone .zr{font-size:26px;font-weight:700;letter-spacing:-.02em;color:var(--c);font-variant-numeric:tabular-nums}
  .zone p{margin:0;color:var(--muted);font-size:13px}
  .st{font-size:12px;padding:3px 9px;border-radius:99px;border:1px solid var(--line);white-space:nowrap}
  .st.in{color:var(--pos);border-color:rgba(63,185,138,.5);background:rgba(63,185,138,.1)}
  .st.wait{color:var(--muted)}
  .st.low{color:var(--sell);border-color:rgba(232,162,59,.5);background:rgba(232,162,59,.1)}
  @media (max-width:820px){.plan{grid-template-columns:1fr}.dl{border-right:0;border-bottom:1px solid var(--line);padding:0 0 12px}}

  footer{color:var(--muted);font-size:12px;margin-top:28px;line-height:1.6}
  .fdot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>Dashboard PEA M PORTA</h1>
      <div class="sub" id="sub">Chargement…</div>
    </div>
    <button id="refresh">Actualiser les cours</button>
  </header>

  <div class="kpis" id="kpis"></div>

  <section id="plan-sec">
    <h2>Pour actions</h2>
    <div class="plan" id="plan"></div>
  </section>

  <section>
    <h2>Positions</h2>
    <div class="card tablewrap">
      <table>
        <thead><tr>
          <th>Valeur</th><th>Cours</th><th>Var. jour</th><th>Qté</th><th>PRU</th>
          <th>Valorisation</th><th>+/- value</th><th>Poids</th><th>Stratégie</th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </section>

  <section>
    <h2>Répartition du portefeuille</h2>
    <div class="card">
      <div class="stack" id="stack" role="img" aria-label="Répartition par ligne"></div>
      <div class="legend" id="legend"></div>
      <div id="alert"></div>
    </div>
  </section>

  <section>
    <h2>Répartition par secteur</h2>
    <div class="sectors" id="sectors"></div>
  </section>

  <section>
    <h2>Mouvements planifiés</h2>
    <div class="moves" id="moves"></div>
  </section>

  <section>
    <h2>Agenda<small>valeurs du portefeuille</small></h2>
    <div class="card" id="agenda"></div>
  </section>

  <footer id="foot"></footer>
</div>

<script>
const eur = (n, d=0) => n.toLocaleString('fr-FR',{minimumFractionDigits:d,maximumFractionDigits:d}) + '\u00a0€';
const num = (n, d=2) => n.toLocaleString('fr-FR',{minimumFractionDigits:d,maximumFractionDigits:d});
const sgn = (n, f) => (n>0?'+':n<0?'−':'') + f(Math.abs(n));
const cls = n => n>0.005 ? 'pos' : n<-0.005 ? 'neg' : '';
const pct = (n, d=1) => sgn(n, x=>num(x,d)) + '\u00a0%';
const ABBR = {PE500:'USA', PAASI:'ASI', PINR:'IND', GUARD:'DEF'};

function renderMove(m){
  if(m.kind==='candidate'){
    return `<div class="mv candidate">
      <div class="mv-top"><span class="verb">${m.verb}</span></div>
      <div class="mv-name">${m.name}</div>
      <div class="levels">${m.levels.map(l=>`<div>${l[0]}<b>${l[1]}</b></div>`).join('')}</div>
      <p>${m.text}</p></div>`;
  }
  if(m.kind==='watch'){
    return `<div class="mv watch">
      <div class="mv-top"><span class="verb">${m.verb}</span></div>
      <div class="mv-name">${m.name} <span>· ${num(m.weight,1)}\u00a0% du PEA</span></div>
      <p>${m.text}</p></div>`;
  }
  const isSell = m.kind==='sell';
  const need = isSell ? 'Il manque ' + pct(m.gap) : 'Il faut ' + pct(m.gap);
  const pills = [];
  if(m.amount) pills.push(`<span class="pill">${isSell?'Produit':'Budget'} <b>~${eur(m.amount)}</b></span>`);
  if(m.shares) pills.push(`<span class="pill"><b>${m.shares}</b> titres${isSell?'':' environ'}</span>`);
  return `<div class="mv ${m.kind}">
    <div class="mv-top"><span class="verb">${m.verb}</span>${m.when?`<span class="when">${m.when}</span>`:''}</div>
    <div class="mv-name">${m.name}</div>
    <div class="lv"><span class="now">${num(m.price)}\u00a0€</span><span class="arrow">→</span><span class="tgt">${num(m.target, m.target%1?2:0)}\u00a0€</span></div>
    <div><div class="bar"><i style="width:${m.progress}%"></i></div></div>
    <div class="barlbl"><span>${need}</span><b>${m.progress}\u00a0%</b></div>
    ${pills.length?`<div class="amount">${pills.join('')}</div>`:''}
    <p>${m.text}</p></div>`;
}

function zoneStatus(z, price, active){
  if(!active) return `<span class="st wait">${z.phase==='after'?'Après publication':'Échéance passée'}</span>`;
  if(price>=z.low && price<=z.high) return '<span class="st in">Dans la zone · acheter</span>';
  if(price>z.high) return `<span class="st wait">Au-dessus · ${pct((z.high/price-1)*100)}</span>`;
  return `<span class="st low">Sous la zone · vérifier la cause</span>`;
}

function renderPlan(p){
  const sec = document.getElementById('plan-sec');
  if(!p){ sec.style.display='none'; return; }
  const today = new Date(); today.setHours(0,0,0,0);
  const days = Math.round((new Date(p.deadline+'T00:00:00') - today)/86400000);
  const before = days > 0 || (days === 0 && new Date().getHours() < 18);
  const big = days>1 ? 'J−'+days : days===1 ? 'Demain' : days===0 ? "Aujourd'hui" : 'Publié';
  const shares = Math.floor(p.budget/((p.zones[0].low+p.zones[0].high)/2));
  document.getElementById('plan').innerHTML = `
    <div class="dl">
      <span class="k">Échéance · ${p.deadline_label}</span>
      <span class="big">${big}</span>
      <span class="ev">${p.event}</span>
      <span class="px">${p.name} : <b>${num(p.price)}\u00a0€</b>${p.live?'':' (export)'} · budget ~${eur(p.budget)} (~${shares} titres)</span>
    </div>` + p.zones.map(z=>{
      const active = z.phase==='before' ? before : !before;
      return `<div class="zone ${active?'':'off'}">
        <div class="zt"><span>${z.title}</span>${zoneStatus(z, p.price, active)}</div>
        <div class="zr">${num(z.low,0)}–${num(z.high,0)}\u00a0€</div>
        <p>${z.text}</p></div>`;
    }).join('');
}

function render(d){
  renderPlan(d.plan);
  document.getElementById('sub').textContent =
    'Positions du ' + d.export_date + ' · cours actualisés le ' + d.updated;

  const ytdOk = d.ytd_gain != null && d.ytd_pct != null;
  document.getElementById('kpis').innerHTML = `
    <div class="kpi"><div class="l">Valorisation des titres</div>
      <div class="v">${eur(d.total)}</div>
      <div class="s">Coût d'acquisition ${eur(d.cost)}</div></div>
    <div class="kpi"><div class="l">Plus-value latente</div>
      <div class="v ${cls(d.pv)}">${sgn(d.pv, x=>eur(x))}</div>
      <div class="s ${cls(d.pv_pct)}">${pct(d.pv_pct)} vs coût</div></div>
    <div class="kpi"><div class="l">Gain année en cours</div>
      <div class="v ${ytdOk?cls(d.ytd_gain):''}">${ytdOk?sgn(d.ytd_gain, x=>eur(x)):'—'}</div>
      <div class="s">Depuis le 31/12/${d.ytd_year-1}${d.ytd_count<d.n?' · '+d.ytd_count+'/'+d.n+' lignes':''}</div></div>
    <div class="kpi"><div class="l">Gain YTD</div>
      <div class="v ${ytdOk?cls(d.ytd_pct):''}">${ytdOk?pct(d.ytd_pct):'—'}</div>
      <div class="s">vs valeur au 31/12/${d.ytd_year-1}</div></div>`;

  document.getElementById('moves').innerHTML = d.moves.map(renderMove).join('');

  const maxW = Math.max(...d.rows.map(r=>r.weight));
  document.getElementById('rows').innerHTML = d.rows.map(r=>`<tr>
      <td><div class="who">
        <div class="av" style="background:${r.color}">${ABBR[r.code]||r.code}</div>
        <div><b>${r.name}</b><small>${r.note}</small></div></div></td>
      <td><span class="px live">${r.live?'<i class="ldot"></i>':''}${num(r.price)}\u00a0€</span>${r.live?'':'<span class="est">export</span>'}</td>
      <td>${r.day==null?'<span class="est">—</span>':`<span class="dpill ${cls(r.day)}">${pct(r.day,2)}</span>`}</td>
      <td>${r.qty}</td>
      <td>${num(r.pru)}\u00a0€</td>
      <td class="val">${eur(r.value)}</td>
      <td><span class="pvpill ${cls(r.pv)}">${pct(r.pv_pct)}</span>
        <span class="pvamt ${cls(r.pv)}">${sgn(r.pv, x=>eur(x))}</span></td>
      <td class="wt"><span>${num(r.weight,1)}\u00a0%</span><div class="bar"><i style="width:${r.weight/maxW*100}%"></i></div></td>
      <td><span class="tag ${r.tone}">${r.action}</span></td>
    </tr>`).join('');

  const today = new Date();
  document.getElementById('agenda').innerHTML = d.agenda.map(e=>{
    const days = Math.ceil((new Date(e.date) - today)/86400000);
    const left = days>0 ? `dans ${days} j` : '';
    return `<div class="ag"><div class="d"><b>${e.label}</b><span>${left}</span></div>
      <div class="dot" style="background:${e.color}"></div>
      <div class="t"><b>${e.title}</b><span>${e.text}</span></div></div>`;
  }).join('');

  document.getElementById('stack').innerHTML = d.rows.map(r=>
    `<div style="width:${r.weight}%;background:${r.color}" title="${r.name} ${num(r.weight,1)} %"></div>`).join('');
  document.getElementById('legend').innerHTML = d.rows.map(r=>
    `<span><i style="background:${r.color}"></i>${r.name} ${num(r.weight,1)}\u00a0%</span>`).join('');
  const big = d.rows.filter(r=>r.weight>d.concentration_alert);
  document.getElementById('alert').innerHTML = big.length
    ? `<div class="alert">${big.map(r=>`${r.name} pèse ${num(r.weight,1)}\u00a0% du PEA`).join(' · ')} : au-dessus du seuil de ${d.concentration_alert}\u00a0%.</div>` : '';

  document.getElementById('sectors').innerHTML = d.sectors.map(s=>`
    <div class="sec" style="--c:${s.color}">
      <div class="sec-top"><b>${s.name}</b><span class="${cls(s.pv)}">${pct(s.pv_pct)}</span></div>
      <div class="sec-w">${num(s.weight,1)}\u00a0%</div>
      <div class="bar"><i style="width:${s.weight}%"></i></div>
      <div class="sec-meta"><span>${eur(s.value)}</span><span class="${cls(s.pv)}">${sgn(s.pv, x=>eur(x))}</span></div>
      <div class="mem">${s.members.map(m=>`<span>${m.name}<em>${num(m.weight,1)}\u00a0%</em></span>`).join('')}</div>
    </div>`).join('');

  const live = d.live_count===d.n;
  document.getElementById('foot').innerHTML =
    `<span class="fdot" style="background:${live?'var(--pos)':'var(--sell)'}"></span>` +
    (live ? 'Cours Yahoo Finance en direct sur les ' + d.n + ' lignes.'
          : d.live_count + ' ligne(s) sur ' + d.n + ' en direct ; les autres sont valorisées au cours de l\'export du ' + d.export_date + '.') +
    (live ? '' : '<br>Détail Yahoo : ' + d.yahoo_errors + ' (diagnostic complet sur /api/debug)') +
    '<br>Actualisation automatique toutes les 2 minutes. Outil de suivi personnel, pas un conseil en investissement.';
}

async function load(url){
  try{ const r = await fetch(url); render(await r.json()); }
  catch(e){ document.getElementById('sub').textContent = 'Données indisponibles, réessaie dans un instant.'; }
}
document.getElementById('refresh').onclick = () => load('/api/refresh');
load('/api/data');
setInterval(()=>load('/api/data'), 120000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return PAGE


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
