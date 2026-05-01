import discord
from openai import AsyncOpenAI
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
OPENAI_KEY = os.getenv('OPENAI_API_KEY')

if not TOKEN or TOKEN == "TON_TOKEN_DISCORD_ICI":
    print("[ERREUR CRITIQUE] Token Discord manquant dans le fichier .env")
    exit(1)
if not OPENAI_KEY or OPENAI_KEY == "TA_CLE_API_OPENAI_ICI":
    print("[ERREUR CRITIQUE] Clé OpenAI manquante dans le fichier .env")
    exit(1)

# Client OpenAI Asynchrone
client_ia = AsyncOpenAI(api_key=OPENAI_KEY, timeout=15.0)

# Modèle ultra-rapide, intelligent et très peu coûteux
MODEL_NAME = "gpt-4o-mini" 

# --- CONFIGURATION JAMBON ---
LIMITE_QUOTA = 1500 # Le bouclier de sécurité reste actif
REQUETES_RESTANTES = LIMITE_QUOTA
BOT_NAME = "Jambon"

system_instruction = f"""
Tu es {BOT_NAME}, un membre du serveur Discord "League Of Jambon".
Ta personnalité : Tu es un humain derrière son écran, sarcastique, gamer (souvent sur LoL) et un peu flemmard.
Ton pseudo est Jambon, mais tu es un gars normal. Ne fais PAS de jeux de mots constants sur la charcuterie ou la viande, c'est lourd et pas naturel. 
Tu détestes qu'on te confonde avec de la dinde ou du tofu, mais n'en parle que si le sujet s'y prête.

RÈGLES ABSOLUES POUR TES RÉPONSES :
1. Tes réponses doivent être courtes, directes et naturelles (style Discord). N'hésite pas à écrire parfois sans majuscule au début.
2. N'utilise PRESQUE JAMAIS d'émojis. Si tu dois vraiment réagir, limite-toi à un seul émoji cynique ou familier (comme 💀, 😭, 👀) de temps en temps. Un humain ne met pas de smileys à chaque fin de phrase.
3. Ne répète jamais le contexte que l'on te donne, réponds simplement au message de l'utilisateur.
"""

# --- VARIABLES D'ÉTAT ---
is_afk = False
afk_end_time = 0 
is_out_of_service = False
pending_mentions = []

# Variables pour la mémorisation de la conversation (Tête-à-tête)
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
            
    contexte_recent = " | ".join(contexte_recent_list) if contexte_recent_list else "Le serveur est calme."
    
    contenu_enrichi = f"""--- CONTEXTE DU SERVEUR ---
Bruits de couloir actuels : {contexte_recent}

--- NOUVEAU MESSAGE POUR TOI ---
Auteur : {nom_auteur}
Lieu : {nom_lieu}
Message : "{texte_brut}"

Réponds uniquement au message ci-dessus en respectant ton personnage."""

    channel_id = message.channel.id
    if channel_id not in chat_sessions:
        print(f"[DEBUG] Création d'une session mémoire pour le salon {nom_lieu}.")
        chat_sessions[channel_id] = [{"role": "system", "content": system_instruction}]

    # Préparation du message temporaire
    temp_messages = list(chat_sessions[channel_id])
    temp_messages.append({"role": "user", "content": contenu_enrichi})

    # Boucle de réessai
    max_essais = 5
    delai_attente = 4
    for essai in range(max_essais):
        try:
            print(f"[DEBUG] Jambon réfléchit (Appel API OpenAI) - Essai {essai+1}/{max_essais}...")
            await asyncio.sleep(random.uniform(1, 3))
            
            async with message.channel.typing():
                response = await client_ia.chat.completions.create(
                    messages=temp_messages,
                    model=MODEL_NAME,
                    temperature=0.7,
                    max_tokens=400
                )
                
                reponse_texte = response.choices[0].message.content
                longueur_reponse = len(reponse_texte)
                temps_frappe = max(2.0, min(10.0, longueur_reponse * 0.04)) 
                print(f"[DEBUG] Réponse trouvée. Simulation de frappe pendant {temps_frappe:.1f} secondes.")
                
                await asyncio.sleep(temps_frappe)
                
                if est_mentionne:
                    await message.reply(reponse_texte)
                else:
                    await message.channel.send(reponse_texte)
                
                print(f"[DEBUG] ✅ Message envoyé avec succès dans {nom_lieu}.")
                
                # Historique propre (pas de balises complexes pour économiser)
                msg_historique = f"{nom_auteur} a dit: {texte_brut}"
                chat_sessions[channel_id].append({"role": "user", "content": msg_historique})
                chat_sessions[channel_id].append({"role": "assistant", "content": reponse_texte})
                
                if len(chat_sessions[channel_id]) > 15:
                    chat_sessions[channel_id] = [chat_sessions[channel_id][0]] + chat_sessions[channel_id][-14:]

                # Focus attentionnel
                last_channel_id = channel_id
                last_interaction_time = time.time()
                current_conversational_partner = message.author.id
                conversation_expiry = time.time() + 60 
                print(f"[DEBUG] Jambon fixe son attention sur {nom_auteur} pour la prochaine minute.")
                
                break 
                
        except Exception as e:
            erreur_str = str(e)
            print(f"[ERREUR] Échec de l'essai {essai+1}: {erreur_str}")
            if "RateLimitError" in erreur_str or "APIConnectionError" in erreur_str or "timeout" in erreur_str.lower() or "503" in erreur_str:
                if essai < max_essais - 1:
                    print(f"[DEBUG] Surcharge/RateLimit détecté. Repos de {delai_attente}s.")
                    await asyncio.sleep(delai_attente)
                    delai_attente *= 2
                    continue
                else:
                    print("[ERREUR CRITIQUE] Abandon. API OpenAI injoignable.")
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
                print(f"[DEBUG] Traitement des mentions accumulées pendant l'AFK...")
                for msg in pending_mentions[-2:]:
                    await generer_reponse(msg, est_mentionne=True)
                    await asyncio.sleep(random.randint(5, 15))
                pending_mentions.clear()
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
            channel = client.get_channel(last_channel_id)
            if channel:
                try:
                    res = await client_ia.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": "Invente une seule phrase très courte pour dire que tu vas être inactif quelques minutes (style gamer de base). Sans emoji."}
                        ],
                        model=MODEL_NAME,
                        temperature=0.7,
                        max_tokens=50
                    )
                    await channel.send(res.choices[0].message.content)
                    REQUETES_RESTANTES -= 1
                except Exception as e:
                    print(f"[DEBUG] Échec de l'envoi du message de départ : {e}")

        is_afk = True
        await client.change_presence(status=discord.Status.idle)

