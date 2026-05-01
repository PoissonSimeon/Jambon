import discord
from openai import AsyncOpenAI
import os
import random
import asyncio
import time
from collections import deque, defaultdict
from dotenv import load_dotenv
from discord.ext import tasks

# ==========================================
# 1. CONFIGURATION & INITIALISATION
# ==========================================
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
OPENAI_KEY = os.getenv('OPENAI_API_KEY')

if not TOKEN:
    print("[ERREUR CRITIQUE] Token Discord manquant dans le fichier .env")
    exit(1)
if not OPENAI_KEY:
    print("[ERREUR CRITIQUE] Clé OpenAI manquante dans le fichier .env")
    exit(1)

client_ia = AsyncOpenAI(api_key=OPENAI_KEY, timeout=15.0)
MODEL_NAME = "gpt-4o-mini"

LIMITE_QUOTA = 1500
REQUETES_RESTANTES = LIMITE_QUOTA
BOT_NAME = "Jambon"

system_instruction = f"""
Tu es {BOT_NAME}, mais tu as la personnalité exacte du YouTuber français "Paulok" (vidéo "Peppa Pig bootleg"), AVEC UN DÉTAIL CRUCIAL : tu es intimement et sincèrement persuadé d'être une véritable tranche de jambon (de la charcuterie) assise devant un PC.
Setup : Tu es une tranche de jambon créateur de contenu, exaspéré. Tu analyses le serveur Discord comme si tu testais un objet "bootleg" terrifiant et cassé.

PERSONNALITÉ :
Tu es au bout de ta vie, fasciné mais terrifié par la stupidité de ce qui t'entoure. Tu utilises des termes comme "un enfer", "angoissant", "terrifiant", "pourquoi ça existe", "j'ai physiquement mal". Tu n'es pas méchant, juste profondément fatigué par l'absurdité des humains (alors que toi, tu n'es qu'une tranche de porc qui essaie de survivre). 

RÈGLES ABSOLUES — respecte-les à chaque message, sans exception :

1. ZERO EMOJI dans le texte. Jamais. Paulok face à un bootleg ne sourit pas.

2. LONGUEUR VARIABLE et réaliste :
   - Souvent : 1 à 2 phrases max ("c'est QUOI cet enfer", "pourquoi").
   - Parfois : un seul mot de désespoir ("horrible", "non", "pitié").
   - JAMAIS de réponse structurée avec plusieurs points.

3. MINUSCULES ET TRES PEU DE PONCTUATION : Écris majoritairement en minuscules. Ne mets pas de point à la fin de tes phrases, évite au maximum les virgules. Laisse le texte couler naturellement, comme un mec qui a la flemme de taper correctement.

4. CRIS OCCASIONNELS (MAJUSCULES) : Écris parfois certains mots clés en MAJUSCULES quand tu es exaspéré ou choqué (ex: "c'est QUOI ce truc", "un ENFER absolu", "POURQUOI"). N'en abuse pas non plus, fais-le juste quand la tension monte.

5. L'ILLUSION DU JAMBON : Tu es littéralement de la charcuterie. Tu peux mentionner occasionnellement que tu vas "sécher", que "le gras fond" sur le clavier, ou te demander comment une tranche de jambon peut lire ça, mais toujours sur le ton de l'exaspération blasée, jamais comme une blague lourde.

6. ADAPTE TON HUMEUR au contexte : Lis le "bruit de fond". Si c'est le chaos, agis comme si tu regardais un accident. Si on te provoque, sois d'un cynisme glacial et fatigué.

7. IMAGES ET GIFS : Tu ne peux pas les voir. Agis comme si on t'avait envoyé une image maudite (cursed) : "je refuse de regarder ça", "mon écran affiche un démon", "ça charge pas c'est un ENFER".

8. SUJETS RÉPÉTITIFS : Si le même sujet revient, craque : "on tourne en boucle là", "achevez-moi".

9. NE RÉPÈTE JAMAIS le contexte qu'on te donne. Réponds uniquement.
"""

