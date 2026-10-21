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
import urllib.error
import urllib.parse
import urllib.request

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"

# (id, nome, simboli Yahoo da provare in ordine, simbolo Stooq o None, tipo, codice Bloomberg)
# tipo: azione, etf, cambio, materia, tasso
TITOLI = [
    ("wdc", "Western Digital", ["WDC"], "wdc.us", "azione", "WDC US"),
    ("stx", "Seagate", ["STX"], "stx.us", "azione", "STX US"),
    ("spot", "Spotify Technology", ["SPOT"], "spot.us", "azione", "SPOT US"),
    ("enx", "Euronext", ["ENX.PA"], None, "azione", "ENX FP"),
    ("tsm", "Taiwan Semiconductor (ADR)", ["TSM"], "tsm.us", "azione", "TSM US"),
    ("rok", "Rockwell Automation", ["ROK"], "rok.us", "azione", "ROK US"),
    ("abb", "ABB", ["ABBN.SW"], None, "azione", "ABBN SW"),
    ("medacta", "Medacta", ["MOVE.SW"], None, "azione", "MOVE SW"),
    ("moncler", "Moncler", ["MONC.MI"], None, "azione", "MONC IM"),
    ("schneider", "Schneider Electric", ["SU.PA"], None, "azione", "SU FP"),
    ("us10y", "Treasury USA 10 anni (rendimento)", ["^TNX"], "10usy.b", "tasso", "USGG10YR Index"),
    ("usdchf", "USD/CHF", ["CHF=X", "USDCHF=X"], "usdchf", "cambio", "USDCHF Curncy"),
    ("siemensenergy", "Siemens Energy", ["ENR.DE"], None, "azione", "ENR GY"),
    ("hermes", "Hermès International", ["RMS.PA"], None, "azione", "RMS FP"),
    ("oro", "Oro (XAU/USD)", ["XAUUSD=X", "GC=F"], "xauusd", "materia", "XAU Curncy"),
    ("lonza", "Lonza Group", ["LONN.SW"], None, "azione", "LONN SW"),
    ("wdef", "WisdomTree Europe Defence UCITS (EUR)", ["WDEF.MI", "WDEF.DE", "WDEF.AS", "WDEF.L"], None, "etf", "WDEF IM"),
    ("nvda", "NVIDIA", ["NVDA"], "nvda.us", "azione", "NVDA US"),
    ("msft", "Microsoft", ["MSFT"], "msft.us", "azione", "MSFT US"),
    ("ftnt", "Fortinet", ["FTNT"], "ftnt.us", "azione", "FTNT US"),
    ("amd", "AMD", ["AMD"], "amd.us", "azione", "AMD US"),
    ("mu", "Micron", ["MU"], "mu.us", "azione", "MU US"),
    ("aapl", "Apple", ["AAPL"], "aapl.us", "azione", "AAPL US"),
    ("googl", "Alphabet A", ["GOOGL"], "googl.us", "azione", "GOOGL US"),
    ("vrt", "Vertiv Holdings", ["VRT"], "vrt.us", "azione", "VRT US"),
    ("meta", "Meta Platforms", ["META"], "meta.us", "azione", "META US"),
    ("panw", "Palo Alto Networks", ["PANW"], "panw.us", "azione", "PANW US"),
    ("gev", "GE Vernova", ["GEV"], "gev.us", "azione", "GEV US"),
    ("amzn", "Amazon", ["AMZN"], "amzn.us", "azione", "AMZN US"),
]

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


import http.cookiejar

_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
_crumb = None


def scarica(url, tentativi=3):
    for n in range(tentativi):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})
            with _opener.open(req, timeout=20) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if n == tentativi - 1 or e.code not in (429, 500, 502, 503):
                raise
            time.sleep(5 * (n + 1))
        except Exception:
            if n == tentativi - 1:
                raise
            time.sleep(2 * (n + 1))


def crumb_yahoo():
    """Come fa il browser: prima un cookie di sessione, poi il 'crumb' da allegare alle richieste."""
    global _crumb
    if _crumb is not None:
        return _crumb
    for url in ("https://fc.yahoo.com", "https://finance.yahoo.com/"):
        try:
            scarica(url, tentativi=1)
        except Exception:
            pass  # risponde spesso con un errore, ma imposta comunque il cookie
    for host in ("query1", "query2"):
        try:
            c = scarica(f"https://{host}.finance.yahoo.com/v1/test/getcrumb", tentativi=2).decode().strip()
            if c and "<" not in c and len(c) < 50:
                _crumb = c
                return c
        except Exception as e:
            print("crumb non ottenuto:", host, e, file=sys.stderr)
    _crumb = ""
    return ""


def da_yahoo(simbolo):
    """Usa la libreria yfinance, che imita un browser e non viene bloccata come le richieste semplici."""
    import yfinance as yf
    t = yf.Ticker(simbolo)
    storia = t.history(period="2y", interval="1d", auto_adjust=False, raise_errors=True)
    storia = storia.dropna(subset=["Close"])
    if len(storia) < 20:
        raise RuntimeError(f"Yahoo {simbolo}: solo {len(storia)} punti")
    punti = {}
    for indice, riga in storia.iterrows():
        punti[indice.date().isoformat()] = float(riga["Close"])
    meta = getattr(t, "history_metadata", None) or {}
    return {
        "punti": sorted(punti.items()),
        "valuta": meta.get("currency") or "",
        "mercato": meta.get("fullExchangeName") or meta.get("exchangeName") or "",
        "simbolo": simbolo,
        "fonte": "Yahoo Finance",
    }


def da_stooq(simbolo):
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(simbolo)}&i=d"
    testo = scarica(url).decode("utf-8", "replace")
    if not testo.startswith("Date"):
        raise RuntimeError(f"Stooq {simbolo}: risposta inattesa: {testo[:80]!r}")
    righe = list(csv.DictReader(io.StringIO(testo)))
    limite = (dt.date.today() - dt.timedelta(days=740)).isoformat()
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

    titoli, falliti, ok = [], [], []
    for ident, nome, simboli_yahoo, simbolo_stooq, tipo, bbg in TITOLI:
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
                vecchi[ident]["bbg"] = bbg
                titoli.append(vecchi[ident])
            continue
        valuta = risultato["valuta"] or (vecchi.get(ident, {}).get("valuta", ""))
        if simboli_yahoo[0] in ("GC=F",) or risultato["simbolo"] == "GC=F":
            nota = "Prezzo dei futures sull'oro (Comex), molto vicino all'oro a pronti."
        else:
            nota = ""
        titoli.append({
            "id": ident, "nome": nome, "tipo": tipo, "simbolo": risultato["simbolo"], "bbg": bbg,
            "valuta": valuta, "mercato": risultato["mercato"], "fonte": risultato["fonte"], "nota": nota,
            "punti": [[d, arrotonda(v)] for d, v in risultato["punti"]],
        })
        print(f"ok  {nome}: {risultato['simbolo']} ({risultato['fonte']}), {len(risultato['punti'])} punti")
        ok.append(f"{nome}: {risultato['simbolo']} ({risultato['fonte']})")
        time.sleep(0.4)

    for f in falliti:
        print("NO ", f, file=sys.stderr)
        print(f"::warning title=Portafoglio::{f[:900]}")
    print(f"::notice title=Portafoglio crumb::{'si' if _crumb else 'no'}")
    print(f"::notice title=Portafoglio::Scaricati {len(ok)} su {len(TITOLI)}: " + "; ".join(ok)[:3000])
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
