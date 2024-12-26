import discord
import json
import time
import random
import string
import httpx
from discord.ext import commands, tasks

# Inicjalizacja bota
bot = discord.Bot(intents=discord.Intents.all())

# Wczytanie ustawień z pliku settings.json
with open("settings.json", "r", encoding="utf-8") as f:
    settings = json.load(f)

# Przykład prefiksu karty Nitro
cardstart = "485953"

def getRandomString(length):
    """Generuje losowy ciąg znaków (litery i cyfry)"""
    pool = string.ascii_lowercase + string.digits
    return "".join(random.choice(pool) for i in range(length))

def getRandomNumber(length):
    """Generuje losowy ciąg cyfr"""
    return "".join(random.choice(string.digits) for i in range(length))

def isAdmin(ctx):
    """Sprawdza, czy użytkownik jest administratorem bota"""
    return str(ctx.author.id) in settings["botAdminId"]

def isWhitelisted(ctx):
    """Sprawdza, czy użytkownik jest na białej liście"""
    return str(ctx.author.id) in settings["botWhitelistedId"]

# Funkcja do dodawania tokenów do pliku "used.json" po ich użyciu
def makeUsed(token):
    """Dodaje token do pliku 'used.json' po wykonaniu operacji"""
    data = json.load(open('used.json', 'r'))
    if token in data:
        return  # Jeśli token już jest używany, nic nie rób
    data[token] = {
        "boostedAt": str(time.time()),
        "boostFinishAt": str(time.time() + 30 * 86400)  # Ważny przez 30 dni
    }
    json.dump(data, open('used.json', 'w'), indent=4)

# Funkcja do usuwania tokenu z listy
def removeToken(token):
    """Usuwa token z pliku 'tokens.txt'"""
    with open('tokens.txt', "r") as f:
        tokens = f.read().splitlines()
        tokens = [t for t in tokens if t != token]  # Usuwanie tokenu
    with open('tokens.txt', "w") as f:
        f.write("\n".join(tokens))

# Funkcja do uruchamiania procesu boostowania
def runBoost(invite, amount, expires):
    """Główna funkcja do boostowania serwera za pomocą tokenów"""
    if amount % 2 != 0:
        amount += 1  # Jeśli ilość boostów jest nieparzysta, zwiększ do parzystej

    tokens = get_all_tokens("tokens.txt")
    boosts_done = 0
    for token in tokens:
        s, headers = get_headers(token)
        profile = validate_token(s, headers)
        if not profile:
            continue

        boost_data = s.get(f"https://discord.com/api/v9/users/@me/guilds/premium/subscription-slots", headers=headers)
        if boost_data.status_code == 200:
            if len(boost_data.json()) > 0:
                join_outcome, server_id = do_join_server(s, token, headers, profile, invite)
                if join_outcome:
                    for boost in boost_data.json():
                        if boosts_done >= amount:
                            removeToken(token)
                            if expires:
                                makeUsed(token)
                            return

                        boost_id = boost["id"]
                        boosted = do_boost(s, token, headers, profile, server_id, boost_id)
                        if boosted:
                            boosts_done += 1
                        else:
                            print(f"Error boosting with token {token}")
                    removeToken(token)
                    if expires:
                        makeUsed(token)
                else:
                    print(f"Error joining server with token {token}")

        else:
            removeToken(token)
            print(f"Token {token} does not have Nitro")

@tasks.loop(seconds=5.0)
async def check_used():
    """Sprawdzanie, które tokeny już wygasły i ich usuwanie"""
    used = json.load(open("used.json"))
    toremove = [token for token in used if str(time.time()) >= used[token]["boostFinishAt"]]

    for token in toremove:
        used.pop(token)
        with open("tokens.txt", "a", encoding="utf-8") as file:
            file.write(f"{token}\n")
        print(f"Token {token} was expired and moved back to stock.")

    json.dump(used, open("used.json", "w"), indent=4)

@bot.slash_command(guild_ids=[settings["guildID"]], name="boost", description="Boost the server with Nitro tokens")
async def boost(ctx, invitecode, amount: int, days: int):
    """Komenda do boostowania serwera"""
    if not isAdmin(ctx):
        return await ctx.respond("Only bot admins can use this command.")
    
    if days not in [30, 90]:
        return await ctx.respond("Boost days must be either 30 or 90.")
    
    await ctx.respond("Boosting started.")
    
    # Oczyszczenie invite code
    INVITE = invitecode.replace("//", "")
    if "/invite/" in INVITE:
        INVITE = INVITE.split("/invite/")[1]
    elif "/" in INVITE:
        INVITE = INVITE.split("/")[1]

    runBoost(INVITE, amount, days == 30)  # Jeśli dni = 30, tokeny będą miały ograniczony czas

    return await ctx.edit(content="Boosting finished!")

# Funkcje pomocnicze do pracy z tokenami i nagłówkami

def get_headers(token):
    """Generuje odpowiednie nagłówki dla żądań Discorda"""
    s = httpx.Client()
    # Pozyskiwanie niezbędnych ciasteczek i innych parametrów
    return s, {'Authorization': f'Bearer {token}'}

def get_all_tokens(filename):
    """Pobiera wszystkie tokeny z pliku"""
    with open(filename, 'r') as f:
        return [line.strip() for line in f.readlines()]

def validate_token(s, headers):
    """Sprawdza, czy token jest ważny"""
    response = s.get("https://discord.com/api/v9/users/@me", headers=headers)
    if response.status_code == 200:
        profile = response.json()
        return f"{profile['username']}#{profile['discriminator']}"
    return None

def do_boost(s, token, headers, profile, server_id, boost_id):
    """Aktywuje boost na serwerze"""
    boost_data = {"user_premium_guild_subscription_slot_ids": [boost_id]}
    response = s.put(f"https://discord.com/api/v9/guilds/{server_id}/premium/subscriptions", json=boost_data, headers=headers)
    return response.status_code == 201

def do_join_server(s, token, headers, profile, invite):
    """Dołącza do serwera przy użyciu zaproszenia"""
    response = s.post(f"https://discord.com/api/v9/invites/{invite}", headers=headers)
    if response.status_code == 200:
        server_id = response.json()["guild"]["id"]
        return True, server_id
    return False, None

# Uruchomienie bota
bot.run(settings["botToken"])
