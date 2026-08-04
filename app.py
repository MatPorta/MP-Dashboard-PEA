"""
Dashboard PEA — M. Porta Matthieu
Flask + Yahoo Finance (cours temps réel) + fallback statique
Version 3 — ajout variation intraday, objectif L'Oréal 375€, % sur barres
            d'allocation, design amélioré colonne Stratégie
"""

from flask import Flask, render_template_string
import requests
from datetime import datetime, timezone
import time

app = Flask(__name__)

# ---------------------------------------------------------------------------
# 1. COMPOSITION DU PEA — état au 31 juillet 2026 (export courtier)
#    ticker Yahoo Finance | quantité | PRU (€)
# ---------------------------------------------------------------------------
POSITIONS = [
    {"nom": "ASML Holding",   "ticker": "ASML.AS", "qte": 19,  "pru": 613.5011, "strategie": "Surveiller",       "fallback": 1459.50, "secteur": "Semi-conducteurs",        "type": "action"},
    {"nom": "Air Liquide",    "ticker": "AI.PA",   "qte": 98,  "pru": 170.1012, "strategie": "Tenir",             "fallback": 172.40, "secteur": "Gaz industriels",          "type": "action"},
    {"nom": "ETF Asie PAASI", "ticker": "PAASI.PA","qte": 357, "pru": 26.3803,  "strategie": "Tenir",             "fallback": 38.195, "secteur": "ETF géographique",         "type": "etf"},
    {"nom": "ETF S&P 500",    "ticker": "PE500.PA","qte": 150, "pru": 41.5128,  "strategie": "Tenir",             "fallback": 53.88, "secteur": "ETF géographique",          "type": "etf"},
    {"nom": "Accor",          "ticker": "AC.PA",   "qte": 132, "pru": 38.277,   "strategie": "Vendre 53 €",       "fallback": 45.65, "secteur": "Hôtellerie / Tourisme",    "type": "action"},
    {"nom": "GUARD Défense",  "ticker": "GUARD.PA","qte": 427, "pru": 11.9511,  "strategie": "Tenir",             "fallback": 11.668, "secteur": "Défense",                  "type": "action"},
    {"nom": "ETF Inde PINR",  "ticker": "PINR.PA", "qte": 154, "pru": 26.1556,  "strategie": "Tenir",             "fallback": 23.21, "secteur": "ETF géographique",          "type": "etf"},
    {"nom": "GTT",            "ticker": "GTT.PA",  "qte": 13,  "pru": 191.14,   "strategie": "Renforcer 175 €",   "fallback": 196.70, "secteur": "GNL / Énergie",           "type": "action"},
    {"nom": "L'Oréal",        "ticker": "OR.PA",   "qte": 5,   "pru": 378.146,  "strategie": "Renforcer 375 €",   "fallback": 386.65, "secteur": "Beauté / Consommation",   "type": "action"},
    {"nom": "OVHcloud",       "ticker": "OVH.PA",  "qte": 23,  "pru": 9.6109,   "strategie": "Renforcer 10 €",    "fallback": 14.89, "secteur": "Cloud souverain",          "type": "action"},
]


# ---------------------------------------------------------------------------
# 2. AGENDA H2 2026 & MOUVEMENTS PLANIFIÉS
# ---------------------------------------------------------------------------
AGENDA = [
    {"date": "Fin juillet / août 2026", "evenement": "Résultats S1 Accor → déclencheur potentiel ordre limite 50 €"},
    {"date": "T3 2026",                 "evenement": "Clôture cession Essendi (Accor → Blackstone) · 675 M€ + rachat d'actions 500 M€"},
    {"date": "Automne 2026",            "evenement": "CA T3 Air Liquide · Confirmation trajectoire 200 €"},
    {"date": "Automne 2026",            "evenement": "CA T3 L'Oréal · Premières contributions Gucci Beauté"},
    {"date": "2 novembre 2026",         "evenement": "CA T3 GTT · Nouvelles commandes · Conférence 8h30"},
    {"date": "10 décembre 2026",        "evenement": "Acompte dividende GTT 4,30 € (~55,90 € sur 13 titres)"},
    {"date": "20 octobre 2026",         "evenement": "FY2026 + Plan Step Ahead OVHcloud · Renforcer à 10 € si convaincant"},
]

