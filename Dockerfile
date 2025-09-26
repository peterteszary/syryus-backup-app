# 1. lépés: Hivatalos Python alap-image használata
FROM python:3.9-slim

# 2. lépés: Rendszer szintű függőségek telepítése (JAVÍTOTT RÉSZ)
RUN apt-get update && apt-get install -y \
    lftp \
    mariadb-client \
    && rm -rf /var/lib/apt/lists/*

# 3. lépés: Munkakönyvtár beállítása a konténeren belül
WORKDIR /app

# 4. lépés: A függőségek másolása és telepítése
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. lépés: Az alkalmazás kódjának másolása
COPY . .

# 6. lépés: Az adatbázis inicializálása
RUN python -c 'from app import db; db.create_all()'

# 7. lépés: A konténeren belüli port megadása
EXPOSE 5000

# 8. lépés: Az alkalmazás indítása Gunicornnal
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]