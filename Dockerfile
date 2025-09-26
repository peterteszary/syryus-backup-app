# 1. lépés: Hivatalos Python alap-image használata
FROM python:3.9-bullseye

# 2. lépés: HÁLÓZATI DIAGNOSZTIKA
# Teszteljük a nyers internet kapcsolatot (IP cím alapján)
RUN ping -c 4 8.8.8.8

# Teszteljük a DNS feloldást (domain név alapján)
RUN ping -c 4 google.com

# 3. lépés: Rendszer szintű függőségek telepítése
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
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