MOUVEMENTS_PLANIFIES = [
    {"valeur": "Accor",    "action": "Vendre à 53 €",      "detail": "Ordre limite actif · 132 titres · Produit ~7 000 € → intégralement L'Oréal"},
    {"valeur": "L'Oréal",  "action": "Renforcer",           "detail": "Avec produit Accor (~17 titres) · Objectif d'achat : 375 € · PRU cible ~380 €"},
    {"valeur": "GTT",      "action": "Renforcer",           "detail": "Autour de 175 € · Améliore PRU de 191 € → ~183 € · Post-résultats S1"},
    {"valeur": "OVHcloud", "action": "Renforcer",           "detail": "À 10 € · Uniquement après Step Ahead du 20 octobre · Réserve ~660 €"},
    {"valeur": "ASML",     "action": "Ne pas toucher",      "detail": "Concentration max 31,8% du PEA · Surveiller export controls US"},
    {"valeur": "ETF S&P 500", "action": "Garder",           "detail": "150 titres (9,5%) · Coussin de diversification USA"},
]

# ---------------------------------------------------------------------------
# 2bis. FICHES PAR VALEUR — à mettre à jour manuellement au fil des discussions
#       et des publications. 3 champs : thèse principale, objectif de cours
#       consensus, prochain événement à surveiller.
# ---------------------------------------------------------------------------
FICHES = {
    "ASML.AS": {
        "these": "Monopole mondial EUV — seul fournisseur de machines de lithographie pour puces IA avancées.",
        "objectif": "1 900–2 300 € (Evercore / BofA / Oddo BHF)",
        "evenement": {"date": "Automne 2026", "texte": "Résultats T3 — surveiller les export controls US/Chine"},
    },
    "AI.PA": {
        "these": "Fournisseur indispensable des data centers IA, semi-conducteurs et hôpitaux — contrats indexés sur 15 ans.",
        "objectif": "200–206 € (Morgan Stanley / BofA, upgrades juillet 2026)",
        "evenement": {"date": "Automne 2026", "texte": "CA T3 — confirmation de la trajectoire vers 200 €"},
    },
    "AC.PA": {
        "these": "Cession de la participation Essendi à Blackstone (675 M€) + rachat d'actions 500 M€ — recentrage asset-light.",
        "objectif": "Pas de consensus documenté — objectif de vente personnel 53 €",
        "evenement": {"date": "Fin juillet / août 2026", "texte": "Résultats S1 — déclencheur potentiel de l'ordre de vente"},
    },
    "GUARD.PA": {
        "these": "Position de diversification sur le secteur de la défense européenne.",
        "objectif": "Non renseigné",
        "evenement": {"date": "—", "texte": "Prochaine publication à renseigner"},
    },
    "GTT.PA": {
        "these": "Monopole mondial des cuves cryogéniques pour méthaniers — modèle de redevances, marge EBITDA >65%.",
        "objectif": "230 € (BofA)",
        "evenement": {"date": "2 novembre 2026", "texte": "CA T3 · nouvelles commandes · conférence 8h30"},
    },
    "OR.PA": {
        "these": "N°1 mondial de la cosmétique — licence exclusive Gucci Beauté sur 50 ans, partenariat OpenAI.",
        "objectif": "425 € consensus (RBC 450 €, HSBC/Citi 435 €)",
        "evenement": {"date": "Automne 2026", "texte": "CA T3 · premières contributions Gucci Beauté"},
    },
    "OVH.PA": {
        "these": "Cloud souverain européen — contrat Commission européenne 180 M€, ambition LLM souverain.",
        "objectif": "~10 € consensus (cours actuel jugé trop éloigné pour renforcer)",
        "evenement": {"date": "20 octobre 2026", "texte": "FY2026 + dévoilement du plan Step Ahead"},
    },
    "PAASI.PA": {
        "these": "ETF de diversification géographique sur l'Asie — pas de thèse actionnaire spécifique.",
        "objectif": "Non applicable (ETF)",
        "evenement": {"date": "—", "texte": "Aucun catalyseur spécifique à surveiller"},
    },
    "PE500.PA": {
        "these": "ETF S&P 500 — coussin de diversification USA, réduit à 150 titres au profit d'Air Liquide.",
        "objectif": "Non applicable (ETF)",
        "evenement": {"date": "—", "texte": "Aucun catalyseur spécifique à surveiller"},
    },
    "PINR.PA": {
        "these": "ETF de diversification géographique sur l'Inde.",
        "objectif": "Non applicable (ETF)",
        "evenement": {"date": "—", "texte": "Aucun catalyseur spécifique à surveiller"},
    },
}

