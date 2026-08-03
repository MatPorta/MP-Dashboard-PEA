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
    {"nom": "ASML Holding",   "ticker": "ASML.AS", "qte": 19,  "pru": 613.5011, "strategie": "Surveiller",       "fallback": 1459.50, "secteur": "Semi-conducteurs"},
    {"nom": "Air Liquide",    "ticker": "AI.PA",   "qte": 98,  "pru": 170.1012, "strategie": "Tenir",             "fallback": 172.40, "secteur": "Gaz industriels"},
    {"nom": "ETF Asie PAASI", "ticker": "PAASI.PA","qte": 357, "pru": 26.3803,  "strategie": "Tenir",             "fallback": 38.195, "secteur": "ETF géographique"},
    {"nom": "ETF S&P 500",    "ticker": "PE500.PA","qte": 150, "pru": 41.5128,  "strategie": "Tenir",             "fallback": 53.88, "secteur": "ETF géographique"},
    {"nom": "Accor",          "ticker": "AC.PA",   "qte": 132, "pru": 38.277,   "strategie": "Vendre 53 €",       "fallback": 45.65, "secteur": "Hôtellerie / Tourisme"},
    {"nom": "GUARD Défense",  "ticker": "GUARD.PA","qte": 427, "pru": 11.9511,  "strategie": "Tenir",             "fallback": 11.668, "secteur": "Défense"},
    {"nom": "ETF Inde PINR",  "ticker": "PINR.PA", "qte": 154, "pru": 26.1556,  "strategie": "Tenir",             "fallback": 23.21, "secteur": "ETF géographique"},
    {"nom": "GTT",            "ticker": "GTT.PA",  "qte": 13,  "pru": 191.14,   "strategie": "Renforcer 175 €",   "fallback": 196.70, "secteur": "GNL / Énergie"},
    {"nom": "L'Oréal",        "ticker": "OR.PA",   "qte": 5,   "pru": 378.146,  "strategie": "Renforcer 375 €",   "fallback": 386.65, "secteur": "Beauté / Consommation"},
    {"nom": "OVHcloud",       "ticker": "OVH.PA",  "qte": 23,  "pru": 9.6109,   "strategie": "Renforcer 10 €",    "fallback": 14.89, "secteur": "Cloud souverain"},
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
# 2bis. FONDAMENTAUX PAR VALEUR — à mettre à jour manuellement à chaque publication
#       (T1/S1/T3/FY). Champs optionnels : laisser vide/None si non applicable
#       (ex. ETF) ou pas encore connu.
# ---------------------------------------------------------------------------
FONDAMENTAUX = {
    "ASML.AS": {
        "maj": "31/07/2026",
        "publication": "T2 2026 — résultats records",
        "croissance_ca": "CA 9,33 Mds€ · guidance relevée 43–45 Mds€",
        "bpa": "7,59 € vs 6,89 € attendu (+10,2%)",
        "indicateur_cle": {"label": "Exposition Chine", "valeur": "~20% du CA — risque export controls US"},
        "catalyseur": {"date": "Automne 2026", "texte": "Résultats T3 — à surveiller"},
    },
    "AI.PA": {
        "maj": "28/07/2026",
        "publication": "S1 2026",
        "croissance_ca": "CA 13,82 Mds€ · +2,6% comparable (+3,5% au T2)",
        "bpa": "Marge opérationnelle 20,9% (+110 bps, record)",
        "indicateur_cle": {"label": "Guidances 2026/2027", "valeur": "Confirmées · +100 bps supplémentaires en 2027"},
        "catalyseur": {"date": "Automne 2026", "texte": "CA T3 · Confirmation trajectoire 200 €"},
    },
    "PAASI.PA": {
        "maj": "31/07/2026",
        "publication": None,
        "croissance_ca": None,
        "bpa": None,
        "indicateur_cle": {"label": "Nature", "valeur": "ETF géographique — pas de publication trimestrielle"},
        "catalyseur": {"date": "—", "texte": "Coussin de diversification Asie"},
    },
    "PE500.PA": {
        "maj": "31/07/2026",
        "publication": None,
        "croissance_ca": None,
        "bpa": None,
        "indicateur_cle": {"label": "Nature", "valeur": "ETF géographique — pas de publication trimestrielle"},
        "catalyseur": {"date": "—", "texte": "Coussin de diversification USA · 150 titres conservés"},
    },
    "AC.PA": {
        "maj": "31/07/2026",
        "publication": "Résultats S1 attendus",
        "croissance_ca": "Non publié à date",
        "bpa": "Non publié à date",
        "indicateur_cle": {"label": "Cession Essendi", "valeur": "→ Blackstone · 675 M€ + rachat d'actions 500 M€"},
        "catalyseur": {"date": "Fin juillet / août 2026", "texte": "Résultats S1 → déclencheur ordre limite vente"},
    },
    "GUARD.PA": {
        "maj": "31/07/2026",
        "publication": None,
        "croissance_ca": None,
        "bpa": None,
        "indicateur_cle": {"label": "Thèse", "valeur": "Exposition secteur défense européen"},
        "catalyseur": {"date": "—", "texte": "Prochaine publication à renseigner"},
    },
    "PINR.PA": {
        "maj": "31/07/2026",
        "publication": None,
        "croissance_ca": None,
        "bpa": None,
        "indicateur_cle": {"label": "Nature", "valeur": "ETF géographique — pas de publication trimestrielle"},
        "catalyseur": {"date": "—", "texte": "Exposition croissance indienne"},
    },
    "GTT.PA": {
        "maj": "28/07/2026",
        "publication": "S1 2026",
        "croissance_ca": "CA 387,3 M€ (stable) · RN 210,4 M€ (+16,9%)",
        "bpa": "5,68 € vs 5,00 € attendu (+13,6%)",
        "indicateur_cle": {"label": "Carnet de commandes", "valeur": "1,853 Md€ — record historique · 65 commandes S1 dont 56 méthaniers"},
        "catalyseur": {"date": "2 novembre 2026", "texte": "CA T3 · Conférence 8h30"},
    },
    "OR.PA": {
        "maj": "29/07/2026",
        "publication": "S1 2026",
        "croissance_ca": "CA 23,77 Mds€ · +6,8% comparable",
        "bpa": "RN 3,55 Mds€ (+5,4%) · Marge 21,3% (+20 bps, record)",
        "indicateur_cle": {"label": "Gucci Beauté", "valeur": "Pas encore dans les chiffres — contribution attendue S2 2026"},
        "catalyseur": {"date": "Automne 2026", "texte": "CA T3 · Premières contributions Gucci Beauté"},
    },
    "OVH.PA": {
        "maj": "25/06/2026",
        "publication": "T3 FY2026",
        "croissance_ca": "+6,9% organique (haut de fourchette guidance +5–7%)",
        "bpa": "FCF positif · EBITDA en hausse · guidances confirmées",
        "indicateur_cle": {"label": "Plan Step Ahead", "valeur": "Non dévoilé — promis depuis octobre 2025"},
        "catalyseur": {"date": "20 octobre 2026", "texte": "FY2026 + Plan Step Ahead"},
    },
}

