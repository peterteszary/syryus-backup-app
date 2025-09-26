#!/bin/sh

# Várakozás, hogy az adatbázis szolgáltatás (ha lenne) elinduljon (jó gyakorlat)
# Ebben az esetben nem szükséges, de a jövőre nézve hasznos
# sleep 5

# Lefuttatjuk az adatbázis inicializáló szkriptet
echo ">>> Running Database Initializer..."
python init_db.py

# Elindítjuk a fő alkalmazást (a webszervert)
# Az 'exec' parancs fontos, mert átadja a fő processz szerepét a gunicornnak
echo ">>> Starting Gunicorn Web Server..."
exec gunicorn --bind 0.0.0.0:5000 app:app