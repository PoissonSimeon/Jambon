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
    print("[ERREUR CRITIQUE] Token Discord manquant dans le fichier .env")
    exit(1)
if not GEMINI_KEY or GEMINI_KEY == "TA_CLE_API_GEMINI_ICI":
    print("[ERREUR CRITIQUE] Clé Gemini manquante dans le fichier .env")
    exit(1)

client_gemini = genai.Client(api_key=GEMINI_KEY)
MODEL_NAME = "gemini-2.5-flash"

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
afk_end_time = 0 
is_out_of_service = False
pending_mentions = []

# NOUVEAU : Variables pour la mémorisation de la conversation (Tête-à-tête)
last_channel_id = None
last_interaction_time = 0
current_conversational_partner = None 
conversation_expiry = 0

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
    global current_conversational_partner, conversation_expiry
    
    if is_out_of_service: 
        print("[DEBUG] Requête ignorée : Jambon est hors service (Quota).")
        return

    REQUETES_RESTANTES -= 1
    print(f"[DEBUG] Génération de réponse... (Quotas restants: {REQUETES_RESTANTES})")
    
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
        print(f"[DEBUG] Création d'une nouvelle session mémoire pour le salon {nom_lieu}.")
        chat_sessions[channel_id] = client_gemini.aio.chats.create(model=MODEL_NAME, config=config_gemini)

    max_essais = 3
    delai_attente = 2
    for essai in range(max_essais):
        try:
            print(f"[DEBUG] Jambon réfléchit (Appel API Google) - Essai {essai+1}/{max_essais}...")
            await asyncio.sleep(random.uniform(1, 3))
            
            async with message.channel.typing():
                print(f"[DEBUG] Statut 'Jambon écrit...' activé sur Discord.")
                response = await chat_sessions[channel_id].send_message(contenu_enrichi)
                
                longueur_reponse = len(response.text)
                temps_frappe = max(2.0, min(10.0, longueur_reponse * 0.04)) 
                print(f"[DEBUG] Réponse trouvée ({longueur_reponse} caractères). Simulation de frappe pendant {temps_frappe:.1f} secondes.")
                
                await asyncio.sleep(temps_frappe)
                
                if est_mentionne:
                    await message.reply(response.text)
                else:
                    await message.channel.send(response.text)
                
                print(f"[DEBUG] ✅ Message envoyé avec succès dans {nom_lieu}.")
                
                # Mise à jour de l'attention (Jambon se focalise sur cette personne)
                last_channel_id = channel_id
                last_interaction_time = time.time()
                current_conversational_partner = message.author.id
                conversation_expiry = time.time() + 60 # Jambon reste concentré sur lui pendant 60 secondes
                print(f"[DEBUG] Jambon fixe son attention sur {nom_auteur} pour la prochaine minute.")
                
                break 
                
        except Exception as e:
            erreur_str = str(e)
            print(f"[ERREUR] Échec de l'essai {essai+1}: {erreur_str}")
            if "503" in erreur_str or "UNAVAILABLE" in erreur_str or "429" in erreur_str:
                if essai < max_essais - 1:
                    print(f"[DEBUG] Surcharge détectée. Repos de {delai_attente}s avant le prochain essai.")
                    await asyncio.sleep(delai_attente)
                    delai_attente *= 2
                    continue
                else:
                    print("[ERREUR CRITIQUE] Abandon. API Google injoignable après 3 essais.")
                    break
            else:
                break

