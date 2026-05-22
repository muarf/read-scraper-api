# Utiliser l'image Python 3.10 avec Debian 12 (Bookworm) où wkhtmltopdf est disponible
FROM python:3.10-bookworm

# Installer les dépendances système AVANT de copier les fichiers
RUN apt-get update && \
    apt-get install -y chromium-driver && \
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt install ./google-chrome-stable_current_amd64.deb -y && \
    rm google-chrome-stable_current_amd64.deb && \
    apt-get clean

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Copier les fichiers nécessaires
COPY backend /app/backend
COPY common /app/common
COPY frontend /app/frontend
COPY admin /app/admin
COPY web_scraper /app/web_scraper
COPY static /app/static
COPY .env* /app/
COPY requirements.txt /app/

# Installer les dépendances Python
RUN pip install -r /app/requirements.txt

ENV PYTHONPATH "${PYTHONPATH}:/app/web_scraper"

# Définir la commande d'exécution
CMD ["python", "-m", "backend.main"]