CACHE = {"data": None, "ts": 0}
CACHE_TTL = 120  # secondes — refresh auto toutes les 2 minutes


def fetch_quote(ticker: str):
    """Récupère (cours, variation_intraday_%, historique_cloture_3mois) via Yahoo Finance,
    en un seul appel (range=3mo/interval=1d) — le point courant sert à la fois pour le
    cours affiché et pour le dernier point de la sparkline. Fallback query2 puis (None, None, [])."""
    headers = {"User-Agent": "Mozilla/5.0"}
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{ticker}"
        try:
            r = requests.get(url, headers=headers, params={"range": "3mo", "interval": "1d"}, timeout=6)
            if r.status_code == 200:
                data = r.json()
                result = data.get("chart", {}).get("result")
                if result:
                    meta = result[0]["meta"]
                    price = meta.get("regularMarketPrice")
                    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
                    quote = result[0].get("indicators", {}).get("quote", [{}])[0]
                    closes = [c for c in quote.get("close", []) if c is not None]
                    if price:
                        price = round(float(price), 2)
                        change_pct = None
                        if prev_close:
                            change_pct = round((price - float(prev_close)) / float(prev_close) * 100, 2)
                        return price, change_pct, closes
        except Exception:
            continue
    return None, None, []


def generate_sparkline(closes, width=110, height=30, pad=3):
    """Construit les points d'une mini-courbe SVG (sparkline) à partir d'une liste de
    cours de clôture. Retourne None si pas assez de données."""
    if not closes or len(closes) < 2:
        return None
    lo, hi = min(closes), max(closes)
    rng = (hi - lo) or 1
    n = len(closes)
    pts = []
    for i, c in enumerate(closes):
        x = i / (n - 1) * width
        y = pad + (1 - (c - lo) / rng) * (height - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    points_str = " ".join(pts)
    area_points = f"0,{height} " + points_str + f" {width:.1f},{height}"
    trend_pct = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0
    return {
        "points": points_str,
        "area_points": area_points,
        "trend_pct": round(trend_pct, 1),
        "width": width,
        "height": height,
    }


def strat_style(strategie: str):
    """Retourne l'icône et la classe CSS associées à une stratégie."""
    s = strategie.lower()
    if "vendre" in s:
        return {"icon": "🔴", "cls": "strat-sell"}
    if "renforcer" in s:
        return {"icon": "🔵", "cls": "strat-buy"}
    if "surveiller" in s:
        return {"icon": "🟡", "cls": "strat-watch"}
    if "ne pas toucher" in s:
        return {"icon": "⚪", "cls": "strat-neutral"}
    if "garder" in s:
        return {"icon": "🟢", "cls": "strat-hold"}
    if "tenir" in s:
        return {"icon": "🟢", "cls": "strat-hold"}
    return {"icon": "⚙️", "cls": "strat-default"}


def build_portfolio():
    """Construit la liste des positions avec cours live, variation intraday ou fallback."""
    now = time.time()
    if CACHE["data"] and (now - CACHE["ts"] < CACHE_TTL):
        return CACHE["data"]

    rows = []
    total_valo = 0.0
    total_cout = 0.0
    live_count = 0

    for pos in POSITIONS:
        cours, var_jour, closes = fetch_quote(pos["ticker"])
        source = "live"
        if cours is None:
            cours = pos["fallback"]
            var_jour = None
            source = "estimé"
        else:
            live_count += 1

        valo = cours * pos["qte"]
        cout = pos["pru"] * pos["qte"]
        pv = valo - cout
        pv_pct = (pv / cout * 100) if cout else 0
        style = strat_style(pos["strategie"])

        # Fiche simplifiée (mise à jour manuelle au fil des discussions/publications)
        fiche = FICHES.get(pos["ticker"], {})

        # Mini-courbe de tendance sur 3 mois (sparkline)
        spark = generate_sparkline(closes)

        rows.append({
            **pos,
            "cours": cours,
            "var_jour": var_jour,
            "valo": valo,
            "pv": pv,
            "pv_pct": pv_pct,
            "source": source,
            "strat_icon": style["icon"],
            "strat_cls": style["cls"],
            "fiche": fiche,
            "spark": spark,
        })
        total_valo += valo
        total_cout += cout

    for row in rows:
        row["poids"] = (row["valo"] / total_valo * 100) if total_valo else 0

    rows.sort(key=lambda r: r["valo"], reverse=True)
    for i, row in enumerate(rows):
        row["color"] = f"hsl({(i * 37) % 360}, 55%, 50%)"

    # Agrégation par secteur
    secteurs = {}
    for row in rows:
        s = row["secteur"]
        secteurs.setdefault(s, 0.0)
        secteurs[s] += row["valo"]
    secteur_rows = [
        {"nom": s, "valo": v, "poids": (v / total_valo * 100) if total_valo else 0}
        for s, v in secteurs.items()
    ]
    secteur_rows.sort(key=lambda r: r["valo"], reverse=True)
    for i, s in enumerate(secteur_rows):
        s["color"] = f"hsl({(i * 53) % 360}, 45%, 45%)"

    def split_mosaic(items, threshold=10.0):
        """Sépare une liste triée (desc) en 2 lignes pour un rendu en mosaïque :
        ligne 1 = grosses positions (>= threshold%), ligne 2 = le reste.
        Garantit toujours au moins 1 élément en ligne 1."""
        row1 = [it for it in items if it["poids"] >= threshold]
        if not row1:
            row1 = items[:1]
        row2 = items[len(row1):]
        return row1, row2

    rows_row1, rows_row2 = split_mosaic(rows)
    secteurs_row1, secteurs_row2 = split_mosaic(secteur_rows)

    # Fiches : actions nominatives d'abord (triées par poids), puis ETF
    actions = sorted([r for r in rows if r["type"] == "action"], key=lambda r: r["poids"], reverse=True)
    etfs = sorted([r for r in rows if r["type"] == "etf"], key=lambda r: r["poids"], reverse=True)
    fiches_rows = actions + etfs

    result = {
        "secteurs": secteur_rows,
        "secteurs_row1": secteurs_row1,
        "secteurs_row2": secteurs_row2,
        "rows": rows,
        "rows_row1": rows_row1,
        "rows_row2": rows_row2,
        "fiches_rows": fiches_rows,
        "total_valo": total_valo,
        "total_cout": total_cout,
        "total_pv": total_valo - total_cout,
        "total_pv_pct": ((total_valo - total_cout) / total_cout * 100) if total_cout else 0,
        "updated_at": datetime.now(timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M"),
        "live_count": live_count,
        "total_count": len(rows),
    }
    CACHE["data"] = result
    CACHE["ts"] = now
    return result


TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PEA — M. Porta Matthieu</title>
<meta http-equiv="refresh" content="120">
<style>
  :root {
    --bg: #0b0e14;
    --panel: #131722;
    --panel-2: #1a1f2e;
    --border: #262b3a;
    --text: #e8eaf0;
    --text-dim: #8b92a8;
    --green: #3ecf8e;
    --red: #f26d6d;
    --accent: #5b8def;
    --gold: #d4af37;
    --amber: #e8b84b;
    --gray: #8b92a8;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    margin: 0;
    padding: 24px;
  }
  .wrap { max-width: 1150px; margin: 0 auto; }
  header { margin-bottom: 24px; }
  h1 { font-size: 1.5rem; margin: 0 0 4px 0; }
  .sub { color: var(--text-dim); font-size: 0.9rem; }
  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin: 20px 0 28px 0;
  }
  .kpi {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }
  .kpi .label { color: var(--text-dim); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .kpi .value { font-size: 1.5rem; font-weight: 600; margin-top: 4px; }
  .pos { color: var(--green); }
  .neg { color: var(--red); }
  .dim { color: var(--text-dim); }
  .panel {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 24px;
  }
  .panel h2 { font-size: 1.05rem; margin: 0 0 16px 0; color: var(--text); }
  table { width: 100%; border-collapse: collapse; font-size: 0.88rem; }
  th, td { padding: 10px 8px; text-align: right; border-bottom: 1px solid var(--border); }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--text-dim); font-weight: 500; font-size: 0.75rem; text-transform: uppercase; }
  tr:hover td { background: var(--panel-2); }

  /* Colonne Stratégie — design amélioré */
  .strat {
    font-size: 0.8rem;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 6px;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
  }
  .strat-buy    { color: var(--accent); background: rgba(91,141,239,0.12); }
  .strat-sell   { color: var(--red);    background: rgba(242,109,109,0.12); }
  .strat-hold   { color: var(--green);  background: rgba(62,207,142,0.12); }
  .strat-watch  { color: var(--amber);  background: rgba(232,184,75,0.12); }
  .strat-neutral{ color: var(--gray);   background: rgba(139,146,168,0.10); }
  .strat-default{ color: var(--text-dim); background: rgba(139,146,168,0.08); }

  .badge { font-size: 0.68rem; padding: 2px 6px; border-radius: 4px; margin-left: 6px; }
  .badge.live { background: rgba(62,207,142,0.15); color: var(--green); }
  .badge.estime { background: rgba(212,175,55,0.15); color: var(--gold); }
  .var-jour { font-size: 0.82rem; }

  /* Mosaïque proportionnelle (répartition) */
  .mosaic { display: flex; flex-direction: column; gap: 4px; margin-top: 10px; }
  .mosaic-row { display: flex; gap: 4px; }
  .mosaic-row.row1 { height: 78px; }
  .mosaic-row.row2 { height: 46px; }
  .mosaic-tile {
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    font-size: 0.72rem;
    font-weight: 600;
    color: #0b0e14;
    padding: 2px 6px;
    overflow: hidden;
    white-space: nowrap;
  }

  /* Timeline verticale (agenda / mouvements planifiés) */
  .timeline { position: relative; padding-left: 22px; margin-top: 4px; }
  .timeline::before {
    content: "";
    position: absolute;
    left: 4px;
    top: 4px;
    bottom: 4px;
    width: 1px;
    background: var(--border);
  }
  .timeline-item { position: relative; padding-bottom: 18px; }
  .timeline-item:last-child { padding-bottom: 0; }
  .timeline-dot {
    position: absolute;
    left: -22px;
    top: 3px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 2px solid var(--panel);
  }
  .timeline-date { font-size: 0.78rem; font-weight: 600; margin-bottom: 2px; }
  .timeline-txt { font-size: 0.88rem; color: var(--text); }
  .timeline-sub { color: var(--text-dim); }
  footer { text-align: center; color: var(--text-dim); font-size: 0.78rem; margin-top: 32px; }
  .refresh-note { color: var(--text-dim); font-size: 0.78rem; margin-top: 6px; }

  /* Fiches détaillées par valeur — version simplifiée */
  .fiches-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 14px;
  }
  .fiche {
    background: var(--panel-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
  }
  .fiche-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 10px;
    gap: 10px;
  }
  .fiche-titre { font-weight: 600; font-size: 0.95rem; }
  .fiche-secteur { color: var(--text-dim); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; margin-top: 2px; }
  .fiche-row {
    font-size: 0.85rem;
    line-height: 1.45;
    padding: 8px 0;
    border-top: 1px solid var(--border);
  }
  .fiche-row:first-of-type { border-top: none; padding-top: 0; }
  .fiche-row .fl { display: block; color: var(--text-dim); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 3px; }
  .fiche-row.evt .fl { color: var(--accent); }
  .fiche-spark {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
    border-top: 1px solid var(--border);
  }
  .fiche-spark svg { flex-shrink: 0; display: block; }
  .fiche-spark-meta { font-size: 0.75rem; }
  .fiche-spark-meta .fl { display: block; color: var(--text-dim); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 3px; }
  .fiche-spark-trend { font-weight: 600; font-size: 0.85rem; }
  .fiche-spark-trend.up { color: var(--green); }
  .fiche-spark-trend.down { color: var(--red); }

  /* Agenda + Mouvements planifiés côte à côte */
  .dual-panel {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 24px;
  }
  .dual-panel .panel { margin-bottom: 0; }
  @media (max-width: 720px) {
    .dual-panel { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>PEA — M. Porta Matthieu</h1>
    <div class="sub">N° 017703412016 · Mis à jour le {{ data.updated_at }} · {{ data.live_count }}/{{ data.total_count }} cours en direct</div>
  </header>

  <div class="kpis">
    <div class="kpi">
      <div class="label">Valorisation totale</div>
      <div class="value">{{ "%.0f"|format(data.total_valo) }} €</div>
    </div>
    <div class="kpi">
      <div class="label">Coût d'acquisition</div>
      <div class="value">{{ "%.0f"|format(data.total_cout) }} €</div>
    </div>
    <div class="kpi">
      <div class="label">Plus-value latente</div>
      <div class="value {{ 'pos' if data.total_pv >= 0 else 'neg' }}">
        {{ "+" if data.total_pv >= 0 else "" }}{{ "%.0f"|format(data.total_pv) }} €
      </div>
    </div>
    <div class="kpi">
      <div class="label">Performance</div>
      <div class="value {{ 'pos' if data.total_pv_pct >= 0 else 'neg' }}">
        {{ "+" if data.total_pv_pct >= 0 else "" }}{{ "%.1f"|format(data.total_pv_pct) }}%
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>Composition du portefeuille</h2>
    <table>
      <thead>
        <tr>
          <th>Valeur</th>
          <th>Cours</th>
          <th>Var. jour</th>
          <th>Qté</th>
          <th>PRU</th>
          <th>Valo</th>
          <th>+/-</th>
          <th>+/-%</th>
          <th>Poids</th>
          <th>Stratégie</th>
        </tr>
      </thead>
      <tbody>
        {% for r in data.rows %}
        <tr>
          <td>{{ r.nom }}</td>
          <td>{{ "%.2f"|format(r.cours) }} €
            <span class="badge {{ 'live' if r.source == 'live' else 'estime' }}">{{ r.source }}</span>
          </td>
          <td class="var-jour {{ 'pos' if r.var_jour is not none and r.var_jour >= 0 else ('neg' if r.var_jour is not none else 'dim') }}">
            {% if r.var_jour is not none %}{{ "+" if r.var_jour >= 0 else "" }}{{ "%.2f"|format(r.var_jour) }}%{% else %}—{% endif %}
          </td>
          <td>{{ r.qte }}</td>
          <td>{{ "%.2f"|format(r.pru) }} €</td>
          <td>{{ "%.0f"|format(r.valo) }} €</td>
          <td class="{{ 'pos' if r.pv >= 0 else 'neg' }}">{{ "+" if r.pv >= 0 else "" }}{{ "%.0f"|format(r.pv) }} €</td>
          <td class="{{ 'pos' if r.pv_pct >= 0 else 'neg' }}">{{ "+" if r.pv_pct >= 0 else "" }}{{ "%.1f"|format(r.pv_pct) }}%</td>
          <td>{{ "%.1f"|format(r.poids) }}%</td>
          <td><span class="strat {{ r.strat_cls }}">{{ r.strat_icon }} {{ r.strategie }}</span></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <div class="mosaic">
      <div class="mosaic-row row1">
        {% for r in data.rows_row1 %}
        <div class="mosaic-tile" style="flex: {{ r.poids }} 1 0%; background: {{ r.color }};" title="{{ r.nom }} — {{ '%.1f'|format(r.poids) }}%">
          {{ r.nom.split(' ')[0] }} {{ '%.1f'|format(r.poids) }}%
        </div>
        {% endfor %}
      </div>
      <div class="mosaic-row row2">
        {% for r in data.rows_row2 %}
        <div class="mosaic-tile" style="flex: {{ r.poids }} 1 0%; background: {{ r.color }};" title="{{ r.nom }} — {{ '%.1f'|format(r.poids) }}%">
          {{ (r.nom.split(' ')[0] + ' ' + '%.1f'|format(r.poids) + '%') if r.poids > 3 else ('%.1f'|format(r.poids) + '%' if r.poids > 1.2 else '') }}
        </div>
        {% endfor %}
      </div>
    </div>
    <div class="refresh-note">Répartition par valeur</div>

    <div class="mosaic" style="margin-top: 18px;">
      <div class="mosaic-row row1">
        {% for s in data.secteurs_row1 %}
        <div class="mosaic-tile" style="flex: {{ s.poids }} 1 0%; background: {{ s.color }};" title="{{ s.nom }} — {{ '%.1f'|format(s.poids) }}%">
          {{ s.nom.split(' ')[0] }} {{ '%.1f'|format(s.poids) }}%
        </div>
        {% endfor %}
      </div>
      <div class="mosaic-row row2">
        {% for s in data.secteurs_row2 %}
        <div class="mosaic-tile" style="flex: {{ s.poids }} 1 0%; background: {{ s.color }};" title="{{ s.nom }} — {{ '%.1f'|format(s.poids) }}%">
          {{ (s.nom.split(' ')[0] + ' ' + '%.1f'|format(s.poids) + '%') if s.poids > 3 else ('%.1f'|format(s.poids) + '%' if s.poids > 1.2 else '') }}
        </div>
        {% endfor %}
      </div>
    </div>
    <div class="refresh-note">Répartition par secteur</div>

    <div class="refresh-note" style="margin-top: 12px;">Actualisation automatique toutes les 2 minutes · Source : Yahoo Finance</div>
  </div>

  <div class="dual-panel">
    <div class="panel">
      <h2>Agenda H2 2026</h2>
      <div class="timeline">
        {% for a in agenda %}
        <div class="timeline-item">
          <div class="timeline-dot" style="background: var(--accent);"></div>
          <div class="timeline-date">{{ a.date }}</div>
          <div class="timeline-txt">{{ a.evenement }}</div>
        </div>
        {% endfor %}
      </div>
    </div>

    <div class="panel">
      <h2>Mouvements planifiés</h2>
      <div class="timeline">
        {% for m in mouvements %}
        <div class="timeline-item">
          <div class="timeline-dot" style="background: var(--gold);"></div>
          <div class="timeline-date">{{ m.valeur }} <span class="timeline-sub">— {{ m.action }}</span></div>
          <div class="timeline-txt">{{ m.detail }}</div>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>Fiches détaillées par valeur</h2>
    <div class="fiches-grid">
      {% for r in data.fiches_rows %}
      <div class="fiche">
        <div class="fiche-head">
          <div>
            <div class="fiche-titre">{{ r.nom }}</div>
            <div class="fiche-secteur">{{ r.secteur }}</div>
          </div>
          <span class="strat {{ r.strat_cls }}">{{ r.strat_icon }} {{ r.strategie }}</span>
        </div>

        {% if r.spark %}
        <div class="fiche-spark">
          <svg viewBox="0 0 {{ r.spark.width }} {{ r.spark.height }}" width="{{ r.spark.width }}" height="{{ r.spark.height }}">
            <polygon points="{{ r.spark.area_points }}" fill="{{ 'var(--green)' if r.spark.trend_pct >= 0 else 'var(--red)' }}" opacity="0.12"></polygon>
            <polyline points="{{ r.spark.points }}" fill="none" stroke="{{ 'var(--green)' if r.spark.trend_pct >= 0 else 'var(--red)' }}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"></polyline>
          </svg>
          <div class="fiche-spark-meta">
            <span class="fl">Tendance 3 mois</span>
            <span class="fiche-spark-trend {{ 'up' if r.spark.trend_pct >= 0 else 'down' }}">{{ '▲' if r.spark.trend_pct >= 0 else '▼' }} {{ '%.1f'|format(r.spark.trend_pct) }}%</span>
          </div>
        </div>
        {% endif %}

        {% if r.fiche.these %}
        <div class="fiche-row"><span class="fl">Thèse</span>{{ r.fiche.these }}</div>
        {% endif %}
        {% if r.fiche.objectif %}
        <div class="fiche-row"><span class="fl">Objectif de cours</span>{{ r.fiche.objectif }}</div>
        {% endif %}
        {% if r.fiche.evenement %}
        <div class="fiche-row evt"><span class="fl">À surveiller — {{ r.fiche.evenement.date }}</span>{{ r.fiche.evenement.texte }}</div>
        {% endif %}
      </div>
      {% endfor %}
    </div>
    <div class="refresh-note" style="margin-top: 14px;">Thèse, objectif de cours et prochain événement mis à jour manuellement au fil des discussions et publications</div>
  </div>

  <footer>
    Dashboard PEA · Outil de suivi personnel — ne constitue pas un conseil en investissement
  </footer>
</div>
</body>
</html>
"""


@app.route("/")
def dashboard():
    data = build_portfolio()
    return render_template_string(TEMPLATE, data=data, agenda=AGENDA, mouvements=MOUVEMENTS_PLANIFIES)


@app.route("/api/refresh")
def refresh():
    """Force un refresh du cache (utile pour le bouton manuel côté front)."""
    CACHE["ts"] = 0
    data = build_portfolio()
    return {"updated_at": data["updated_at"], "total_valo": round(data["total_valo"], 2)}


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