# ==========================================
# 3. TÂCHES DE FOND (COMPORTEMENT HUMAIN)
# ==========================================
@tasks.loop(minutes=1)
async def presence_manager():
    global is_afk, afk_end_time, pending_mentions, last_channel_id, last_interaction_time, REQUETES_RESTANTES, is_out_of_service
    
    if is_afk:
        if time.time() >= afk_end_time:
            print("[DEBUG] ⏰ Fin de l'AFK. Jambon est de retour !")
            is_afk = False
            await client.change_presence(status=discord.Status.online)
            
            if pending_mentions:
                print(f"[DEBUG] Traitement des {len(pending_mentions)} mentions accumulées pendant l'AFK...")
                for msg in pending_mentions[-2:]:
                    await generer_reponse(msg, est_mentionne=True)
                    await asyncio.sleep(random.randint(5, 15))
                pending_mentions.clear()
        else:
            minutes_restantes = int((afk_end_time - time.time()) / 60)
            print(f"[DEBUG] Jambon est AFK (Retour prévu dans ~{minutes_restantes} min).")
        return 

    if REQUETES_RESTANTES < 10 and not is_out_of_service:
        print("[DEBUG] ⚠️ ALERTE QUOTA : Jambon se met hors ligne pour sécurité.")
        if last_channel_id and (time.time() - last_interaction_time) < 300:
            channel = client.get_channel(last_channel_id)
            if channel:
                await channel.send("Bon, j'ai plus de jus là, je vais me faire fumer au frais. À plus les couennes.")
        
        is_out_of_service = True
        await client.change_presence(status=discord.Status.offline)
        return

    if is_out_of_service: return

    if random.random() < 0.15:
        duree_afk = random.randint(300, 1200)
        afk_end_time = time.time() + duree_afk
        print(f"[DEBUG] 💤 Décision de passer AFK pour {int(duree_afk/60)} minutes.")
        
        if last_channel_id and (time.time() - last_interaction_time) < 300:
            print(f"[DEBUG] Jambon génère un message de départ car il discutait récemment...")
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
                except Exception as e:
                    print(f"[DEBUG] Échec de l'envoi du message de départ : {e}")

        is_afk = True
        await client.change_presence(status=discord.Status.idle)

@tasks.loop(hours=6)
async def status_updater():
    liste_statuts = ["Sur mon tel", "En train de manger", "Dodo la", "Sur LoL (a l'aide)", "Fatigué", "Check le frigo", "Gaming", ""]
    if not is_out_of_service and random.random() < 0.15:
        nouveau_statut = random.choice(liste_statuts)
        print(f"[DEBUG] 🔄 Changement de statut de profil : '{nouveau_statut}'")
        activity = discord.CustomActivity(name=nouveau_statut) if nouveau_statut else None
        current_status = discord.Status.idle if is_afk else discord.Status.online
        await client.change_presence(status=current_status, activity=activity)

@tasks.loop(hours=24)
async def reset_quota():
    global REQUETES_RESTANTES, is_out_of_service
    print("[DEBUG] 📅 Réinitialisation journalière du quota (1500 requêtes).")
    REQUETES_RESTANTES = LIMITE_QUOTA
    is_out_of_service = False
    await client.change_presence(status=discord.Status.online)

# ==========================================
# 4. ÉVÉNEMENTS DISCORD
# ==========================================
@client.event
async def on_ready():
    print(f'=== {client.user} est connecté et opérationnel (Gemini 2.5 Flash) ===')
    if not presence_manager.is_running(): presence_manager.start()
    if not status_updater.is_running(): status_updater.start()
    if not reset_quota.is_running(): reset_quota.start()

