#!/usr/bin/env python3
"""Scarica da Kalshi le quote e lo storico dei mercati seguiti.

Scrive data/quote.json (le quote di oggi) e data/storico.json (lo storico
giornaliero). Usa solo l'interfaccia pubblica di Kalshi, senza chiavi.
Si avvia con:  python scripts/aggiorna.py
"""
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

API = "https://api.elections.kalshi.com/trade-api/v2"
DATA = pathlib.Path(__file__).resolve().parent.parent / "data"

# I mercati seguiti. "storico" sono gli esiti di cui si disegna l'andamento.
MERCATI = [
    {
        "id": "iran",
        "evento": "KXUSAIRANAGREEMENT-27",
        "serie": "KXUSAIRANAGREEMENT",
        "storico": ["KXUSAIRANAGREEMENT-27", "KXUSAIRANAGREEMENT-27-28", "KXUSAIRANAGREEMENT-27-29JAN20"],
        "inizio": "2026-04-14",
        "ordine": "scadenza",
        "minimo": 0.0,
    },
    {
        "id": "israele",
        "evento": "KXISRAELPM-26OCT27",
        "serie": "KXISRAELPM",
        "storico": ["KXISRAELPM-26OCT27-GEIZ", "KXISRAELPM-26OCT27-BNET", "KXISRAELPM-26OCT27-NBEN"],
        "inizio": "2026-04-11",
        "ordine": "prob",
        "minimo": 2.0,
    },
    {
        "id": "potere",
        "evento": "KXBALANCEPOWERCOMBO-27FEB",
        "serie": "KXBALANCEPOWERCOMBO",
        "storico": ["KXBALANCEPOWERCOMBO-27FEB-DD", "KXBALANCEPOWERCOMBO-27FEB-DR", "KXBALANCEPOWERCOMBO-27FEB-RR"],
        "inizio": "2025-12-11",
        "ordine": "prob",
        "minimo": 0.0,
    },
    {
        "id": "francia",
        "evento": "KXFRENCHPRES-27",
        "serie": "KXFRENCHPRES",
        "storico": ["KXFRENCHPRES-27-MLEP", "KXFRENCHPRES-27-EPHI", "KXFRENCHPRES-27-DLIS", "KXFRENCHPRES-27-JMEL"],
        "inizio": "2026-01-01",
        "ordine": "prob",
        "minimo": 1.0,
    },
    {
        "id": "llm",
        "evento": "KXBESTLLM-29DEC31",
        "serie": "KXBESTLLM",
        "storico": ["KXBESTLLM-29DEC31-GOOG", "KXBESTLLM-29DEC31-ANTH", "KXBESTLLM-29DEC31-OAI", "KXBESTLLM-29DEC31-XAI"],
        "inizio": "2026-10-09",
        "ordine": "prob",
        "minimo": 0.0,
        "massimo": 6,
    },
]

# Nomi in italiano per gli esiti che non sono nomi di persona o di azienda.
NOMI = {
    "KXBALANCEPOWERCOMBO-27FEB-DD": ("Democratici a Camera e Senato", "Dem. entrambe"),
    "KXBALANCEPOWERCOMBO-27FEB-DR": ("Camera ai Democratici, Senato ai Repubblicani", "Divisa (D Camera)"),
    "KXBALANCEPOWERCOMBO-27FEB-RR": ("Repubblicani a Camera e Senato", "Rep. entrambe"),
    "KXBALANCEPOWERCOMBO-27FEB-RD": ("Camera ai Repubblicani, Senato ai Democratici", "Divisa (R Camera)"),
}
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MESI_BREVI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
ATTIVI = {"active", "open", "initialized"}


def chiedi(percorso, parametri=None, tentativi=4):
    url = f"{API}{percorso}"
    if parametri:
        url += "?" + urllib.parse.urlencode(parametri)
    for n in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kalshi-osservatorio/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # rete instabile o limite di richieste: riprova
            if n == tentativi - 1:
                raise RuntimeError(f"Richiesta fallita: {url}: {e}") from e
            time.sleep(2 * (n + 1))


def numero(d, chiave_dollari, chiave_centesimi=None):
    """Legge un prezzo in dollari, sia nei campi *_dollars sia in centesimi."""
    v = d.get(chiave_dollari)
    if v not in (None, ""):
        return float(v)
    if chiave_centesimi and d.get(chiave_centesimi) is not None:
        return float(d[chiave_centesimi]) / 100
    return None


def punto_medio(bid, ask):
    """Probabilità in % come punto medio tra acquisto e vendita; None se il libro è vuoto."""
    if bid is None and ask is None:
        return None
    bid = bid or 0.0
    if ask is None or ask >= 1.0:
        return bid * 100 if bid > 0 else None
    return (bid + ask) / 2 * 100


def mercati_evento(evento):
    risultato, cursore = [], None
    while True:
        p = {"event_ticker": evento, "limit": 200}
        if cursore:
            p["cursor"] = cursore
        r = chiedi("/markets", p)
        risultato += r.get("markets", [])
        cursore = r.get("cursor")
        if not cursore:
            return risultato


