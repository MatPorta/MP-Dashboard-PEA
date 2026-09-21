"""
MP-Dashboard-PEA — PEA M. PORTA MATTHIEU (n° 017703412016)
Positions : export courtier du 21/09/2026
Cours : Yahoo Finance (query1 / query2), repli sur les cours de l'export si indisponible.
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests
from flask import Flask, jsonify

app = Flask(__name__)

# --------------------------------------------------------------------------
# DONNÉES — à mettre à jour à chaque nouvel export courtier
# --------------------------------------------------------------------------
EXPORT_DATE = "21/09/2026"

# Produit de la vente de 75 titres PE500 (21/09/2026), en attente pour L'Oréal.
# Le courtier ne le montre pas dans l'export "simple" : montant estimé.
CASH_PENDING = 4155.0

# ticker Yahoo, nom, quantité, PRU, cours de repli (export), stratégie, statut
POSITIONS = [
    {"code": "ASML",  "name": "ASML Holding",       "yahoo": "ASML.AS", "qty": 19,  "pru": 613.5011, "fallback": 1491.60,
     "action": "Surveiller", "tone": "watch",
     "note": "Ne pas renforcer · export controls US"},
    {"code": "AI",    "name": "Air Liquide",         "yahoo": "AI.PA",   "qty": 98,  "pru": 170.1012, "fallback": 164.76,
     "action": "Tenir", "tone": "hold",
     "note": "Pas de renforcement prévu · position long terme"},
    {"code": "PAASI", "name": "ETF Asie émergente",  "yahoo": "PAASI.PA", "qty": 357, "pru": 26.3803,  "fallback": 40.425,
     "action": "Tenir", "tone": "hold", "note": "Amundi PEA MSCI Emerging Asia"},
    {"code": "AC",    "name": "Accor",               "yahoo": "AC.PA",   "qty": 132, "pru": 38.277,   "fallback": 45.99,
     "action": "Vendre à 50 €", "tone": "sell", "target": 50.0,
     "note": "Ordre limite actif · 132 titres"},
    {"code": "PE500", "name": "ETF S&P 500",         "yahoo": "PE500.PA", "qty": 75,  "pru": 41.5128,  "fallback": 55.43,
     "action": "Tenir (allégé)", "tone": "hold",
     "note": "50 % vendu le 21/09 (150 → 75 titres)"},
    {"code": "GUARD", "name": "GUARD Défense EU",    "yahoo": "GUARD.PA", "qty": 427, "pru": 11.9511,  "fallback": 11.178,
     "action": "Tenir", "tone": "hold", "note": "BNP Paribas Easy Bloomberg Europe Defense"},
    {"code": "PINR",  "name": "ETF Inde",            "yahoo": "PINR.PA", "qty": 154, "pru": 26.1556,  "fallback": 22.275,
     "action": "Tenir", "tone": "hold", "note": "Amundi PEA MSCI India"},
    {"code": "GTT",   "name": "GTT",                 "yahoo": "GTT.PA",  "qty": 13,  "pru": 191.14,   "fallback": 224.20,
     "action": "Tenir", "tone": "hold",
     "note": "Conviction intacte · entrée à 175 € trop éloignée du cours"},
    {"code": "OR",    "name": "L'Oréal",             "yahoo": "OR.PA",   "qty": 5,   "pru": 378.146,  "fallback": 382.05,
     "action": "Renforcer ~375 €", "tone": "buy", "target": 375.0,
     "note": "Produit PE500 (~4 155 €), puis produit Accor"},
    {"code": "OVH",   "name": "OVHcloud",            "yahoo": "OVH.PA",  "qty": 23,  "pru": 9.6109,   "fallback": 18.39,
     "action": "Renforcer à 10 €", "tone": "buy", "target": 10.0,
     "note": "Uniquement après le plan Step Ahead (20 oct.)"},
]

MOVES = [
    {"code": "AC", "title": "Accor — vendre à 50 €",
     "text": "Ordre limite actif sur 132 titres (~6 600 €). À l'exécution, nouvelle discussion sur la répartition du produit "
             "(L'Oréal en priorité, autres pistes à arbitrer)."},
    {"code": "OR", "title": "L'Oréal — renforcer avec le produit PE500",
     "text": "~4 155 € en attente, point d'entrée visé à ~375 €. Le produit d'Accor viendra ensuite."},
    {"code": "OVH", "title": "OVHcloud — renforcer à 10 €",
     "text": "Seulement si le plan Step Ahead convainc le 20 octobre. Le cours reste bien au-dessus du consensus."},
    {"code": "ESL", "title": "EssilorLuxottica — candidate",
     "text": "Pas en portefeuille. Première tranche vers 155 €, renfort vers 145 €, thèse à réévaluer sous 133 €. "
             "Catalyseur : résultats FY2026 le 20 octobre."},
    {"code": "ASML", "title": "ASML — ne pas toucher",
     "text": "Ligne dominante du PEA. Surveiller les restrictions d'export vers la Chine."},
]

AGENDA = [
    {"date": "2026-10-20", "label": "20 oct.", "title": "OVHcloud FY2026 + plan Step Ahead",
     "text": "Déclencheur possible du renfort à 10 €."},
    {"date": "2026-10-20", "label": "20 oct.", "title": "EssilorLuxottica FY2026",
     "text": "Catalyseur avant une éventuelle entrée."},
    {"date": "2026-10-23", "label": "23 oct.", "title": "GTT — CA du T3",
     "text": "Nouvelles commandes de méthaniers."},
    {"date": "2026-11-15", "label": "Automne", "title": "Air Liquide et L'Oréal — chiffres T3",
     "text": "Trajectoire Air Liquide · premières contributions Gucci Beauté chez L'Oréal."},
    {"date": "2026-12-10", "label": "10 déc.", "title": "GTT — acompte sur dividende",
     "text": "4,30 € par titre, soit 55,90 € sur 13 titres."},
]

# Seuil d'alerte de concentration (poids max d'une ligne)
CONCENTRATION_ALERT = 25.0

# --------------------------------------------------------------------------
# COURS TEMPS RÉEL
# --------------------------------------------------------------------------
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
CACHE_TTL = 120  # secondes
_cache = {"ts": 0, "payload": None}


def fetch_price(symbol):
    """Retourne (cours, variation_jour_%) ou (None, None)."""
    for host in ("query1", "query2"):
        try:
            url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
            r = requests.get(url, headers=HEADERS, timeout=5)
            if r.status_code != 200:
                continue
            meta = r.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price:
                day = (price / prev - 1) * 100 if prev else None
                return float(price), day
        except Exception:
            continue
    return None, None


def build_payload():
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda p: fetch_price(p["yahoo"]), POSITIONS))

    rows, live_count = [], 0
    for p, (price, day) in zip(POSITIONS, results):
        live = price is not None
        live_count += live
        price = price if live else p["fallback"]
        value = price * p["qty"]
        cost = p["pru"] * p["qty"]
        row = {
            "code": p["code"], "name": p["name"], "qty": p["qty"], "pru": p["pru"],
            "price": price, "live": live, "day": day,
            "value": value, "cost": cost, "pv": value - cost, "pv_pct": (value / cost - 1) * 100,
            "action": p["action"], "tone": p["tone"], "note": p["note"],
            "target": p.get("target"),
            "gap_target": ((p["target"] / price - 1) * 100) if p.get("target") else None,
        }
        rows.append(row)

    total = sum(r["value"] for r in rows)
    cost_total = sum(r["cost"] for r in rows)
    for r in rows:
        r["weight"] = r["value"] / total * 100
    rows.sort(key=lambda r: r["value"], reverse=True)

    return {
        "rows": rows,
        "total": total,
        "cost": cost_total,
        "pv": total - cost_total,
        "pv_pct": (total / cost_total - 1) * 100,
        "cash_pending": CASH_PENDING,
        "total_with_cash": total + CASH_PENDING,
        "best": max(rows, key=lambda r: r["pv_pct"])["name"],
        "best_pct": max(r["pv_pct"] for r in rows),
        "worst": min(rows, key=lambda r: r["pv_pct"])["name"],
        "worst_pct": min(r["pv_pct"] for r in rows),
        "live_count": live_count,
        "n": len(rows),
        "export_date": EXPORT_DATE,
        "concentration_alert": CONCENTRATION_ALERT,
        "moves": MOVES,
        "agenda": AGENDA,
        "updated": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }


@app.route("/api/data")
def api_data():
    force = os.environ.get("NO_CACHE") == "1"
    if force or not _cache["payload"] or time.time() - _cache["ts"] > CACHE_TTL:
        _cache["payload"] = build_payload()
        _cache["ts"] = time.time()
    return jsonify(_cache["payload"])


@app.route("/api/refresh")
def api_refresh():
    _cache["ts"] = 0
    return api_data()


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
<title>PEA · Tableau de bord</title>
<style>
  :root{
    --bg:#0e1116; --panel:#161b22; --panel2:#1c232c; --line:#262e39;
    --text:#e6e9ee; --muted:#8b95a3; --pos:#3fb98a; --neg:#ef6b5b;
    --sell:#e8a23b; --buy:#5aa9f0; --watch:#b58cf0; --hold:#6b7684;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
       -webkit-font-smoothing:antialiased}
  .wrap{max-width:1180px;margin:0 auto;padding:28px 20px 60px}
  header{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:22px}
  h1{font-size:22px;margin:0;font-weight:650;letter-spacing:-.01em}
  .sub{color:var(--muted);font-size:13px;margin-top:2px}
  button{background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:8px;
         padding:8px 14px;font:inherit;font-size:13px;cursor:pointer}
  button:hover{border-color:#3a4554}
  button:focus-visible{outline:2px solid var(--buy);outline-offset:2px}

  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:22px}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
  .kpi .l{color:var(--muted);font-size:12.5px}
  .kpi .v{font-size:24px;font-weight:650;margin-top:4px;font-variant-numeric:tabular-nums}
  .kpi .s{color:var(--muted);font-size:12.5px;margin-top:2px}
  .pos{color:var(--pos)} .neg{color:var(--neg)}

  section{margin-bottom:26px}
  h2{font-size:15px;font-weight:650;margin:0 0 10px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px}

  .alloc{display:flex;height:18px;border-radius:6px;overflow:hidden;margin:14px 16px 10px;background:var(--panel2)}
  .alloc div{height:100%}
  .legend{display:flex;flex-wrap:wrap;gap:6px 16px;padding:0 16px 14px;font-size:12.5px;color:var(--muted)}
  .legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px}
  .alert{margin:0 16px 14px;padding:9px 12px;border-radius:8px;background:rgba(232,162,59,.1);
         border:1px solid rgba(232,162,59,.35);font-size:13px}

  .tablewrap{overflow-x:auto}
  table{width:100%;border-collapse:collapse;min-width:860px;font-variant-numeric:tabular-nums}
  th,td{padding:11px 14px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
  th{color:var(--muted);font-weight:500;font-size:12.5px}
  th:first-child,td:first-child{text-align:left}
  th:last-child,td:last-child{text-align:left}
  tr:last-child td{border-bottom:0}
  .nm b{font-weight:600} .nm small{display:block;color:var(--muted);font-size:12px;white-space:normal;max-width:260px}
  .tag{display:inline-block;padding:3px 9px;border-radius:99px;font-size:12px;border:1px solid}
  .tag.hold{color:var(--hold);border-color:#3a4351}
  .tag.sell{color:var(--sell);border-color:rgba(232,162,59,.5);background:rgba(232,162,59,.08)}
  .tag.buy{color:var(--buy);border-color:rgba(90,169,240,.5);background:rgba(90,169,240,.08)}
  .tag.watch{color:var(--watch);border-color:rgba(181,140,240,.5);background:rgba(181,140,240,.08)}
  .gap{display:block;color:var(--muted);font-size:11.5px}
  .est{color:var(--muted);font-size:11px;margin-left:4px}

  .two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  @media(max-width:860px){.two{grid-template-columns:1fr}}
  .item{padding:13px 16px;border-bottom:1px solid var(--line)}
  .item:last-child{border-bottom:0}
  .item b{display:block;font-weight:600;margin-bottom:2px}
  .item span{color:var(--muted);font-size:13.5px}
  .ag{display:flex;gap:14px}
  .ag .d{min-width:62px;color:var(--buy);font-weight:600;font-size:13.5px}
  .ag .in{color:var(--muted);font-size:12px;display:block;font-weight:400}
  footer{color:var(--muted);font-size:12px;margin-top:24px;line-height:1.6}
  .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>PEA M. Porta · n° 017703412016</h1>
      <div class="sub" id="sub">Chargement…</div>
    </div>
    <button id="refresh">Actualiser les cours</button>
  </header>

  <div class="kpis" id="kpis"></div>

  <section>
    <h2>Répartition du portefeuille</h2>
    <div class="card">
      <div class="alloc" id="alloc" role="img" aria-label="Répartition par ligne"></div>
      <div class="legend" id="legend"></div>
      <div id="alert"></div>
    </div>
  </section>

  <section>
    <h2>Positions</h2>
    <div class="card tablewrap">
      <table>
        <thead><tr>
          <th>Valeur</th><th>Cours</th><th>Jour</th><th>Qté</th><th>PRU</th>
          <th>Valorisation</th><th>+/- value</th><th>Poids</th><th>Stratégie</th>
        </tr></thead>
        <tbody id="rows"></tbody>
      </table>
    </div>
  </section>

  <div class="two">
    <section>
      <h2>Mouvements planifiés</h2>
      <div class="card" id="moves"></div>
    </section>
    <section>
      <h2>Agenda du dernier trimestre 2026</h2>
      <div class="card" id="agenda"></div>
    </section>
  </div>

  <footer id="foot"></footer>
</div>

<script>
const eur = (n, d=0) => n.toLocaleString('fr-FR',{minimumFractionDigits:d,maximumFractionDigits:d}) + '\u00a0€';
const num = (n, d=2) => n.toLocaleString('fr-FR',{minimumFractionDigits:d,maximumFractionDigits:d});
const sgn = (n, f) => (n>0?'+':n<0?'−':'') + f(Math.abs(n));
const cls = n => n>0.005 ? 'pos' : n<-0.005 ? 'neg' : '';
const COLORS = ['#5aa9f0','#3fb98a','#b58cf0','#e8a23b','#ef6b5b','#4dc2c9','#d98ec4','#8fbf5a','#7c8cf0','#8b95a3'];

function render(d){
  document.getElementById('sub').textContent =
    'Positions du ' + d.export_date + ' · cours actualisés le ' + d.updated;

  const k = document.getElementById('kpis');
  k.innerHTML = `
    <div class="kpi"><div class="l">Valorisation des titres</div>
      <div class="v">${eur(d.total)}</div>
      <div class="s">Coût d'acquisition ${eur(d.cost)}</div></div>
    <div class="kpi"><div class="l">Plus-value latente</div>
      <div class="v ${cls(d.pv)}">${sgn(d.pv, x=>eur(x))}</div>
      <div class="s ${cls(d.pv_pct)}">${sgn(d.pv_pct, x=>num(x,1))}\u00a0% vs coût</div></div>
    <div class="kpi"><div class="l">Produit PE500 en attente</div>
      <div class="v">${eur(d.cash_pending)}</div>
      <div class="s">Estimation · pour L'Oréal · total avec liquidités ${eur(d.total_with_cash)}</div></div>
    <div class="kpi"><div class="l">Meilleure ligne</div>
      <div class="v pos">${sgn(d.best_pct, x=>num(x,0))}\u00a0%</div>
      <div class="s">${d.best}</div></div>
    <div class="kpi"><div class="l">Ligne la plus basse</div>
      <div class="v ${cls(d.worst_pct)}">${sgn(d.worst_pct, x=>num(x,1))}\u00a0%</div>
      <div class="s">${d.worst}</div></div>`;

  const a = document.getElementById('alloc'), lg = document.getElementById('legend');
  a.innerHTML = d.rows.map((r,i)=>`<div style="width:${r.weight}%;background:${COLORS[i%COLORS.length]}" title="${r.name} ${num(r.weight,1)} %"></div>`).join('');
  lg.innerHTML = d.rows.map((r,i)=>`<span><i style="background:${COLORS[i%COLORS.length]}"></i>${r.name} ${num(r.weight,1)}\u00a0%</span>`).join('');
  const big = d.rows.filter(r=>r.weight>d.concentration_alert);
  document.getElementById('alert').innerHTML = big.length
    ? `<div class="alert">${big.map(r=>`${r.name} pèse ${num(r.weight,1)}\u00a0% du PEA`).join(' · ')} — au-dessus du seuil de ${d.concentration_alert}\u00a0%.</div>` : '';

  document.getElementById('rows').innerHTML = d.rows.map(r=>{
    const gap = r.gap_target==null ? '' :
      `<span class="gap">cible ${num(r.target, r.target<100?0:0)}\u00a0€ · ${sgn(r.gap_target, x=>num(x,1))}\u00a0%</span>`;
    return `<tr>
      <td class="nm"><b>${r.name}</b><small>${r.note}</small></td>
      <td>${num(r.price)}\u00a0€${r.live?'':'<span class="est">export</span>'}</td>
      <td class="${cls(r.day||0)}">${r.day==null?'—':sgn(r.day, x=>num(x,2))+'\u00a0%'}</td>
      <td>${r.qty}</td>
      <td>${num(r.pru)}\u00a0€</td>
      <td>${eur(r.value)}</td>
      <td class="${cls(r.pv)}">${sgn(r.pv, x=>eur(x))}<span class="gap">${sgn(r.pv_pct, x=>num(x,1))}\u00a0%</span></td>
      <td>${num(r.weight,1)}\u00a0%</td>
      <td><span class="tag ${r.tone}">${r.action}</span>${gap}</td>
    </tr>`;}).join('');

  document.getElementById('moves').innerHTML = d.moves.map(m=>
    `<div class="item"><b>${m.title}</b><span>${m.text}</span></div>`).join('');

  const today = new Date();
  document.getElementById('agenda').innerHTML = d.agenda.map(e=>{
    const days = Math.ceil((new Date(e.date) - today)/86400000);
    const left = days>0 ? `<span class="in">dans ${days} j</span>` : '';
    return `<div class="item ag"><div class="d">${e.label}${left}</div><div><b>${e.title}</b><span>${e.text}</span></div></div>`;
  }).join('');

  const live = d.live_count===d.n;
  document.getElementById('foot').innerHTML =
    `<span class="dot" style="background:${live?'var(--pos)':'var(--sell)'}"></span>` +
    (live ? 'Cours Yahoo Finance en direct sur les ' + d.n + ' lignes.'
          : d.live_count + ' ligne(s) sur ' + d.n + ' en direct ; les autres reprennent le cours de l\'export du ' + d.export_date + '.') +
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
