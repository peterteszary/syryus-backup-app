# 1. lépés: Hivatalos Python alap-image használata
FROM python:3.9-bullseye

# 2. lépés: Csomaglisták frissítése. HA EZ A LÉPÉS ELBUKIK, AKKOR VAN HÁLÓZATI HIBA.
RUN apt-get update -y

# 3. lépés: A hálózati diagnosztikai eszközök telepítése
RUN apt-get install -y --no-install-recommends iputils-ping

# 4. lépés: Most már futtatjuk a tényleges hálózati tesztet
RUN ping -c 4 8.8.8.8

# 5. lépés: Az alkalmazáshoz szükséges csomagok telepítése
RUN apt-get install -y --no-install-recommends \
    lftp \
    mariadb-client \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# A fájl többi része változatlan...
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python -c 'from app import db; db.create_all()'
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]