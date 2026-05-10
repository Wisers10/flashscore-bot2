import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, time, timezone
import os
import time as time_module
import re

# ================= CONFIGURAÇÕES =================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')

# IDs dos canais de notificações (Atualizado para apenas um canal conforme pedido)
ID_CANAIS_STR = os.getenv('ID_CANAL_NOTIFICACOES', '1501014726111395850')
CANAIS_NOTIFICACOES = [int(i.strip()) for i in ID_CANAIS_STR.split(',') if i.strip().isdigit()]
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

# Fuso horário de Portugal (Ajuste manual de +1h sobre o UTC)
OFFSET_PT = timedelta(hours=1)

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

HEADERS_WEB = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-PT,pt;q=0.9,en;q=0.8'
}

# ================= FUNÇÕES DE UTILIDADE =================

def normalizar_nome(nome):
    nome = nome.upper()
    substituicoes = {
        "PARIS SAINT-GERMAIN": "PSG", "BAYERN MÜNCHEN": "BAYERN", "BAYERN MUNICH": "BAYERN",
        "MANCHESTER CITY": "MAN CITY", "MANCHESTER UNITED": "MAN UTD", "SPORTING CP": "SPORTING",
        "SL BENFICA": "BENFICA", "FC PORTO": "PORTO", "SC BRAGA": "BRAGA"
    }
    for original, novo in substituicoes.items():
        if original in nome: return novo
    return re.sub(r'\b(FC|SL|SC|CP|REAL|ST|CLUB|ATLETICO)\b', '', nome).strip()

# ================= MOTOR DE BUSCA DE TV (JOGOSNA.TV) =================

async def buscar_tv_portugal(session, home_name, away_name):
    url = "https://www.jogosna.tv/"
    h_simple = normalizar_nome(home_name)
    a_simple = normalizar_nome(away_name)
    try:
        async with session.get(url, headers=HEADERS_WEB, timeout=12) as response:
            if response.status != 200: return None
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            blocos = soup.find_all(['div', 'tr', 'li'])
            for bloco in blocos:
                texto = bloco.get_text().upper()
                if h_simple in texto and a_simple in texto:
                    canais_pt = ["TVI", "SIC", "RTP 1", "RTP", "SPORT TV", "DAZN", "ELEVEN", "BTV", "CANAL 11", "EUROSPORT"]
                    for canal in canais_pt:
                        if canal in texto:
                            match = re.search(rf"{canal}\s*\d+", texto)
                            return match.group(0) if match else canal
            return None
    except: return None

# ================= FUNÇÕES DE API =================

async def buscar_jogos_async(session, team_id, nome_equipa="Equipa"):
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
        except: return []

async def criar_evento_discord(guild, nome_jogo, data_inicio_utc, liga, tv_info=None):
    data_pt = data_inicio_utc.replace(tzinfo=timezone.utc).astimezone(timezone(OFFSET_PT))
    agora_pt = datetime.now(timezone(OFFSET_PT))
    if data_pt < agora_pt or (data_pt.hour == 13 and data_pt.minute == 0): return False
    try:
        eventos_atuais = await guild.fetch_scheduled_events()
        for e in eventos_atuais:
            if e.name == nome_jogo and e.start_time.astimezone(timezone(OFFSET_PT)).date() == data_pt.date(): return False
        desc = f"🏆 {liga}\n📺 Transmissão: **{tv_info if tv_info else 'Não listado'}**\n\nVamos comentar o jogo no canal de voz!"
        data_fim = data_pt + timedelta(hours=2)
        canal_voz = guild.get_channel(int(ID_CANAL_VOZ_STR)) if ID_CANAL_VOZ_STR else None
        if canal_voz:
            await guild.create_scheduled_event(name=nome_jogo, description=desc, start_time=data_pt, end_time=data_fim, entity_type=discord.EntityType.voice, channel=canal_voz, privacy_level=discord.PrivacyLevel.guild_only)
        else:
            await guild.create_scheduled_event(name=nome_jogo, description=desc, start_time=data_pt, end_time=data_fim, entity_type=discord.EntityType.external, location="Televisão", privacy_level=discord.PrivacyLevel.guild_only)
        return True
    except: return False