CACHE = {"data": None, "ts": 0}
CACHE_TTL = 120  # secondes — refresh auto toutes les 2 minutes


def fetch_quote(ticker: str):
    """Récupère (cours, variation_intraday_%) via Yahoo Finance, avec fallback query2 puis (None, None)."""
    headers = {"User-Agent": "Mozilla/5.0"}
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{ticker}"
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                data = r.json()
                result = data.get("chart", {}).get("result")
                if result:
                    meta = result[0]["meta"]
                    price = meta.get("regularMarketPrice")
                    prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
                    if price:
                        price = round(float(price), 2)
                        change_pct = None
                        if prev_close:
                            change_pct = round((price - float(prev_close)) / float(prev_close) * 100, 2)
                        return price, change_pct
        except Exception:
            continue
    return None, None


def fetch_live_extras(tickers):
    """Récupère en un seul appel batch le PER (trailingPE) et le range 52 semaines
    pour une liste de tickers, via l'endpoint Yahoo Finance /v7/finance/quote.
    Retourne un dict {ticker: {"per": float|None, "w52_low": float|None, "w52_high": float|None}}.
    Best-effort : en cas d'échec, retourne un dict vide (le template affichera '—')."""
    headers = {"User-Agent": "Mozilla/5.0"}
    symbols = ",".join(tickers)
    extras = {}
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v7/finance/quote"
        try:
            r = requests.get(url, headers=headers, params={"symbols": symbols}, timeout=6)
            if r.status_code == 200:
                results = r.json().get("quoteResponse", {}).get("result", [])
                for q in results:
                    extras[q.get("symbol")] = {
                        "per": q.get("trailingPE"),
                        "w52_low": q.get("fiftyTwoWeekLow"),
                        "w52_high": q.get("fiftyTwoWeekHigh"),
                    }
                if extras:
                    return extras
        except Exception:
            continue
    return extras


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

    extras = fetch_live_extras([p["ticker"] for p in POSITIONS])

    for pos in POSITIONS:
        cours, var_jour = fetch_quote(pos["ticker"])
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

        # Indicateurs live (PER, range 52 semaines)
        ex = extras.get(pos["ticker"], {})
        per = ex.get("per")
        w52_low = ex.get("w52_low")
        w52_high = ex.get("w52_high")
        w52_pos_pct = None
        if w52_low is not None and w52_high is not None and w52_high > w52_low:
            w52_pos_pct = max(0, min(100, (cours - w52_low) / (w52_high - w52_low) * 100))

        # Indicateurs fondamentaux (mis à jour manuellement à chaque publication)
        fond = FONDAMENTAUX.get(pos["ticker"], {})

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
            "per": per,
            "w52_low": w52_low,
            "w52_high": w52_high,
            "w52_pos_pct": w52_pos_pct,
            "fond": fond,
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

    result = {
        "secteurs": secteur_rows,
        "secteurs_row1": secteurs_row1,
        "secteurs_row2": secteurs_row2,
        "rows": rows,
        "rows_row1": rows_row1,
        "rows_row2": rows_row2,
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

  /* Fiches détaillées par valeur */
  .fiches-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
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
  }
  .fiche-titre { font-weight: 600; font-size: 0.95rem; }
  .fiche-secteur { color: var(--text-dim); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.03em; margin-top: 2px; }
  .fiche-live {
    display: flex;
    gap: 18px;
    margin: 10px 0 12px 0;
    padding: 10px 0;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
  }
  .fiche-live-item { flex: 1; }
  .fiche-live-label { color: var(--text-dim); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.03em; }
  .fiche-live-val { font-size: 1.05rem; font-weight: 600; margin-top: 2px; }
  .w52-bar {
    position: relative;
    height: 6px;
    border-radius: 3px;
    background: var(--border);
    margin-top: 6px;
    overflow: visible;
  }
  .w52-fill {
    position: absolute;
    top: -3px;
    width: 3px;
    height: 12px;
    border-radius: 2px;
    background: var(--accent);
  }
  .w52-range { color: var(--text-dim); font-size: 0.68rem; margin-top: 4px; display: flex; justify-content: space-between; }
  .fiche-row {
    font-size: 0.82rem;
    margin-bottom: 7px;
    line-height: 1.4;
  }
  .fiche-row .fl { color: var(--text-dim); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.02em; margin-right: 6px; }
  .fiche-cata {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--border);
    font-size: 0.8rem;
  }
  .fiche-cata .fl { color: var(--gold); font-weight: 600; }
  .fiche-maj { color: var(--text-dim); font-size: 0.68rem; margin-top: 8px; text-align: right; }
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
    <h2>Fiches détaillées par valeur</h2>
    <div class="fiches-grid">
      {% for r in data.rows %}
      <div class="fiche">
        <div class="fiche-head">
          <div>
            <div class="fiche-titre">{{ r.nom }}</div>
            <div class="fiche-secteur">{{ r.secteur }}</div>
          </div>
          <span class="strat {{ r.strat_cls }}">{{ r.strat_icon }} {{ r.strategie }}</span>
        </div>

        <div class="fiche-live">
          <div class="fiche-live-item">
            <div class="fiche-live-label">PER</div>
            <div class="fiche-live-val">{% if r.per %}{{ "%.1f"|format(r.per) }}x{% else %}—{% endif %}</div>
          </div>
          <div class="fiche-live-item" style="flex: 2;">
            <div class="fiche-live-label">Position range 52 sem.</div>
            {% if r.w52_pos_pct is not none %}
            <div class="w52-bar">
              <div class="w52-fill" style="left: calc({{ r.w52_pos_pct }}% - 1.5px);"></div>
            </div>
            <div class="w52-range">
              <span>{{ "%.1f"|format(r.w52_low) }} €</span>
              <span>{{ "%.0f"|format(r.w52_pos_pct) }}%</span>
              <span>{{ "%.1f"|format(r.w52_high) }} €</span>
            </div>
            {% else %}
            <div class="fiche-live-val">—</div>
            {% endif %}
          </div>
        </div>

        {% if r.fond.publication %}
        <div class="fiche-row"><span class="fl">Publication</span>{{ r.fond.publication }}</div>
        {% endif %}
        {% if r.fond.croissance_ca %}
        <div class="fiche-row"><span class="fl">CA</span>{{ r.fond.croissance_ca }}</div>
        {% endif %}
        {% if r.fond.bpa %}
        <div class="fiche-row"><span class="fl">Résultat</span>{{ r.fond.bpa }}</div>
        {% endif %}
        {% if r.fond.indicateur_cle %}
        <div class="fiche-row"><span class="fl">{{ r.fond.indicateur_cle.label }}</span>{{ r.fond.indicateur_cle.valeur }}</div>
        {% endif %}

        {% if r.fond.catalyseur %}
        <div class="fiche-cata">
          <span class="fl">{{ r.fond.catalyseur.date }} —</span> {{ r.fond.catalyseur.texte }}
        </div>
        {% endif %}

        {% if r.fond.maj %}
        <div class="fiche-maj">Fondamentaux mis à jour le {{ r.fond.maj }}</div>
        {% endif %}
      </div>
      {% endfor %}
    </div>
    <div class="refresh-note" style="margin-top: 14px;">PER et range 52 semaines : Yahoo Finance (temps réel) · CA/résultats/indicateurs clés : mis à jour manuellement à chaque publication</div>
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
