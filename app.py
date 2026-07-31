from flask import Flask, jsonify, render_template_string
import requests
import json
from datetime import datetime

app = Flask(__name__)

FINNHUB_KEY = "d9m7do9r01qpfnk7cbs0d9m7do9r01qpfnk7cbsg"

# Positions du portefeuille PEA
POSITIONS = [
    {"ticker": "ASML.AS",  "nom": "ASML Holding",       "code": "ASML",  "qte": 19,  "pru": 613.50, "couleur": "#2a78d6", "strat": "Surveiller"},
    {"ticker": "AI.PA",    "nom": "Air Liquide",          "code": "AI",    "qte": 98,  "pru": 170.00, "couleur": "#1baf7a", "strat": "Tenir"},
    {"ticker": "CS.PA",    "nom": "ETF Asie Émergents",   "code": "PAASI", "qte": 357, "pru": 26.38,  "couleur": "#eb6834", "strat": "Tenir"},
    {"ticker": "500.PA",   "nom": "ETF S&P 500",          "code": "PE500", "qte": 150, "pru": 41.51,  "couleur": "#eda100", "strat": "Tenir"},
    {"ticker": "AC.PA",    "nom": "Accor",                "code": "AC",    "qte": 132, "pru": 38.28,  "couleur": "#e87ba4", "strat": "Vendre 50€"},
    {"ticker": "GUARD.PA", "nom": "ETF Défense EU",       "code": "GUARD", "qte": 427, "pru": 11.95,  "couleur": "#008300", "strat": "Tenir"},
    {"ticker": "PINR.PA",  "nom": "ETF Inde MSCI",        "code": "PINR",  "qte": 154, "pru": 26.16,  "couleur": "#4a3aa7", "strat": "Tenir"},
    {"ticker": "GTT.PA",   "nom": "Gaztransport (GTT)",   "code": "GTT",   "qte": 13,  "pru": 191.14, "couleur": "#0fa86e", "strat": "Renforcer 175€"},
    {"ticker": "OR.PA",    "nom": "L'Oréal",              "code": "OR",    "qte": 5,   "pru": 378.15, "couleur": "#c4a060", "strat": "Renforcer"},
    {"ticker": "OVH.PA",   "nom": "OVHcloud",             "code": "OVH",   "qte": 23,  "pru": 9.61,   "couleur": "#6c5ce7", "strat": "Renforcer 10€"},
]

# Fallback cours si Finnhub ne répond pas
FALLBACK = {
    "ASML": 1411.10, "AI": 173.00, "PAASI": 36.53, "PE500": 53.48,
    "AC": 46.79, "GUARD": 11.58, "PINR": 22.96, "GTT": 190.20,
    "OR": 386.65, "OVH": 15.12
}

def get_quote(ticker):
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_KEY}"
        r = requests.get(url, timeout=5)
        data = r.json()
        if data.get("c") and data["c"] > 0:
            return {"cours": data["c"], "variation": data.get("dp", 0), "source": "live"}
    except:
        pass
    return None

@app.route("/api/cours")
def api_cours():
    result = []
    total_valo = 0
    total_cost = 0

    for p in POSITIONS:
        quote = get_quote(p["ticker"])
        if quote:
            cours = quote["cours"]
            variation = quote["variation"]
            source = "live"
        else:
            cours = FALLBACK.get(p["code"], p["pru"])
            variation = 0
            source = "estimé"

        valo = cours * p["qte"]
        cost = p["pru"] * p["qte"]
        pv_e = valo - cost
        pv_pct = (pv_e / cost) * 100
        total_valo += valo
        total_cost += cost

        result.append({
            **p,
            "cours": round(cours, 2),
            "variation": round(variation, 2),
            "valo": round(valo, 2),
            "pv_e": round(pv_e, 2),
            "pv_pct": round(pv_pct, 1),
            "source": source
        })

    # Trier par valorisation décroissante
    result.sort(key=lambda x: x["valo"], reverse=True)

    # Calculer les poids après tri
    for p in result:
        p["poids"] = round((p["valo"] / total_valo) * 100, 1)

    pv_totale = total_valo - total_cost
    return jsonify({
        "positions": result,
        "total_valo": round(total_valo, 2),
        "total_cost": round(total_cost, 2),
        "pv_totale": round(pv_totale, 2),
        "pv_pct": round((pv_totale / total_cost) * 100, 1),
        "updated": datetime.now().strftime("%d/%m/%Y %H:%M")
    })

HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PEA — M. Porta</title>
<style>
  :root {
    --bg: #0d1117; --surface: #161b22; --surface2: #1c2128; --border: #30363d;
    --text: #e6edf3; --text2: #8b949e; --text3: #484f58;
    --green: #2ea043; --green-bg: #0d2a0f; --green-t: #3fb950;
    --red: #da3633; --red-bg: #2d0f0f; --red-t: #f85149;
    --amber: #d29922; --blue: #388bfd; --mono: 'SF Mono', 'Monaco', monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; min-height: 100vh; }

  /* HEADER */
  .header { background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; position: sticky; top: 0; z-index: 10; }
  .header-left { display: flex; align-items: center; gap: 12px; }
  .header-icon { width: 36px; height: 36px; border-radius: 8px; background: linear-gradient(135deg, #388bfd, #8957e5); display: flex; align-items: center; justify-content: center; font-size: 16px; }
  .header-title { font-size: 16px; font-weight: 600; }
  .header-sub { font-size: 12px; color: var(--text2); margin-top: 1px; }
  .header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green-t); animation: pulse 2s infinite; display: inline-block; margin-right: 5px; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
  .live-tag { font-size: 11px; color: var(--green-t); display: flex; align-items: center; }
  .est-tag { font-size: 11px; color: var(--amber); display: none; }
  .refresh-btn { background: var(--surface2); border: 1px solid var(--border); color: var(--text); padding: 6px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: background .15s; font-family: inherit; }
  .refresh-btn:hover { background: var(--border); }
  .refresh-btn:disabled { opacity: .5; }
  .spin { display: inline-block; }
  .spin.loading { animation: spin .8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .ts { font-size: 11px; color: var(--text3); font-family: var(--mono); }

  /* KPIs */
  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); background: var(--surface); border-bottom: 1px solid var(--border); }
  .kpi { padding: 18px 24px; border-right: 1px solid var(--border); }
  .kpi:last-child { border-right: none; }
  .kpi-label { font-size: 11px; color: var(--text3); text-transform: uppercase; letter-spacing: .07em; margin-bottom: 6px; }
  .kpi-val { font-size: 24px; font-weight: 600; font-family: var(--mono); }
  .kpi-sub { font-size: 12px; color: var(--text2); margin-top: 4px; }

  /* CONTENT */
  .content { padding: 20px 24px; }

  /* TABLE */
  .table-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 20px; }
  .table-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); }
  .table-title { font-size: 13px; font-weight: 500; }
  table { width: 100%; border-collapse: collapse; }
  thead th { font-size: 11px; color: var(--text2); text-transform: uppercase; letter-spacing: .05em; padding: 8px 14px; text-align: right; border-bottom: 1px solid var(--border); background: var(--surface2); font-weight: 500; white-space: nowrap; }
  thead th:first-child { text-align: left; }
  thead th:nth-child(2) { text-align: left; }
  tbody tr { border-bottom: 1px solid var(--border); transition: background .1s; }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: var(--surface2); }
  td { padding: 11px 14px; text-align: right; font-size: 13px; font-family: var(--mono); color: var(--text); white-space: nowrap; }
  td:first-child { text-align: left; font-family: inherit; }
  td:nth-child(2) { text-align: left; font-family: inherit; }
  .ticker-name { font-size: 13px; font-weight: 500; display: flex; align-items: center; gap: 7px; }
  .ticker-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
  .ticker-sub { font-size: 11px; color: var(--text2); margin-top: 1px; }
  .poids-wrap { display: flex; align-items: center; gap: 6px; }
  .poids-bar { height: 4px; border-radius: 2px; min-width: 2px; }
  .poids-val { font-size: 11px; color: var(--text2); font-family: var(--mono); }
  .green { color: var(--green-t); }
  .red { color: var(--red-t); }
  .amber { color: var(--amber); }
  .pill { display: inline-block; font-size: 10px; font-weight: 500; padding: 2px 7px; border-radius: 5px; white-space: nowrap; }
  .pill-green { background: var(--green-bg); color: var(--green-t); border: 1px solid #1a4d1f; }
  .pill-red { background: var(--red-bg); color: var(--red-t); border: 1px solid #4d1a1a; }
  .pill-amber { background: #2d2205; color: var(--amber); border: 1px solid #4d3a0a; }
  .pill-blue { background: #0d1f3c; color: var(--blue); border: 1px solid #1a3a6c; }
  .pill-grey { background: var(--surface2); color: var(--text2); border: 1px solid var(--border); }
  .cours-live { color: var(--blue); }
  .cours-est { color: var(--amber); }
  .var-pos::before { content: '▲ '; font-size: 9px; }
  .var-neg::before { content: '▼ '; font-size: 9px; }

  /* ALLOC BAR */
  .alloc-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 20px; }
  .alloc-head { padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 13px; font-weight: 500; }
  .alloc-bar { display: flex; height: 10px; gap: 1px; }
  .alloc-legend { display: flex; flex-wrap: wrap; gap: 8px 16px; padding: 12px 16px; }
  .alloc-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text2); }
  .alloc-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }

  /* AGENDA */
  .bottom-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .side-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .side-head { padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 13px; font-weight: 500; }
  .agenda-item { display: flex; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--border); align-items: flex-start; }
  .agenda-item:last-child { border-bottom: none; }
  .agenda-date { font-size: 11px; font-weight: 600; color: var(--text2); min-width: 72px; font-family: var(--mono); padding-top: 2px; }
  .agenda-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 5px; }
  .agenda-title { font-size: 12px; font-weight: 500; margin-bottom: 2px; }
  .agenda-sub { font-size: 11px; color: var(--text2); }
  .mvt-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 16px; border-bottom: 1px solid var(--border); }
  .mvt-item:last-child { border-bottom: none; }
  .mvt-icon { font-size: 14px; flex-shrink: 0; }
  .mvt-title { font-size: 12px; font-weight: 500; margin-bottom: 2px; }
  .mvt-sub { font-size: 11px; color: var(--text2); line-height: 1.4; }

  /* ERROR */
  .error-banner { background: #2d1a05; border: 1px solid #4d3a0a; border-radius: 6px; padding: 8px 14px; margin-bottom: 14px; font-size: 12px; color: var(--amber); display: none; }

  @media (max-width: 768px) {
    .kpis { grid-template-columns: 1fr 1fr; }
    .bottom-grid { grid-template-columns: 1fr; }
    .content { padding: 12px; }
    .header { padding: 12px; }
    td, th { padding: 8px 8px; font-size: 11px; }
  }
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <div class="header-icon">📊</div>
    <div>
      <div class="header-title">PEA — M. Porta Matthieu</div>
      <div class="header-sub">N° 017703412016 · Euronext Paris</div>
    </div>
  </div>
  <div class="header-right">
    <span class="live-tag" id="liveTag"><span class="live-dot"></span>LIVE</span>
    <span class="est-tag" id="estTag">⚠ Cours estimés</span>
    <span class="ts" id="tsLabel">—</span>
    <button class="refresh-btn" id="refreshBtn" onclick="load()">
      <span class="spin" id="spinIcon">↻</span> Actualiser
    </button>
  </div>
</div>

<div class="kpis" id="kpis">
  <div class="kpi"><div class="kpi-label">Valorisation</div><div class="kpi-val" id="kTotal">—</div><div class="kpi-sub" id="kDate">—</div></div>
  <div class="kpi"><div class="kpi-label">Plus-value totale</div><div class="kpi-val" id="kPV">—</div><div class="kpi-sub" id="kPVpct">—</div></div>
  <div class="kpi"><div class="kpi-label">Meilleure perf.</div><div class="kpi-val green" id="kBest">—</div><div class="kpi-sub" id="kBestN">—</div></div>
  <div class="kpi"><div class="kpi-label">À surveiller</div><div class="kpi-val red" id="kWorst">—</div><div class="kpi-sub" id="kWorstN">—</div></div>
</div>

<div class="content">
  <div class="error-banner" id="errBanner">⚠ Impossible de récupérer les cours en temps réel. Affichage des derniers cours connus.</div>

  <div class="table-wrap">
    <div class="table-head">
      <span class="table-title">Positions</span>
      <span style="font-size:11px;color:var(--text2)" id="nbLines">10 lignes</span>
    </div>
    <table>
      <thead>
        <tr>
          <th style="text-align:left">Valeur</th>
          <th style="text-align:left">Poids</th>
          <th>Qté</th><th>PRU €</th><th>Cours</th>
          <th>Var.</th><th>Valorisation</th>
          <th>+/- €</th><th>+/- %</th><th>Stratégie</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>

  <div class="alloc-wrap">
    <div class="alloc-head">Allocation</div>
    <div class="alloc-bar" id="allocBar"></div>
    <div class="alloc-legend" id="allocLeg"></div>
  </div>

  <div class="bottom-grid">
    <div class="side-card">
      <div class="side-head">📅 Échéances H2 2026</div>
      <div class="agenda-item">
        <span class="agenda-date">T3 2026</span>
        <div class="agenda-dot" style="background:#e87ba4"></div>
        <div><div class="agenda-title">Clôture Essendi — Accor</div><div class="agenda-sub">675 M€ → annonce rachat 500 M€ · Catalyseur vers 50 €</div></div>
      </div>
      <div class="agenda-item">
        <span class="agenda-date">2 nov.</span>
        <div class="agenda-dot" style="background:#0fa86e"></div>
        <div><div class="agenda-title">CA T3 2026 — GTT</div><div class="agenda-sub">Nouvelles commandes T3 · Conférence 8h30</div></div>
      </div>
      <div class="agenda-item">
        <span class="agenda-date">20 oct.</span>
        <div class="agenda-dot" style="background:#6c5ce7"></div>
        <div><div class="agenda-title">FY2026 + Step Ahead — OVHcloud</div><div class="agenda-sub">Plan stratégique 2026–2030 · Renforcer à 10 € si convaincant</div></div>
      </div>
      <div class="agenda-item">
        <span class="agenda-date">Automne</span>
        <div class="agenda-dot" style="background:#1baf7a"></div>
        <div><div class="agenda-title">CA T3 — Air Liquide</div><div class="agenda-sub">Confirmation trajectoire 200 € · Objectif MS</div></div>
      </div>
      <div class="agenda-item">
        <span class="agenda-date">Automne</span>
        <div class="agenda-dot" style="background:#c4a060"></div>
        <div><div class="agenda-title">CA T3 — L'Oréal</div><div class="agenda-sub">1ères contributions Gucci Beauté attendues au S2</div></div>
      </div>
    </div>

    <div class="side-card">
      <div class="side-head">🎯 Mouvements planifiés</div>
      <div class="mvt-item">
        <span class="mvt-icon">🔴</span>
        <div><div class="mvt-title">VENDRE — Accor à 50 €</div><div class="mvt-sub">132 titres · Produit ~6 600 € → intégralement sur L'Oréal</div></div>
      </div>
      <div class="mvt-item">
        <span class="mvt-icon">🟢</span>
        <div><div class="mvt-title">RENFORCER — L'Oréal</div><div class="mvt-sub">~17 titres avec produit Accor · PRU cible ~382 € · Attendre repli 385–395 €</div></div>
      </div>
      <div class="mvt-item">
        <span class="mvt-icon">🟢</span>
        <div><div class="mvt-title">RENFORCER — GTT autour de 175 €</div><div class="mvt-sub">Améliore le PRU (191 €) · Dividende 4,7% · Post-résultats S1</div></div>
      </div>
      <div class="mvt-item">
        <span class="mvt-icon">🟡</span>
        <div><div class="mvt-title">SURVEILLER — OVHcloud à 10 €</div><div class="mvt-sub">Attendre plan Step Ahead du 20 octobre avant renforcement</div></div>
      </div>
      <div class="mvt-item">
        <span class="mvt-icon">⚪</span>
        <div><div class="mvt-title">TENIR — ASML (31,8% du PEA)</div><div class="mvt-sub">Concentration max atteinte · Ne pas renforcer · Surveiller export controls</div></div>
      </div>
    </div>
  </div>
</div>

<script>
function fmt(n, d=2) { return n.toLocaleString('fr-FR', {minimumFractionDigits:d, maximumFractionDigits:d}); }
function fmtE(n, d=2) { return fmt(n,d) + ' €'; }

function pillClass(strat) {
  if (strat.includes('Vendre')) return 'pill pill-red';
  if (strat.includes('Renforcer')) return 'pill pill-green';
  if (strat.includes('Surveiller')) return 'pill pill-amber';
  return 'pill pill-grey';
}

async function load() {
  const btn = document.getElementById('refreshBtn');
  const spin = document.getElementById('spinIcon');
  btn.disabled = true; spin.classList.add('loading');

  try {
    const r = await fetch('/api/cours');
    const d = await r.json();
    render(d);
    document.getElementById('errBanner').style.display = 'none';
  } catch(e) {
    document.getElementById('errBanner').style.display = 'block';
  }
  btn.disabled = false; spin.classList.remove('loading');
}

function render(d) {
  // KPIs
  document.getElementById('kTotal').textContent = fmtE(d.total_valo, 0);
  document.getElementById('kDate').textContent = 'au ' + d.updated;
  const pvEl = document.getElementById('kPV');
  pvEl.textContent = (d.pv_totale >= 0 ? '+' : '') + fmtE(d.pv_totale, 0);
  pvEl.className = 'kpi-val ' + (d.pv_totale >= 0 ? 'green' : 'red');
  document.getElementById('kPVpct').textContent = (d.pv_totale >= 0 ? '+' : '') + fmt(d.pv_pct) + '% vs coût d\'achat';

  const best = [...d.positions].sort((a,b) => b.pv_pct - a.pv_pct)[0];
  const worst = [...d.positions].sort((a,b) => a.pv_pct - b.pv_pct)[0];
  document.getElementById('kBest').textContent = '+' + fmt(best.pv_pct) + '%';
  document.getElementById('kBestN').textContent = best.code;
  document.getElementById('kWorst').textContent = fmt(worst.pv_pct) + '%';
  document.getElementById('kWorstN').textContent = worst.code;

  // Compteur live/estimé
  const hasLive = d.positions.some(p => p.source === 'live');
  document.getElementById('liveTag').style.display = hasLive ? 'flex' : 'none';
  document.getElementById('estTag').style.display = hasLive ? 'none' : 'block';
  document.getElementById('tsLabel').textContent = d.updated;

  // Table
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = d.positions.map(p => {
    const pvPos = p.pv_e >= 0;
    const pvClass = Math.abs(p.pv_pct) < 2 ? 'amber' : pvPos ? 'green' : 'red';
    const pillCls = p.pv_pct >= 2 ? 'pill pill-green' : p.pv_pct <= -2 ? 'pill pill-red' : 'pill pill-amber';
    const varClass = p.variation >= 0 ? 'green var-pos' : 'red var-neg';
    const coursClass = p.source === 'live' ? 'cours-live' : 'cours-est';
    const barW = Math.max(2, Math.round(p.poids * 1.2));

    return `<tr>
      <td>
        <div class="ticker-name"><span class="ticker-dot" style="background:${p.couleur}"></span>${p.code}</div>
        <div class="ticker-sub">${p.nom}</div>
      </td>
      <td>
        <div class="poids-wrap">
          <div class="poids-bar" style="width:${barW}px;background:${p.couleur}"></div>
          <span class="poids-val">${fmt(p.poids,1)}%</span>
        </div>
      </td>
      <td>${p.qte}</td>
      <td>${fmt(p.pru)}</td>
      <td class="${coursClass}">${fmt(p.cours)}</td>
      <td class="${varClass}">${Math.abs(p.variation).toFixed(2)}%</td>
      <td><strong>${fmtE(p.valo, 0)}</strong></td>
      <td class="${pvClass}">${p.pv_e >= 0 ? '+' : ''}${fmtE(p.pv_e, 0)}</td>
      <td><span class="${pillCls}">${p.pv_e >= 0 ? '+' : ''}${fmt(p.pv_pct,1)}%</span></td>
      <td><span class="${pillClass(p.strat)}">${p.strat}</span></td>
    </tr>`;
  }).join('');

  // Allocation bar
  const allocBar = document.getElementById('allocBar');
  const allocLeg = document.getElementById('allocLeg');
  allocBar.innerHTML = d.positions.map(p =>
    `<div style="flex:${p.poids};background:${p.couleur};min-width:2px" title="${p.code} ${p.poids}%"></div>`
  ).join('');
  allocLeg.innerHTML = d.positions.map(p =>
    `<div class="alloc-item"><span class="alloc-dot" style="background:${p.couleur}"></span>${p.code} ${fmt(p.poids,1)}%</div>`
  ).join('');
}

load();
setInterval(load, 120000); // Refresh auto toutes les 2 minutes
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
