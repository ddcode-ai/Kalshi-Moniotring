#!/usr/bin/env python3
"""Scarica i prezzi giornalieri dell'ultimo anno per i titoli del portafoglio.

Scrive data/portafoglio.json. Fonte principale: i grafici pubblici di Yahoo
Finance; se un titolo non risponde si prova Stooq. Nessuna chiave richiesta.
Si avvia con:  python scripts/portafoglio.py
"""
import csv
import datetime as dt
import io
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"

# (id, nome, simboli Yahoo da provare in ordine, simbolo Stooq o None, tipo)
# tipo: azione, etf, cambio, materia, tasso
TITOLI = [
    ("wdc", "Western Digital", ["WDC"], "wdc.us", "azione"),
    ("stx", "Seagate", ["STX"], "stx.us", "azione"),
    ("spot", "Spotify Technology", ["SPOT"], "spot.us", "azione"),
    ("enx", "Euronext", ["ENX.PA"], None, "azione"),
    ("tsm", "Taiwan Semiconductor (ADR)", ["TSM"], "tsm.us", "azione"),
    ("rok", "Rockwell Automation", ["ROK"], "rok.us", "azione"),
    ("abb", "ABB", ["ABBN.SW"], None, "azione"),
    ("medacta", "Medacta", ["MOVE.SW"], None, "azione"),
    ("moncler", "Moncler", ["MONC.MI"], None, "azione"),
    ("schneider", "Schneider Electric", ["SU.PA"], None, "azione"),
    ("us10y", "Treasury USA 10 anni (rendimento)", ["^TNX"], "10usy.b", "tasso"),
    ("usdchf", "USD/CHF", ["CHF=X", "USDCHF=X"], "usdchf", "cambio"),
    ("siemensenergy", "Siemens Energy", ["ENR.DE"], None, "azione"),
    ("hermes", "Hermès International", ["RMS.PA"], None, "azione"),
    ("oro", "Oro (XAU/USD)", ["XAUUSD=X", "GC=F"], "xauusd", "materia"),
    ("lonza", "Lonza Group", ["LONN.SW"], None, "azione"),
    ("wdef", "WisdomTree Europe Defence UCITS (EUR)", ["WDEF.MI", "WDEF.DE", "WDEF.AS", "WDEF.L"], None, "etf"),
    ("nvda", "NVIDIA", ["NVDA"], "nvda.us", "azione"),
    ("msft", "Microsoft", ["MSFT"], "msft.us", "azione"),
    ("ftnt", "Fortinet", ["FTNT"], "ftnt.us", "azione"),
    ("amd", "AMD", ["AMD"], "amd.us", "azione"),
    ("mu", "Micron", ["MU"], "mu.us", "azione"),
    ("aapl", "Apple", ["AAPL"], "aapl.us", "azione"),
    ("googl", "Alphabet A", ["GOOGL"], "googl.us", "azione"),
    ("vrt", "Vertiv Holdings", ["VRT"], "vrt.us", "azione"),
    ("meta", "Meta Platforms", ["META"], "meta.us", "azione"),
    ("panw", "Palo Alto Networks", ["PANW"], "panw.us", "azione"),
    ("gev", "GE Vernova", ["GEV"], "gev.us", "azione"),
]

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def scarica(url, tentativi=3):
    for n in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if n == tentativi - 1:
                raise
            time.sleep(2 * (n + 1))


def da_yahoo(simbolo):
    for host in ("query1", "query2"):
        url = (f"https://{host}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(simbolo)}"
               "?range=1y&interval=1d&includePrePost=false&events=")
        try:
            dati = json.loads(scarica(url))
        except Exception as e:
            ultimo_errore = e
            continue
        res = (dati.get("chart") or {}).get("result") or []
        if not res:
            ultimo_errore = RuntimeError("risposta vuota")
            continue
        r = res[0]
        meta = r.get("meta", {})
        offset = int(meta.get("gmtoffset") or 0)
        chiusure = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        punti = {}
        for ts, c in zip(r.get("timestamp") or [], chiusure):
            if c is None:
                continue
            giorno = dt.datetime.fromtimestamp(ts + offset, dt.timezone.utc).date().isoformat()
            punti[giorno] = c
        if len(punti) < 20:
            ultimo_errore = RuntimeError(f"solo {len(punti)} punti")
            continue
        return {
            "punti": sorted(punti.items()),
            "valuta": meta.get("currency") or "",
            "mercato": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
            "simbolo": simbolo,
            "fonte": "Yahoo Finance",
        }
    raise RuntimeError(f"Yahoo {simbolo}: {ultimo_errore}")


def da_stooq(simbolo):
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(simbolo)}&i=d"
    testo = scarica(url).decode("utf-8", "replace")
    righe = list(csv.DictReader(io.StringIO(testo)))
    limite = (dt.date.today() - dt.timedelta(days=366)).isoformat()
    punti = [(r["Date"], float(r["Close"])) for r in righe if r.get("Date", "") >= limite and r.get("Close")]
    if len(punti) < 20:
        raise RuntimeError(f"Stooq {simbolo}: solo {len(punti)} punti")
    return {"punti": punti, "valuta": "", "mercato": "", "simbolo": simbolo, "fonte": "Stooq"}


def arrotonda(v):
    return float(f"{v:.5g}")


def main():
    vecchi = {}
    file = DATA / "portafoglio.json"
    if file.exists():
        try:
            vecchi = {t["id"]: t for t in json.loads(file.read_text(encoding="utf-8")).get("titoli", [])}
        except Exception:
            vecchi = {}

    titoli, falliti = [], []
    for ident, nome, simboli_yahoo, simbolo_stooq, tipo in TITOLI:
        risultato, errori = None, []
        for s in simboli_yahoo:
            try:
                risultato = da_yahoo(s)
                break
            except Exception as e:
                errori.append(str(e))
            time.sleep(0.5)
        if risultato is None and simbolo_stooq:
            try:
                risultato = da_stooq(simbolo_stooq)
            except Exception as e:
                errori.append(str(e))
        if risultato is None:
            falliti.append(f"{nome}: {' | '.join(errori)}")
            if ident in vecchi:  # tiene i dati precedenti piuttosto che far sparire il titolo
                titoli.append(vecchi[ident])
            continue
        valuta = risultato["valuta"] or (vecchi.get(ident, {}).get("valuta", ""))
        if simboli_yahoo[0] in ("GC=F",) or risultato["simbolo"] == "GC=F":
            nota = "Prezzo dei futures sull'oro (Comex), molto vicino all'oro a pronti."
        else:
            nota = ""
        titoli.append({
            "id": ident, "nome": nome, "tipo": tipo, "simbolo": risultato["simbolo"],
            "valuta": valuta, "mercato": risultato["mercato"], "fonte": risultato["fonte"], "nota": nota,
            "punti": [[d, arrotonda(v)] for d, v in risultato["punti"]],
        })
        print(f"ok  {nome}: {risultato['simbolo']} ({risultato['fonte']}), {len(risultato['punti'])} punti")
        time.sleep(0.4)

    for f in falliti:
        print("NO ", f, file=sys.stderr)
    if len(falliti) == len(TITOLI):
        print("Nessun titolo scaricato: dati non modificati.", file=sys.stderr)
        sys.exit(1)

    DATA.mkdir(exist_ok=True)
    uscita = {"aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
              "non_aggiornati": [f.split(":")[0] for f in falliti], "titoli": titoli}
    file.write_text(json.dumps(uscita, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Portafoglio aggiornato: {len(titoli) - len(falliti)} su {len(TITOLI)} titoli")


if __name__ == "__main__":
    main()