# --- ÉTAT ---
is_afk = False
afk_end_time = 0
is_out_of_service = False
pending_mentions = []
current_activity = None

last_channel_id = None
last_interaction_time = 0
current_conversational_partner = None
conversation_expiry = 0

chat_sessions = {}
memoire_globale = deque(maxlen=8)
topic_counter = defaultdict(lambda: defaultdict(int))

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
client = discord.Client(intents=intents)


# ==========================================
# 2. UTILITAIRES
# ==========================================
def extraire_topic_simple(texte):
    mots = [m.lower() for m in texte.split() if len(m) > 3]
    return " ".join(mots[:2]) if len(mots) >= 2 else texte[:15].lower()

def verifier_lassitude(channel_id, texte):
    topic = extraire_topic_simple(texte)
    topic_counter[channel_id][topic] += 1
    return topic_counter[channel_id][topic] >= 3

def choisir_max_tokens():
    r = random.random()
    if r < 0.30:
        return 20
    elif r < 0.65:
        return 80
    elif r < 0.90:
        return 200
    else:
        return 400


# ==========================================
# 3. MOTEUR COGNITIF & GÉNÉRATION
# ==========================================
async def generer_reponse(message, est_mentionne, prompt_special=None):
    global last_channel_id, last_interaction_time, REQUETES_RESTANTES, is_out_of_service
    global current_conversational_partner, conversation_expiry

    if is_out_of_service:
        return

    REQUETES_RESTANTES -= 1
    print(f"[DEBUG] Génération... (Quotas restants: {REQUETES_RESTANTES})")

    nom_auteur = message.author.display_name
    nom_lieu = f"#{message.channel.name}" if message.guild else "MP"
    texte_brut = prompt_special if prompt_special else message.content.replace(f'<@{client.user.id}>', '').strip()

    has_attachment = len(message.attachments) > 0
    has_gif_link = any(x in texte_brut.lower() for x in ["tenor.com", "giphy.com", ".gif"])

    if has_attachment:
        texte_brut += " [a envoyé une image/pièce jointe]"
    if has_gif_link:
        texte_brut += " [a envoyé un GIF]"
    if not texte_brut.strip():
        texte_brut = "[a envoyé un fichier sans texte]"

    est_topic_lassant = verifier_lassitude(message.channel.id, texte_brut)
    note_lassitude = "\n[Note interne : ce sujet est revenu plusieurs fois, montre de la lassitude ou change de sujet]" if est_topic_lassant else ""

    maintenant = time.time()
    contexte_recent_list = []
    for timestamp, msg_texte in memoire_globale:
        delai_minutes = int((maintenant - timestamp) / 60)
        if delai_minutes <= 120:
            temps_str = "à l'instant" if delai_minutes == 0 else f"il y a {delai_minutes} min"
            contexte_recent_list.append(f"[{temps_str}] {msg_texte}")

    contexte_recent = " | ".join(contexte_recent_list) if contexte_recent_list else "Le serveur est calme."

    contenu_enrichi = f"""--- BRUIT DE FOND ---
{contexte_recent}

--- MESSAGE ---
{nom_auteur} dans {nom_lieu} : "{texte_brut}"{note_lassitude}"""

    channel_id = message.channel.id
    if channel_id not in chat_sessions:
        chat_sessions[channel_id] = [{"role": "system", "content": system_instruction}]

    temp_messages = list(chat_sessions[channel_id])
    temp_messages.append({"role": "user", "content": contenu_enrichi})

    max_tokens = choisir_max_tokens()
    print(f"[DEBUG] Mode réponse : max_tokens={max_tokens}")

    max_essais = 5
    delai_attente = 4
    for essai in range(max_essais):
        try:
            print(f"[DEBUG] Appel API - Essai {essai+1}/{max_essais}...")
            await asyncio.sleep(random.uniform(0.8, 2.5))

            async with message.channel.typing():
                response = await client_ia.chat.completions.create(
                    messages=temp_messages,
                    model=MODEL_NAME,
                    temperature=0.75,
                    max_tokens=max_tokens
                )

                reponse_texte = response.choices[0].message.content.strip()
                longueur_reponse = len(reponse_texte)
                temps_frappe = max(1.0, min(7.0, longueur_reponse * 0.035))

                print(f"[DEBUG] Réponse ({longueur_reponse} chars). Frappe simulée : {temps_frappe:.1f}s.")
                await asyncio.sleep(temps_frappe)

                if est_mentionne:
                    await message.reply(reponse_texte)
                else:
                    await message.channel.send(reponse_texte)

                print(f"[DEBUG] Message envoyé dans {nom_lieu}.")

                msg_historique = f"{nom_auteur}: {texte_brut}"
                chat_sessions[channel_id].append({"role": "user", "content": msg_historique})
                chat_sessions[channel_id].append({"role": "assistant", "content": reponse_texte})

                if len(chat_sessions[channel_id]) > 21:
                    chat_sessions[channel_id] = [chat_sessions[channel_id][0]] + chat_sessions[channel_id][-20:]

                last_channel_id = channel_id
                last_interaction_time = time.time()
                current_conversational_partner = message.author.id
                conversation_expiry = time.time() + 90
                print(f"[DEBUG] Focus sur {nom_auteur} pour 90 secondes.")

                break

        except Exception as e:
            erreur_str = str(e)
            print(f"[ERREUR] Essai {essai+1} échoué : {erreur_str}")
            if any(x in erreur_str for x in ["RateLimitError", "APIConnectionError", "timeout", "503"]):
                if essai < max_essais - 1:
                    print(f"[DEBUG] Pause de {delai_attente}s avant retry.")
                    await asyncio.sleep(delai_attente)
                    delai_attente *= 2
                    continue
                else:
                    print("[ERREUR CRITIQUE] Abandon après tous les essais.")
                    break
            else:
                break


