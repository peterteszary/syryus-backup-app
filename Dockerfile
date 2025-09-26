# 1. lépés: Hivatalos Python alap-image használata
FROM python:3.9-bullseye

# 2. lépés: Minden szükséges rendszer-csomag telepítése egyetlen lépésben
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    lftp \
    mariadb-client \
    iputils-ping \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. lépés: Munkakönyvtár beállítása
WORKDIR /app

# 4. lépés: Python függőségek telepítése
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. lépés: Alkalmazás kódjának másolása
COPY . .

# Az adatbázis inicializáló sort INNEN KIVESSZÜK!
# RUN python -c 'from app import db; db.create_all()'

# 7. lépés: Port megadása
EXPOSE 5000

# 8. lépés: Alkalmazás indítása
# A CMD parancsot módosítjuk, hogy indításkor hozza létre az adatbázist
CMD ["sh", "-c", "python -c 'from app import db; db.create_all()' && gunicorn --bind 0.0.0.0:5000 app:app"]