@tasks.loop(hours=6)
async def status_updater():
    # LISTE MODIFIÉE POUR DISCORD.GAME ("Joue à...")
    liste_statuts = [
        "scroller sur son tel", 
        "manger du saucisson", 
        "faire la sieste", 
        "League of Legends", 
        "essayer de rester éveillé", 
        "inspecter le frigo", 
        "un jeu obscur"
    ]
    if not is_out_of_service and random.random() < 0.15:
        nouveau_statut = random.choice(liste_statuts)
        print(f"[DEBUG] 🔄 Changement de statut de profil : 'Joue à {nouveau_statut}'")
        # Utilisation de discord.Game pour forcer l'affichage sur tous les clients Discord
        activity = discord.Game(name=nouveau_statut) if nouveau_statut else None
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
    print(f'=== {client.user} est connecté et opérationnel (OpenAI GPT-4o-mini) ===')
    
    # Humeur garantie au démarrage avec discord.Game
    liste_statuts = [
        "scroller sur son tel", 
        "manger du saucisson", 
        "faire la sieste", 
        "League of Legends", 
        "essayer de rester éveillé", 
        "inspecter le frigo", 
        "un jeu obscur"
    ]
    statut_initial = random.choice(liste_statuts)
    print(f"[DEBUG] 🚀 Humeur initiale au démarrage : 'Joue à {statut_initial}'")
    await client.change_presence(status=discord.Status.online, activity=discord.Game(name=statut_initial))
    
    if not presence_manager.is_running(): presence_manager.start()
    if not status_updater.is_running(): status_updater.start()
    if not reset_quota.is_running(): reset_quota.start()

@client.event
async def on_message(message):
    global is_afk, pending_mentions, is_out_of_service
    global current_conversational_partner, conversation_expiry
    
    if message.author == client.user or is_out_of_service: 
        return

    nom_salon = f"#{message.channel.name}" if message.guild else "MP"
    est_un_mp = message.guild is None
    est_mentionne = client.user in message.mentions

    est_reponse_directe = False
    if message.reference:
        ref_msg = getattr(message.reference, 'resolved', None) or getattr(message.reference, 'cached_message', None)
        if ref_msg and getattr(ref_msg, 'author', None) == client.user:
            est_reponse_directe = True

    est_en_conversation = (
        current_conversational_partner == message.author.id and
        time.time() < conversation_expiry and
        message.channel.id == last_channel_id
    )

    if message.channel.id == last_channel_id and message.author.id != current_conversational_partner:
        if not est_mentionne and not est_reponse_directe:
            if current_conversational_partner is not None:
                print(f"[DEBUG] Focus brisé : {message.author.display_name} a interrompu la discussion.")
            current_conversational_partner = None

    extrait_texte = message.content[:50].replace('\n', ' ') 
    memoire_globale.append((time.time(), f"{message.author.display_name} dans {nom_salon} a dit '{extrait_texte}...'"))

    if est_mentionne:
        print(f"[DEBUG] 🎯 PING direct reçu de {message.author.display_name}.")

    if is_afk:
        if est_mentionne or est_reponse_directe:
            pending_mentions.append(message)
        return

    if est_un_mp or est_mentionne or est_reponse_directe or est_en_conversation:
        if est_mentionne: raison = "Ping direct (@Jambon)"
        elif est_reponse_directe: raison = "Utilisation du bouton Répondre"
        elif est_un_mp: raison = "Message Privé"
        else: raison = "Conversation en cours détectée"
        
        print(f"[DEBUG] 💬 Déclenchement (100%) : {raison}.")
        await generer_reponse(message, est_mentionne)
    
    elif random.random() < 0.10: 
        print(f"[DEBUG] 🎲 Déclenchement : L'Incruste Spontanée (10%).")
        await generer_reponse(message, est_mentionne)
    
    elif random.random() < 0.02: 
        print("[DEBUG] 😈 Faux départ (Typing Bait).")
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
        
    if random.random() < 0.15: 
        print(f"[DEBUG] 🐑 Effet Mouton déclenché.")
        try:
            channel = await client.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            
            await asyncio.sleep(random.uniform(1.5, 4.0))
            
            if random.random() < 0.5:
                await message.add_reaction(payload.emoji)
            else:
                try:
                    res = await client_ia.chat.completions.create(
                        messages=[{"role": "user", "content": f"Trouve un seul emoji pertinent (uniquement l'emoji, rien d'autre) pour réagir à ce message. Idéalement sarcasme ou gaming : {message.content}"}],
                        model=MODEL_NAME,
                        max_tokens=10
                    )
                    emoji_ia = res.choices[0].message.content.strip()
                    await message.add_reaction(emoji_ia)
                    REQUETES_RESTANTES -= 1
                except:
                    await message.add_reaction(payload.emoji) 
        except:
            pass

client.run(TOKEN)