@client.event
async def on_message(message):
    global is_afk, pending_mentions, is_out_of_service
    global current_conversational_partner, conversation_expiry
    
    if message.author == client.user: 
        return
    
    if is_out_of_service: 
        return

    nom_salon = f"#{message.channel.name}" if message.guild else "MP"
    est_un_mp = message.guild is None
    est_mentionne = client.user in message.mentions

    # 1. Vérifier si c'est une fonctionnalité "Réponse" directe à un message de Jambon (même sans ping)
    est_reponse_directe = False
    if message.reference:
        ref_msg = getattr(message.reference, 'resolved', None) or getattr(message.reference, 'cached_message', None)
        if ref_msg and getattr(ref_msg, 'author', None) == client.user:
            est_reponse_directe = True

    # 2. Vérifier si le joueur est en pleine discussion fluide avec Jambon (tête-à-tête)
    est_en_conversation = (
        current_conversational_partner == message.author.id and
        time.time() < conversation_expiry and
        message.channel.id == last_channel_id
    )

    # 3. L'humain se laisse distraire : on casse le focus de conversation si un autre joueur parle au milieu !
    if message.channel.id == last_channel_id and message.author.id != current_conversational_partner:
        if not est_mentionne and not est_reponse_directe:
            if current_conversational_partner is not None:
                print(f"[DEBUG] Focus brisé : {message.author.display_name} a interrompu la discussion.")
            current_conversational_partner = None

    # Mémorisation globale
    extrait_texte = message.content[:50].replace('\n', ' ') 
    memoire_globale.append((time.time(), f"{message.author.display_name} dans {nom_salon} a dit '{extrait_texte}...'"))

    if est_mentionne:
        print(f"[DEBUG] 🎯 PING direct reçu de {message.author.display_name} dans {nom_salon}.")

    # Gestion de l'AFK 
    if is_afk:
        if est_mentionne or est_reponse_directe:
            print(f"[DEBUG] Jambon est AFK. Message de {message.author.display_name} mis en file d'attente.")
            pending_mentions.append(message)
        else:
            print(f"[DEBUG] Message ignoré car Jambon est AFK.")
        return

    # Matrice de Décision
    if est_un_mp or est_mentionne or est_reponse_directe or est_en_conversation:
        raison = "MP/Ping"
        if est_reponse_directe: raison = "Utilisation du bouton Répondre"
        elif est_en_conversation: raison = "Conversation en cours détectée"
        
        print(f"[DEBUG] 💬 Déclenchement (100%) : {raison}.")
        await generer_reponse(message, est_mentionne)
    
    elif random.random() < 0.10: # 10% L'Incruste
        print(f"[DEBUG] 🎲 Déclenchement : L'Incruste Spontanée (10% de chance atteinte).")
        await generer_reponse(message, est_mentionne)
    
    elif random.random() < 0.02: # 2% Faux Départ
        print("[DEBUG] 😈 Déclenchement : Faux départ (Typing Bait).")
        try:
            async with message.channel.typing():
                await asyncio.sleep(random.uniform(2, 4))
            print("[DEBUG] Faux départ terminé. Rien n'a été envoyé.")
        except:
            pass
    else:
        # Message classique ignoré
        pass

@client.event
async def on_raw_reaction_add(payload):
    global REQUETES_RESTANTES
    if is_out_of_service or is_afk or payload.user_id == client.user.id:
        return
        
    if random.random() < 0.15: # 15% Effet Mouton
        print(f"[DEBUG] 🐑 Effet Mouton déclenché sur un message.")
        try:
            channel = await client.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            
            await asyncio.sleep(random.uniform(1.5, 4.0))
            
            if random.random() < 0.5:
                print(f"[DEBUG] Mimétisme : Jambon copie l'émoji exact ({payload.emoji}).")
                await message.add_reaction(payload.emoji)
            else:
                print(f"[DEBUG] Mimétisme IA : Jambon réfléchit à un émoji adapté...")
                try:
                    res = await client_gemini.aio.models.generate_content(
                        model=MODEL_NAME,
                        contents=f"Trouve un seul emoji pertinent (uniquement l'emoji, rien d'autre) pour réagir à ce message. Idéalement sarcasme, gaming, charcuterie : {message.content}"
                    )
                    emoji_ia = res.text.strip()
                    print(f"[DEBUG] Mimétisme IA réussi : Émoji trouvé '{emoji_ia}'.")
                    await message.add_reaction(emoji_ia)
                    REQUETES_RESTANTES -= 1
                except Exception as e:
                    print(f"[DEBUG] Mimétisme IA échoué ({e}). Fallback sur la copie de l'émoji.")
                    await message.add_reaction(payload.emoji) 
        except Exception as e:
            print(f"[DEBUG] Erreur globale de l'Effet Mouton : {e}")

client.run(TOKEN)
