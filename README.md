# Kalshi Osservatorio

Dashboard pubblica che segue cinque mercati di previsione di [Kalshi](https://kalshi.com):

- Accordo nucleare USA-Iran
- Primo ministro di Israele dopo le elezioni 2026
- Equilibrio di potere al Congresso USA (midterm 2026)
- Presidenziali francesi 2027
- Miglior modello di IA a fine 2029

## Come funziona

- `index.html` è la pagina, pubblicata con GitHub Pages.
- `data/quote.json` e `data/storico.json` contengono le quote e lo storico giornaliero.
- `scripts/aggiorna.py` scarica i dati dall'interfaccia pubblica di Kalshi (senza chiavi).
- `.github/workflows/aggiorna.yml` esegue lo script ogni mattina alle 05:15 UTC, salva i nuovi dati e ripubblica la pagina.

Per aggiornare subito: scheda **Actions** → **Aggiorna e pubblica** → **Run workflow**.

Per seguire un altro mercato, aggiungilo all'elenco `MERCATI` in `scripts/aggiorna.py` e in `index.html`.

Pagina informativa, non è un consiglio di investimento.