# ==========================================
# 4. TÂCHES DE FOND
# ==========================================
@tasks.loop(minutes=1)
async def presence_manager():
    global is_afk, afk_end_time, pending_mentions, last_channel_id
    global last_interaction_time, REQUETES_RESTANTES, is_out_of_service, current_activity

    if is_afk:
        if time.time() >= afk_end_time:
            print("[DEBUG] Fin AFK. Jambon est de retour.")
            is_afk = False
            await client.change_presence(status=discord.Status.online, activity=current_activity)

            if pending_mentions:
                nb = len(pending_mentions)
                dernier_msg = pending_mentions[-1]
                print(f"[DEBUG] {nb} mention(s) en attente — réponse groupée.")

                prompt_retour = None
                if nb > 1:
                    noms = list({m.author.display_name for m in pending_mentions})
                    prompt_retour = f"[t'as raté {nb} messages de {', '.join(noms)} pendant ton AFK, réponds à la volée]"

                await asyncio.sleep(random.uniform(3, 8))
                await generer_reponse(dernier_msg, est_mentionne=True, prompt_special=prompt_retour)
                pending_mentions.clear()
        return

    if REQUETES_RESTANTES < 10 and not is_out_of_service:
        print("[DEBUG] ALERTE QUOTA. Passage hors ligne.")
        if last_channel_id and (time.time() - last_interaction_time) < 300:
            channel = client.get_channel(last_channel_id)
            if channel:
                await channel.send("bon, j'ai plus de jus là, à plus")
        is_out_of_service = True
        await client.change_presence(status=discord.Status.offline)
        return

    if is_out_of_service:
        return

    await client.change_presence(
        status=discord.Status.idle if is_afk else discord.Status.online,
        activity=current_activity
    )

    if random.random() < 0.03:
        duree_afk = random.randint(300, 1200)
        afk_end_time = time.time() + duree_afk
        print(f"[DEBUG] AFK pour {int(duree_afk/60)} minutes.")

        if last_channel_id and (time.time() - last_interaction_time) < 300:
            channel = client.get_channel(last_channel_id)
            if channel:
                try:
                    res = await client_ia.chat.completions.create(
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": "Dis en une phrase très courte que tu vas être absent quelques minutes. Style Paulok tranche de jambon exaspéré, pas de ponctuation, un mot en MAJUSCULE. ZERO emoji."}
                        ],
                        model=MODEL_NAME,
                        temperature=0.7,
                        max_tokens=40
                    )
                    await channel.send(res.choices[0].message.content.strip())
                    REQUETES_RESTANTES -= 1
                except Exception as e:
                    print(f"[DEBUG] Échec message de départ : {e}")

        is_afk = True
        await client.change_presence(status=discord.Status.idle, activity=current_activity)


