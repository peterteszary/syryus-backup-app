#!/bin/sh

# Lefuttatjuk az adatbázis inicializáló szkriptet
echo ">>> Running Database Initializer..."
python init_db.py

# A KULCSFONTOSSÁGÚ ÚJ SOR:
# Jogosultságot adunk MINDEN felhasználónak, hogy írhassa és olvashassa
# az 'instance' mappát és a benne lévő fájlokat.
echo ">>> Setting universal permissions on database directory..."
chmod -R 777 /app/instance

# Elindítjuk a fő alkalmazást (a webszervert)
echo ">>> Starting Gunicorn Web Server..."
exec gunicorn --bind 0.0.0.0:5000 app:app