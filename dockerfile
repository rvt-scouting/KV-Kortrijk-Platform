# We beginnen met een lichtgewicht Python versie
FROM python:3.12

# Zet de werkmap in de container
WORKDIR /app

# Installeer systeem tools die nodig zijn voor database connecties (psycopg2)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Kopieer eerst alleen de requirements (slimme caching)
COPY requirements.txt .

# Installeer de python libraries
RUN pip install --no-cache-dir -r requirements.txt

# Kopieer nu de rest van je app code naar de container
COPY . .

# Vertel Docker dat poort 8501 open moet (de streamlit poort)
EXPOSE 8501

# Het commando om de app te starten
CMD ["streamlit", "run", "home.py", "--server.port=8501", "--server.address=0.0.0.0"]