def nomi_esito(cfg, m):
    t = m["ticker"]
    if t in NOMI:
        return NOMI[t]
    if cfg["ordine"] == "scadenza":
        chiusura = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).date()
        giorno = "1°" if chiusura.day == 1 else str(chiusura.day)
        return (f"Entro il {giorno} {MESI[chiusura.month - 1]} {chiusura.year}",
                f"{MESI_BREVI[chiusura.month - 1]} {chiusura.year}")
    nome = (m.get("yes_sub_title") or m.get("subtitle") or t).strip()
    partito = ""
    if "::" in (m.get("subtitle") or ""):
        partito = m["subtitle"].split("::", 1)[1].strip()
    esito = f"{nome} ({partito})" if partito else nome
    parti = nome.split()
    # Cognome senza il nome di battesimo: "Marine Le Pen" -> "Le Pen"
    breve = nome if cfg["id"] == "llm" or len(parti) < 2 else " ".join(parti[1:])
    return esito, breve


def candele(serie, ticker, inizio, fine):
    """Valori di fine giornata (punto medio) tra due date, a blocchi di 150 giorni."""
    valori = {}
    t0 = int(dt.datetime.combine(inizio, dt.time(), dt.timezone.utc).timestamp())
    t_fine = int(fine.timestamp())
    while t0 < t_fine:
        t1 = min(t0 + 150 * 86400, t_fine)
        r = chiedi(f"/series/{serie}/markets/{ticker}/candlesticks",
                   {"start_ts": t0, "end_ts": t1, "period_interval": 1440})
        for c in r.get("candlesticks", []):
            bid = numero(c.get("yes_bid") or {}, "close_dollars", "close")
            ask = numero(c.get("yes_ask") or {}, "close_dollars", "close")
            p = punto_medio(bid, ask)
            if p is not None:
                giorno = dt.datetime.fromtimestamp(c["end_period_ts"], dt.timezone.utc).date()
                valori[giorno] = p
        t0 = t1
        time.sleep(0.3)
    return valori


def main():
    adesso = dt.datetime.now(dt.timezone.utc)
    oggi = adesso.date()
    quote = {"aggiornato": adesso.isoformat(timespec="minutes"), "mercati": []}
    storico = {"aggiornato": quote["aggiornato"], "serie": []}

    for cfg in MERCATI:
        esiti = []
        for m in mercati_evento(cfg["evento"]):
            if m.get("status") not in ATTIVI and m["ticker"] not in cfg["storico"]:
                continue
            bid = numero(m, "yes_bid_dollars", "yes_bid")
            ask = numero(m, "yes_ask_dollars", "yes_ask")
            p = punto_medio(bid, ask)
            if p is None:
                p = (numero(m, "last_price_dollars", "last_price") or 0) * 100
            esito, breve = nomi_esito(cfg, m)
            esiti.append({
                "ticker": m["ticker"], "esito": esito, "etichetta": breve,
                "prob": round(p, 2),
                "acquisto": round((bid or 0) * 100, 1), "vendita": round((ask or 0) * 100, 1),
                "volume": round(float(m.get("volume_fp") or m.get("volume") or 0)),
                "chiusura": m.get("close_time"), "stato": m.get("status"),
            })
        if cfg["ordine"] == "scadenza":
            esiti = [e for e in esiti if e["stato"] in ATTIVI]
            esiti.sort(key=lambda e: e["chiusura"] or "")
        else:
            esiti.sort(key=lambda e: -e["prob"])
            esiti = [e for e in esiti if e["prob"] >= cfg["minimo"] or e["ticker"] in cfg["storico"]]
            if cfg.get("massimo"):
                tenuti = esiti[: cfg["massimo"]]
                tenuti += [e for e in esiti[cfg["massimo"]:] if e["ticker"] in cfg["storico"]]
                esiti = tenuti
        quote["mercati"].append({"id": cfg["id"], "esiti": esiti})
        per_ticker = {e["ticker"]: e for e in esiti}

        inizio = dt.date.fromisoformat(cfg["inizio"])
        for ticker in cfg["storico"]:
            valori = candele(cfg["serie"], ticker, inizio, adesso)
            if ticker in per_ticker:
                valori[oggi] = per_ticker[ticker]["prob"]
            if not valori:
                continue
            punti, giorno, ultimo = [], min(valori), None
            while giorno <= oggi:
                if giorno in valori:
                    ultimo = valori[giorno]
                if ultimo is not None:
                    punti.append([giorno.isoformat(), round(ultimo, 2)])
                giorno += dt.timedelta(days=1)
            etichetta = per_ticker.get(ticker, {}).get("etichetta", ticker)
            storico["serie"].append({"mercato": cfg["id"], "ticker": ticker, "etichetta": etichetta, "punti": punti})
        print(f"{cfg['id']}: {len(esiti)} esiti, {len(cfg['storico'])} serie storiche")

    DATA.mkdir(exist_ok=True)
    (DATA / "quote.json").write_text(json.dumps(quote, ensure_ascii=False, indent=1), encoding="utf-8")
    (DATA / "storico.json").write_text(json.dumps(storico, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Dati aggiornati:", quote["aggiornato"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Aggiornamento non riuscito:", e, file=sys.stderr)
        sys.exit(1)