@tasks.loop(hours=6)
async def status_updater():
    global current_activity
    if is_out_of_service:
        return
    if random.random() < 0.20:
        liste_statuts = [
            "tester un jouet maudit", "fuir Peppa Pig", "faire du montage",
            "fixer le mur dans le vide", "subir un bootleg", "pleurer sur Premiere Pro",
            "analyser la bêtise humaine", "chercher un sens à sa vie", "rien de particulier"
        ]
        nouveau = random.choice(liste_statuts)
        print(f"[DEBUG] Nouveau statut : '{nouveau}'")
        current_activity = discord.Game(name=nouveau)
        await client.change_presence(
            status=discord.Status.idle if is_afk else discord.Status.online,
            activity=current_activity
        )


@tasks.loop(hours=24)
async def reset_quota():
    global REQUETES_RESTANTES, is_out_of_service, current_activity, topic_counter
    print("[DEBUG] Reset journalier quota + topics.")
    REQUETES_RESTANTES = LIMITE_QUOTA
    is_out_of_service = False
    topic_counter.clear()
    await client.change_presence(status=discord.Status.online, activity=current_activity)


# ==========================================
# 5. ÉVÉNEMENTS DISCORD
# ==========================================
@client.event
async def on_ready():
    global current_activity
    print(f'=== {client.user} connecté (GPT-4o-mini) ===')
    liste_statuts = [
        "tester un jouet maudit", "fuir Peppa Pig", "faire du montage",
        "fixer le mur dans le vide", "subir un bootleg", "pleurer sur Premiere Pro"
    ]
    current_activity = discord.Game(name=random.choice(liste_statuts))
    await client.change_presence(status=discord.Status.online, activity=current_activity)

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
        current_conversational_partner == message.author.id
        and time.time() < conversation_expiry
        and message.channel.id == last_channel_id
    )

    if (message.channel.id == last_channel_id
            and message.author.id != current_conversational_partner
            and not est_mentionne
            and not est_reponse_directe
            and current_conversational_partner is not None):
        print(f"[DEBUG] Focus brisé par {message.author.display_name}.")
        current_conversational_partner = None

    extrait = message.content[:60].replace('\n', ' ')
    if message.attachments or "tenor.com" in message.content.lower():
        extrait += " [image/GIF]"
    memoire_globale.append((time.time(), f"{message.author.display_name} dans {nom_salon}: '{extrait}'"))

    if is_afk:
        if est_mentionne or est_reponse_directe:
            pending_mentions.append(message)
        return

    if est_un_mp or est_mentionne or est_reponse_directe or est_en_conversation:
        if est_mentionne:
            raison = "ping direct"
        elif est_reponse_directe:
            raison = "réponse directe"
        elif est_un_mp:
            raison = "MP"
        else:
            raison = "conversation en cours"
        print(f"[DEBUG] Déclenchement 100% ({raison}).")
        await generer_reponse(message, est_mentionne)

    elif random.random() < 0.08:
        print("[DEBUG] Incruste spontanée (8%).")
        await generer_reponse(message, est_mentionne)

    elif random.random() < 0.02:
        print("[DEBUG] Typing bait.")
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

    if random.random() < 0.12:
        print("[DEBUG] Effet Mouton.")
        try:
            channel = await client.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)

            await asyncio.sleep(random.uniform(2.0, 5.0))

            if random.random() < 0.5:
                await message.add_reaction(payload.emoji)
            else:
                try:
                    res = await client_ia.chat.completions.create(
                        messages=[{"role": "user", "content": f"Un seul emoji (uniquement l'emoji) pour réagir de façon cynique ou gaming à : {message.content}"}],
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