# ================= AGENDAS =================

async def gerar_agenda_data(canal_ou_ctx, data_alvo_pt, titulo, filtro_lista=None, filtrar_liga=None):
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🚀 A consultar agenda e transmissões 🇵🇹...")
    
    embed = discord.Embed(title=f"⚽ {titulo}", color=0xf1c40f)
    encontrou = False
    jogos_processados = set() 
    equipas_alvo = {k: EQUIPAS[k] for k in filtro_lista if k in EQUIPAS} if filtro_lista else EQUIPAS

    async with aiohttp.ClientSession() as session:
        tarefas = [buscar_jogos_async(session, info["id"], info["nome"]) for info in equipas_alvo.values()]
        resultados = await asyncio.gather(*tarefas)
        for (chave, info), eventos in zip(equipas_alvo.items(), resultados):
            for j in eventos:
                ts = j.get("startTimestamp")
                if ts:
                    dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
                    dt_pt = dt_utc + OFFSET_PT
                    if data_alvo_pt and dt_pt.date() != data_alvo_pt: continue
                    if filtrar_liga and filtrar_liga.lower() not in j.get("tournament", {}).get("name", "").lower(): continue
                    home, away = j.get("homeTeam", {}).get("name", "N/A"), j.get("awayTeam", {}).get("name", "N/A")
                    jogo_id = f"{home}_{away}_{dt_pt.strftime('%Y%m%d')}"
                    if jogo_id in jogos_processados: continue
                    encontrou = True
                    jogos_processados.add(jogo_id)
                    tv_info = await buscar_tv_portugal(session, home, away)
                    if canal_ou_ctx.guild: await criar_evento_discord(canal_ou_ctx.guild, f"{home} vs {away}", dt_utc, j.get("tournament", {}).get("name", "Competição"), tv_info)
                    hora_f = dt_pt.strftime('%H:%M') if not (dt_pt.hour == 13 and dt_pt.minute == 0) else dt_pt.strftime('%d/%m (TBD)')
                    embed.add_field(name=f"🥅 Jogo do {info['nome']}", value=f"🏆 {j.get('tournament',{}).get('name')}\n🕒 **{hora_f}**\n📺 **{tv_info if tv_info else 'Não listado'}**\n**{home}** vs **{away}**", inline=False)
                    break 

    if not encontrou:
        t = f"📅 Sem jogos para {titulo}."
        if msg: await msg.edit(content=t)
        else: await canal_ou_ctx.send(t)
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

# ================= TAREFA AUTOMÁTICA DIÁRIA =================

@tasks.loop(time=time(hour=8, minute=0, tzinfo=timezone.utc)) # 09:00 Portugal (UTC+1)
async def notificacao_diaria():
    print(f"⏰ [SISTEMA] A executar tarefa agendada para {len(CANAIS_NOTIFICACOES)} canais...")
    hoje_pt = (datetime.now(timezone.utc) + OFFSET_PT).date()
    for id_canal in CANAIS_NOTIFICACOES:
        canal = bot.get_channel(id_canal)
        if canal:
            print(f"   - A enviar agenda automática para canal ID: {id_canal}")
            await gerar_agenda_data(canal, hoje_pt, "Agenda de Hoje")
            await asyncio.sleep(2)

# ================= COMANDOS =================

@bot.command()
async def hoje(ctx):
    hoje_pt = (datetime.now(timezone.utc) + OFFSET_PT).date()
    await gerar_agenda_data(ctx, hoje_pt, "Hoje")

@bot.command()
async def amanha(ctx):
    amanha_data = (datetime.now(timezone.utc) + OFFSET_PT + timedelta(days=1)).date()
    await gerar_agenda_data(ctx, amanha_data, "Amanhã")

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

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha` (Horário de Portugal 🇵🇹)", inline=False)
    embed.add_field(name="⚽ Equipas", value=", ".join([f"!{k}" for k in EQUIPAS.keys()]), inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'✅ Bot Online (Automação Ativa): {bot.user}')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)