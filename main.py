import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time, timezone
import os
import time as time_module

# ================= CONFIGURAÇÕES =================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')

ID_CANAIS_STR = os.getenv('ID_CANAL_NOTIFICACOES', '1500947090560389304,1501014726111395850')
CANAIS_NOTIFICACOES = [int(i.strip()) for i in ID_CANAIS_STR.split(',') if i.strip().isdigit()]
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

CACHE_EXPIRY = 3600 
cache_jogos = {}

if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado.")
    exit()

api_semaphore = asyncio.Semaphore(1)

EQUIPAS = {
    "benfica": {"id": 3006, "nome": "SL Benfica", "cor": 0xff0000},
    "porto": {"id": 3002, "nome": "FC Porto", "cor": 0x0000ff},
    "sporting": {"id": 3001, "nome": "Sporting CP", "cor": 0x00ff00},
    "braga": {"id": 2999, "nome": "SC Braga", "cor": 0xce1126}, 
    "portugal": {"id": 4704, "nome": "Seleção Portuguesa", "cor": 0x006600},
    "liverpool": {"id": 44, "nome": "Liverpool", "cor": 0xc8102E},
    "manunited": {"id": 35, "nome": "Manchester United", "cor": 0xDA291C},
    "mancity": {"id": 17, "nome": "Manchester City", "cor": 0x6CABDD},
    "arsenal": {"id": 42, "nome": "Arsenal", "cor": 0xEF0107},
    "chelsea": {"id": 38, "nome": "Chelsea FC", "cor": 0x034694},
    "tottenham": {"id": 33, "nome": "Tottenham Hotspur", "cor": 0x132257},
    "realmadrid": {"id": 2829, "nome": "Real Madrid", "cor": 0xffffff},
    "barcelona": {"id": 2817, "nome": "FC Barcelona", "cor": 0x004D98},
    "psg": {"id": 1644, "nome": "PSG", "cor": 0x004170},
    "bayern": {"id": 2672, "nome": "Bayern Munich", "cor": 0xDC052D}
}

intents = discord.Intents.default()
intents.message_content = True
intents.guild_scheduled_events = True 
bot = commands.Bot(command_prefix='!', intents=intents)

