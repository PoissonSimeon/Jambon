#!/bin/bash

# Script de démarrage et d'installation automatique pour le Bot Jambon
# Conçu pour Debian 12 (Proxmox LXC)

echo "🍖 Démarrage du script d'initialisation de Jambon..."

# 1. Vérification des dépendances système
echo "Vérification de Python et venv..."
if ! command -v python3 &> /dev/null || ! command -v pip &> /dev/null || ! dpkg -l | grep -q python3-venv; then
    echo "Installation des dépendances système nécessaires..."
    sudo apt update
    sudo apt install python3 python3-venv python3-pip -y
fi

# 2. Configuration de l'environnement virtuel (venv)
if [ ! -d "venv" ]; then
    echo "Création de l'environnement virtuel Python..."
    python3 -m venv venv
fi

# Activation
source venv/bin/activate

# 3. Installation des dépendances Python
echo "Vérification des paquets Python..."
pip install --upgrade pip > /dev/null
pip install discord.py google-generativeai python-dotenv > /dev/null

# 4. Vérification du fichier .env
if [ ! -f ".env" ]; then
    echo ""
    echo "⚠️  ATTENTION : Le fichier .env n'existe pas."
    echo "Je viens de créer un modèle pour toi. Modifie-le avec tes clés API, puis relance ce script."
    echo ""
    echo "DISCORD_TOKEN=\"TON_TOKEN_DISCORD_ICI\"" > .env
    echo "GEMINI_API_KEY=\"TA_CLE_API_GEMINI_ICI\"" >> .env
    exit 1
fi

# 5. Lancement du bot
echo "🚀 Lancement de Jambon..."
python3 bot.py
