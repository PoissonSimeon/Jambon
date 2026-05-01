#!/bin/bash

# Script de démarrage et d'installation automatique pour le Bot Jambon
# Conçu pour Debian 12 (Proxmox LXC) - Version OpenAI (ChatGPT)

echo "🍖 Démarrage du script d'initialisation de Jambon..."

SUDO=""
if [ "$EUID" -ne 0 ]; then
    SUDO="sudo"
fi

echo "Vérification de Python et venv..."
if ! command -v python3 &> /dev/null || ! command -v pip &> /dev/null || ! dpkg -l | grep -q python3-venv; then
    echo "Installation des dépendances système nécessaires..."
    $SUDO apt update
    $SUDO apt install python3 python3-venv python3-pip -y
fi

if [ ! -d "venv" ]; then
    echo "Création de l'environnement virtuel Python..."
    python3 -m venv venv
fi

echo "Vérification et installation des paquets Python (discord.py, openai)..."
venv/bin/pip install --upgrade pip
venv/bin/pip install discord.py openai python-dotenv

if [ ! -f ".env" ]; then
    echo ""
    echo "⚠️  ATTENTION : Le fichier .env n'existe pas."
    echo "Je viens de créer un modèle pour toi. Modifie-le avec tes clés API, puis relance ce script."
    echo ""
    echo "DISCORD_TOKEN=\"TON_TOKEN_DISCORD_ICI\"" > .env
    echo "OPENAI_API_KEY=\"TA_CLE_API_OPENAI_ICI\"" >> .env
    exit 1
fi

echo "🚀 Lancement de Jambon..."
venv/bin/python bot.py
