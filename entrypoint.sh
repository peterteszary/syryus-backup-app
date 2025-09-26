#!/bin/sh

# Lefuttatjuk az adatbázis inicializáló szkriptet
echo ">>> Running Database Initializer..."
python init_db.py

# A KULCSFONTOSSÁGÚ ÚJ SOR:
# Átadjuk az 'instance' mappa (és a benne lévő database.db fájl)
# tulajdonjogát a 'www-data' felhasználónak és csoportnak.
# A Gunicorn alapértelmezetten ezt a felhasználót használja.
echo ">>> Setting ownership of database file..."
chown -R www-data:www-data /app/instance

# Elindítjuk a fő alkalmazást (a webszervert)
echo ">>> Starting Gunicorn Web Server..."
exec gunicorn --bind 0.0.0.0:5000 app:app