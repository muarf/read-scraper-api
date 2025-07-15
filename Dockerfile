# Utiliser l'image Python 3.9
FROM python:3.10

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Copier les fichiers nécessaires
COPY common /app/common
COPY server /app/server
COPY static /app/static
COPY web_scraper /app/web_scraper
COPY requirements.txt /app/
# Installer les dépendances
RUN pip install -r /app/requirements.txt

ENV PYTHONPATH "${PYTHONPATH}:/app/web_scraper"
# Définir la commande d'exécution
CMD ["python", "server/server.py"]
RUN apt-get update && apt-get install -y chromium-driver wkhtmltopdf
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
RUN apt install ./google-chrome-stable_current_amd64.deb -y