HEADERS_API = {
    'x-rapidapi-host': "sofasport.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

# User-Agent para o ZeroZero não bloquear o bot como "robô"
HEADERS_ZZ = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# ================= FUNÇÃO DE SCRAPING (ZEROZERO) =================

async def buscar_tv_portugal(session, home_name, away_name):
    """Tenta encontrar o canal de TV no ZeroZero para um jogo específico"""
    url = "https://www.zerozero.pt/futebol/todos-os-jogos"
    try:
        async with session.get(url, headers=HEADERS_ZZ, timeout=10) as response:
            if response.status != 200: return None
            
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            
            # Procura por todas as linhas de jogos na página
            jogos = soup.find_all('div', class_='match') 
            
            for jogo in jogos:
                texto_jogo = jogo.get_text().lower()
                # Verifica se as duas equipas aparecem na mesma linha
                if home_name.lower() in texto_jogo or away_name.lower() in texto_jogo:
                    # Tenta encontrar ícones de TV (geralmente tags <img> com alt ou title)
                    tv_icons = jogo.find_all('img', title=True)
                    for icon in tv_icons:
                        title = icon['title'].upper()
                        if any(x in title for x in ["SPORT TV", "DAZN", "TVI", "SIC", "RTP", "BTV", "CANAL 11"]):
                            return title
            return None
    except:
        return None

# ================= FUNÇÕES DE API =================

async def buscar_jogos_async(session, team_id, nome_equipa="Equipa", retries=2):
    agora = time_module.time()
    if team_id in cache_jogos:
        if agora - cache_jogos[team_id]["timestamp"] < CACHE_EXPIRY:
            return cache_jogos[team_id]["data"]

    url = "https://sofasport.p.rapidapi.com/v1/teams/events"
    params = {"team_id": str(team_id), "course_events": "next", "page": "0"}
    
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    eventos = data.get("data", {}).get("events", [])
                    cache_jogos[team_id] = {"data": eventos, "timestamp": agora}
                    return eventos
                return []
        except:
            return []

async def criar_evento_discord(guild, nome_jogo, data_inicio, liga, tv_info=None):
    if data_inicio.tzinfo is None: data_inicio = data_inicio.replace(tzinfo=timezone.utc)
    agora = datetime.now(timezone.utc)
    if data_inicio < agora or (data_inicio.hour == 12 and data_inicio.minute == 0): return False

    try:
        eventos_atuais = await guild.fetch_scheduled_events()
        for e in eventos_atuais:
            if e.name == nome_jogo and e.start_time.date() == data_inicio.date(): return False

        desc = f"🏆 {liga}"
        if tv_info: desc += f"\n📺 Transmissão: {tv_info}"
        desc += "\nVamos comentar o jogo no canal de voz!"

        data_fim = data_inicio + timedelta(hours=2)
        canal_voz = guild.get_channel(int(ID_CANAL_VOZ_STR)) if ID_CANAL_VOZ_STR else None

        if canal_voz:
            await guild.create_scheduled_event(
                name=nome_jogo, description=desc, start_time=data_inicio, end_time=data_fim,
                entity_type=discord.EntityType.voice, channel=canal_voz, privacy_level=discord.PrivacyLevel.guild_only
            )
        else:
            await guild.create_scheduled_event(
                name=nome_jogo, description=desc, start_time=data_inicio, end_time=data_fim,
                entity_type=discord.EntityType.external, location="Televisão", privacy_level=discord.PrivacyLevel.guild_only
            )
        return True
    except:
        return False

# ================= AGENDAS =================

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo, filtro_lista=None, filtrar_liga=None):
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🚀 A consultar agenda e canais de TV (ZeroZero)...")
    
    embed = discord.Embed(title=f"⚽ {titulo}", color=0xf1c40f)
    encontrou = False
    equipas_alvo = {k: EQUIPAS[k] for k in filtro_lista if k in EQUIPAS} if filtro_lista else EQUIPAS

    async with aiohttp.ClientSession() as session:
        # 1. Buscar jogos da API
        tarefas = [buscar_jogos_async(session, info["id"], info["nome"]) for info in equipas_alvo.values()]
        resultados = await asyncio.gather(*tarefas)

        for (chave, info), eventos in zip(equipas_alvo.items(), resultados):
            for j in eventos:
                ts = j.get("startTimestamp")
                if ts:
                    dt_jogo = datetime.fromtimestamp(ts, tz=timezone.utc)
                    liga_nome = j.get("tournament", {}).get("name", "Competição")
                    
                    if data_alvo and dt_jogo.date() != data_alvo: continue
                    if filtrar_liga and filtrar_liga.lower() not in liga_nome.lower(): continue

                    encontrou = True
                    home = j.get("homeTeam", {}).get("name", "N/A")
                    away = j.get("awayTeam", {}).get("name", "N/A")
                    
                    # 2. SE encontrar jogo hoje/amanhã, tenta buscar TV no ZeroZero
                    tv_info = await buscar_tv_portugal(session, home, away)
                    
                    if canal_ou_ctx.guild:
                        await criar_evento_discord(canal_ou_ctx.guild, f"{home} vs {away}", dt_jogo, liga_nome, tv_info)

                    hora_f = dt_jogo.strftime('%H:%M') if not (dt_jogo.hour == 12 and dt_jogo.minute == 0) else dt_jogo.strftime('%d/%m (TBD)')
                    tv_str = f"\n📺 **{tv_info}**" if tv_info else ""
                    
                    embed.add_field(
                        name=f"🥅 {info['nome']}",
                        value=f"🏆 {liga_nome}\n🕒 **{hora_f}**{tv_str}\n**{home}** vs **{away}**",
                        inline=False
                    )
                    break 

    if not encontrou:
        if msg: await msg.edit(content=f"📅 Sem jogos para {titulo}.")
        else: await canal_ou_ctx.send(f"📅 Sem jogos para {titulo}.")
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

# ================= COMANDOS =================

@bot.command()
async def hoje(ctx): await gerar_agenda_data(ctx, datetime.now(timezone.utc).date(), "Hoje")

@bot.command()
async def amanha(ctx):
    amanha_data = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    await gerar_agenda_data(ctx, amanha_data, "Amanhã")

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha` (Com canais de TV 🇵🇹)", inline=False)
    embed.add_field(name="⚽ Equipas", value=", ".join([f"!{k}" for k in EQUIPAS.keys()]), inline=False)
    await ctx.send(embed=embed)

# --- Comandos individuais de equipas simplificados para usar o novo motor ---
async def cmd_equipa(ctx, chave):
    await gerar_agenda_data(ctx, None, f"Agenda: {EQUIPAS[chave]['nome']}", filtro_lista=[chave])

@bot.command()
async def psg(ctx): await cmd_equipa(ctx, "psg")
@bot.command()
async def bayern(ctx): await cmd_equipa(ctx, "bayern")
@bot.command()
async def benfica(ctx): await cmd_equipa(ctx, "benfica")
@bot.command()
async def porto(ctx): await cmd_equipa(ctx, "porto")
@bot.command()
async def sporting(ctx): await cmd_equipa(ctx, "sporting")

@bot.event
async def on_ready():
    print(f'✅ Bot Online com suporte a TV (ZeroZero): {bot.user}')

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)