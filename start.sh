#!/bin/bash

# Commande pour démarrer le serveur FastAPI (main:app) avec Uvicorn
# Elle utilise la variable d'environnement $PORT fournie par Render
uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1