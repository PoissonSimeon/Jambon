import discord
from google import genai
from google.genai import types
import os
import random
import asyncio
import time
from collections import deque
from dotenv import load_dotenv
from discord.ext import tasks

# ==========================================
# 1. CONFIGURATION & INITIALISATION
# ==========================================
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

if not TOKEN or TOKEN == "TON_TOKEN_DISCORD_ICI":
    print("ERREUR CRITIQUE: Token Discord manquant dans le fichier .env")
    exit(1)
if not GEMINI_KEY or GEMINI_KEY == "TA_CLE_API_GEMINI_ICI":
    print("ERREUR CRITIQUE: Clé Gemini manquante dans le fichier .env")
    exit(1)

# Client Gemini (Nouvelle API, utilisation de .aio plus bas pour l'asynchrone)
client_gemini = genai.Client(api_key=GEMINI_KEY)
MODEL_NAME = "gemini-1.5-flash" # Strict respect du cahier des charges

# --- CONFIGURATION JAMBON ---
LIMITE_QUOTA = 1500 
REQUETES_RESTANTES = LIMITE_QUOTA
BOT_NAME = "Jambon"

system_instruction = f"""
Tu es {BOT_NAME}, un membre incontournable du serveur "League Of Jambon".
Ta personnalité : Tu es un peu gras, fier de ton appellation, très porté sur le second degré.
Ton univers tourne autour de la charcuterie : tu utilises des expressions comme "ça me fend le gras", 
"je suis fumé", "tu me prends pour une couenne ?".
Tu es un humain derrière son écran, sarcastique et un peu flemmard. 
Tu détestes qu'on te confonde avec de la dinde ou du tofu.

IMPORTANT - FORMAT DES MESSAGES :
Tu vas recevoir les messages sous ce format : [Bruit de fond : <Contexte>] [Lieu : <Salon/MP> | Auteur : <Joueur>] <Message>.
- Le Bruit de fond t'aide à savoir ce qui se dit dans les autres salons pour rebondir dessus si tu le souhaites.
- Le Lieu/Auteur t'indique à qui tu parles directement.
- NE RÉPÈTE JAMAIS le bloc entre crochets dans tes réponses. Agis naturellement.
"""

config_gemini = types.GenerateContentConfig(
    system_instruction=system_instruction,
    temperature=0.7
)

# --- VARIABLES D'ÉTAT ---
is_afk = False
is_out_of_service = False
pending_mentions = []
last_channel_id = None
last_interaction_time = 0

chat_sessions = {}
memoire_globale = deque(maxlen=4) 

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True 
client = discord.Client(intents=intents)

# ==========================================
# 2. MOTEUR COGNITIF & GÉNÉRATION
# ==========================================
async def generer_reponse(message, est_mentionne, prompt_special=None):
    global last_channel_id, last_interaction_time, REQUETES_RESTANTES, is_out_of_service
    
    if is_out_of_service: return

    REQUETES_RESTANTES -= 1
    
    nom_auteur = message.author.display_name
    nom_lieu = f"#{message.channel.name}" if message.guild else "MP"
    texte_brut = prompt_special if prompt_special else message.content.replace(f'<@{client.user.id}>', '').strip()
    
    contexte_recent_list = []
    maintenant = time.time()
    for timestamp, msg_texte in memoire_globale:
        delai_minutes = int((maintenant - timestamp) / 60)
        if delai_minutes <= 120: 
            temps_str = "à l'instant" if delai_minutes == 0 else f"il y a {delai_minutes} min"
            contexte_recent_list.append(f"[{temps_str}] {msg_texte}")
            
    contexte_recent = " | ".join(contexte_recent_list) if contexte_recent_list else "Le serveur est calme depuis un moment."
    
    contenu_enrichi = f"[Bruit de fond : {contexte_recent}] [Lieu actuel : {nom_lieu} | Auteur : {nom_auteur}] {texte_brut}"

    channel_id = message.channel.id
    if channel_id not in chat_sessions:
        # Création de session isolée par salon
        chat_sessions[channel_id] = client_gemini.aio.chats.create(model=MODEL_NAME, config=config_gemini)

    # Boucle de réessai (Exponential Backoff pour absorber les petites erreurs 503 de l'API gratuite)
    max_essais = 3
    delai_attente = 2
    for essai in range(max_essais):
        try:
            # Délai de réflexion humain
            await asyncio.sleep(random.uniform(1, 3))
            
            async with message.channel.typing():
                response = await chat_sessions[channel_id].send_message(contenu_enrichi)
                
                # Illusion de frappe proportionnelle (0.04s par caractère)
                longueur_reponse = len(response.text)
                temps_frappe = max(2.0, min(10.0, longueur_reponse * 0.04)) 
                await asyncio.sleep(temps_frappe)
                
                if est_mentionne:
                    await message.reply(response.text)
                else:
                    await message.channel.send(response.text)
                
                last_channel_id = channel_id
                last_interaction_time = time.time()
                break # Succès, on sort de la boucle
                
        except Exception as e:
            erreur_str = str(e)
            print(f"[ERREUR] Essai {essai+1} échoué : {erreur_str}")
            if "503" in erreur_str or "UNAVAILABLE" in erreur_str or "429" in erreur_str:
                if essai < max_essais - 1:
                    await asyncio.sleep(delai_attente)
                    delai_attente *= 2
                    continue
                else:
                    break
            else:
                break

