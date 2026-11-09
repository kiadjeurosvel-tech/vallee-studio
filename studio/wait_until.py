"""Attend l'heure de livraison (Europe/Berlin). Usage : python -m studio.wait_until 9"""
import datetime as dt
import sys
import time
from zoneinfo import ZoneInfo

hour = int(sys.argv[1]) if len(sys.argv) > 1 else 9
now = dt.datetime.now(ZoneInfo("Europe/Berlin"))
target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
wait = (target - now).total_seconds()
if 0 < wait <= 110 * 60:
    print(f"Livraison programmée à {target:%H:%M} (Berlin) : attente de {wait / 60:.0f} min.", flush=True)
    time.sleep(wait)
else:
    print(f"Il est {now:%H:%M} à Berlin : livraison immédiate.")
