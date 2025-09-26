# 1. lépés: Alap-image
FROM python:3.9-bullseye

# 2. lépés: Rendszer-csomagok telepítése
RUN apt-get update -y && \
    apt-get install -y --no-install-recommends \
    lftp \
    mariadb-client \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 3. lépés: Munkakönyvtár
WORKDIR /app

# 4. lépés: Python függőségek
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. lépés: Alkalmazás kódjának másolása
# Most már az új szkripteket is bemásoljuk
COPY . .

# 6. lépés: Az entrypoint szkript futtathatóvá tétele
RUN chmod +x entrypoint.sh

# 7. lépés: Port megadása
EXPOSE 5000

# 8. lépés: Az entrypoint szkript beállítása a konténer fő indítóparancsaként
ENTRYPOINT ["./entrypoint.sh"]