# ==========================================
# 3. TÂCHES DE FOND (COMPORTEMENT HUMAIN)
# ==========================================
@tasks.loop(minutes=1)
async def presence_manager():
    global is_afk, pending_mentions, last_channel_id, last_interaction_time, REQUETES_RESTANTES, is_out_of_service
    
    # Sécurité Quota
    if REQUETES_RESTANTES < 10 and not is_out_of_service:
        if not is_afk and last_channel_id and (time.time() - last_interaction_time) < 300:
            channel = client.get_channel(last_channel_id)
            if channel:
                await channel.send("Bon, j'ai plus de jus là, je vais me faire fumer au frais. À plus les couennes.")
        
        is_out_of_service = True
        await client.change_presence(status=discord.Status.offline)
        print("Quota épuisé. Bot hors ligne.")
        return

    if is_out_of_service: return

    # Passage AFK (15% de chance)
    if not is_afk and random.random() < 0.15:
        if last_channel_id and (time.time() - last_interaction_time) < 300:
            channel = client.get_channel(last_channel_id)
            if channel:
                try:
                    res = await client_gemini.aio.models.generate_content(
                        model=MODEL_NAME,
                        contents="Dis que tu t'absentes vite fait (style Jambon gamer).",
                        config=config_gemini
                    )
                    await channel.send(res.text)
                    REQUETES_RESTANTES -= 1
                except:
                    pass

        is_afk = True
        await client.change_presence(status=discord.Status.idle)
        
        # Durée de l'absence
        await asyncio.sleep(random.randint(300, 1200))
        
        is_afk = False
        await client.change_presence(status=discord.Status.online)
        
        # Dépilage des notifications
        if pending_mentions:
            for msg in pending_mentions[-2:]:
                await generer_reponse(msg, est_mentionne=True)
                await asyncio.sleep(random.randint(5, 15))
            pending_mentions = []

@tasks.loop(hours=6)
async def status_updater():
    liste_statuts = ["Sur mon tel", "En train de manger", "Dodo la", "Sur LoL (a l'aide)", "Fatigué", "Check le frigo", "Gaming", ""]
    if not is_out_of_service and random.random() < 0.15:
        nouveau_statut = random.choice(liste_statuts)
        activity = discord.CustomActivity(name=nouveau_statut) if nouveau_statut else None
        current_status = discord.Status.idle if is_afk else discord.Status.online
        await client.change_presence(status=current_status, activity=activity)

@tasks.loop(hours=24)
async def reset_quota():
    global REQUETES_RESTANTES, is_out_of_service
    REQUETES_RESTANTES = LIMITE_QUOTA
    is_out_of_service = False
    await client.change_presence(status=discord.Status.online)
    print("Quota journalier réinitialisé.")

# ==========================================
# 4. ÉVÉNEMENTS DISCORD
# ==========================================
@client.event
async def on_ready():
    print(f'=== {client.user} est connecté et opérationnel (Gemini 1.5 Flash) ===')
    if not presence_manager.is_running(): presence_manager.start()
    if not status_updater.is_running(): status_updater.start()
    if not reset_quota.is_running(): reset_quota.start()

@client.event
async def on_message(message):
    global is_afk, pending_mentions, is_out_of_service
    # 4.1 Matrice de Décision : Message de lui-même -> Ignoré
    if message.author == client.user or is_out_of_service: return

    # Remplissage espionnage global
    nom_salon = f"#{message.channel.name}" if message.guild else "MP"
    extrait_texte = message.content[:50].replace('\n', ' ') 
    memoire_globale.append((time.time(), f"{message.author.display_name} dans {nom_salon} a dit '{extrait_texte}...'"))

    est_mentionne = client.user in message.mentions
    # 4.1 Matrice de Décision : Message Privé
    est_un_mp = message.guild is None

    # Gestion de l'AFK
    if is_afk:
        if est_mentionne: pending_mentions.append(message)
        return

    # 4.1 Matrice de Décision : DM ou Mention (100%) ou Incruste (10%)
    if est_un_mp or est_mentionne or (random.random() < 0.10):
        await generer_reponse(message, est_mentionne)
    
    # 4.3 Le Faux Départ (Typing Bait)
    elif random.random() < 0.02:
        try:
            async with message.channel.typing():
                await asyncio.sleep(random.uniform(2, 4))
        except:
            pass

@client.event
async def on_raw_reaction_add(payload):
    global REQUETES_RESTANTES
    if is_out_of_service or is_afk or payload.user_id == client.user.id:
        return
        
    # 4.4 L'Effet Mouton (Reaction Mirroring) : 15% de chance
    if random.random() < 0.15:
        try:
            channel = await client.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            
            await asyncio.sleep(random.uniform(1.5, 4.0))
            
            # Soit il copie (50%), soit il génère un emoji via l'IA (50%)
            if random.random() < 0.5:
                await message.add_reaction(payload.emoji)
            else:
                try:
                    res = await client_gemini.aio.models.generate_content(
                        model=MODEL_NAME,
                        contents=f"Trouve un seul emoji pertinent (uniquement l'emoji, rien d'autre) pour réagir à ce message. Idéalement sarcasme, gaming, charcuterie : {message.content}"
                    )
                    emoji_ia = res.text.strip()
                    await message.add_reaction(emoji_ia)
                    REQUETES_RESTANTES -= 1
                except:
                    await message.add_reaction(payload.emoji) # Fallback si IA fail
        except:
            pass

client.run(TOKEN)
