import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta, time, timezone
import os

# ================= CONFIGURAÇÕES =================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')
ID_CANAL_STR = os.getenv('ID_CANAL_NOTIFICACOES', '123456789012345678')
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

ALLOWED_GUILDS_STR = os.getenv('ALLOWED_GUILDS', '') 
ALLOWED_GUILDS = [int(g.strip()) for g in ALLOWED_GUILDS_STR.split(',') if g.strip().isdigit()]

if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado.")
    exit()

ID_CANAL_NOTIFICACOES = int(ID_CANAL_STR)
api_semaphore = asyncio.Semaphore(5)

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

EQUIPAS_PREMIER = ["liverpool", "manunited", "mancity", "arsenal", "chelsea", "tottenham"]
EQUIPAS_LIGA = ["benfica", "porto", "sporting", "braga"]

intents = discord.Intents.default()
intents.message_content = True
intents.guild_scheduled_events = True 
bot = commands.Bot(command_prefix='!', intents=intents)

HEADERS = {
    'x-rapidapi-host': "sofasport.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

# ================= FILTRO DE PRIVACIDADE =================

@bot.check
async def is_guild_allowed(ctx):
    if not ALLOWED_GUILDS: return True
    return ctx.guild and ctx.guild.id in ALLOWED_GUILDS

# ================= APOIO ASSÍNCRONO =================

async def buscar_jogos_async(session, team_id, nome_equipa="Desconhecida"):
    url = "https://sofasport.p.rapidapi.com/v1/teams/events"
    params = {"team_id": str(team_id), "course_events": "next", "page": "0"}
    async with api_semaphore:
        try:
            async with session.get(url, params=params, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {}).get("events", [])
                return []
        except Exception as e:
            print(f"❌ [API] {nome_equipa}: {e}")
            return []

# ================= EVENTOS DISCORD =================

async def criar_evento_discord(guild, nome_jogo, data_inicio, liga):
    if data_inicio.tzinfo is None:
        data_inicio = data_inicio.replace(tzinfo=timezone.utc)

    if data_inicio < datetime.now(timezone.utc) or (data_inicio.hour == 12 and data_inicio.minute == 0):
        return False

    try:
        try:
            eventos_atuais = await guild.fetch_scheduled_events()
        except discord.Forbidden:
            return False

        for e in eventos_atuais:
            if e.name == nome_jogo and e.start_time.date() == data_inicio.date():
                return False

        data_fim = data_inicio + timedelta(hours=2)
        canal_voz = guild.get_channel(int(ID_CANAL_VOZ_STR)) if ID_CANAL_VOZ_STR else None

        if canal_voz and isinstance(canal_voz, discord.VoiceChannel):
            await guild.create_scheduled_event(
                name=nome_jogo,
                description=f"🏆 {liga} - Vamos comentar o jogo no canal de voz!",
                start_time=data_inicio,
                end_time=data_fim,
                entity_type=discord.EntityType.voice,
                channel=canal_voz,
                privacy_level=discord.PrivacyLevel.guild_only
            )
        else:
            await guild.create_scheduled_event(
                name=nome_jogo,
                description=f"🏆 {liga} - Acompanha o jogo!",
                start_time=data_inicio,
                end_time=data_fim,
                entity_type=discord.EntityType.external,
                location="Televisão / Estádio",
                privacy_level=discord.PrivacyLevel.guild_only
            )
        return True
    except Exception as e:
        print(f"❌ [ERRO EVENTO] {e}")
        return False

# ================= AGENDAS E TAREFAS =================

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo, filtro_lista=None, filtrar_liga=None):
    msg = await canal_ou_ctx.send(f"🚀 A processar agenda para {titulo}...") if isinstance(canal_ou_ctx, commands.Context) else None
    guild = canal_ou_ctx.guild
    
    embed = discord.Embed(title=f"⚽ {titulo}", color=0xf1c40f)
    encontrou = False
    jogos_adicionados = set()
    
    equipas_alvo = {k: EQUIPAS[k] for k in filtro_lista if k in EQUIPAS} if filtro_lista else EQUIPAS

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        ids = [info["id"] for info in equipas_alvo.values()]
        nomes = [info["nome"] for info in equipas_alvo.values()]
        tarefas = [buscar_jogos_async(session, team_id, nome) for team_id, nome in zip(ids, nomes)]
        
        resultados = await asyncio.gather(*tarefas)

        for nome_equipa_original, eventos in zip(nomes, resultados):
            for j in eventos:
                ts = j.get("startTimestamp")
                if ts:
                    dt_jogo = datetime.fromtimestamp(ts, tz=timezone.utc)
                    liga_nome = j.get("tournament", {}).get("name", "Competição")
                    
                    # Filtro de data: Se data_alvo for definida, tem de bater certo
                    if data_alvo and dt_jogo.date() != data_alvo:
                        continue
                    
                    # Filtro de liga (mais abrangente para Champions por exemplo)
                    if filtrar_liga:
                        palavras_filtro = filtrar_liga.lower().split()
                        if not all(p in liga_nome.lower() for p in palavras_filtro):
                            continue

                    home = j.get("homeTeam", {}).get("name", "N/A")
                    away = j.get("awayTeam", {}).get("name", "N/A")
                    nome_jogo = f"{home} vs {away}"
                    
                    jogo_id = f"{nome_jogo}_{dt_jogo.strftime('%Y%m%d')}"
                    if jogo_id in jogos_adicionados:
                        continue
                    
                    encontrou = True
                    jogos_adicionados.add(jogo_id)
                    
                    if guild:
                        await criar_evento_discord(guild, nome_jogo, dt_jogo, liga_nome)

                    hora_f = dt_jogo.strftime('%H:%M') if not (dt_jogo.hour == 12 and dt_jogo.minute == 0) else dt_jogo.strftime('%d/%m (TBD)')
                    data_str = "" if data_alvo else f"📅 {dt_jogo.strftime('%d/%m')} "
                    
                    embed.add_field(name=f"🥅 {nome_jogo}", value=f"🏆 {liga_nome}\n🕒 {data_str}**{hora_f}**", inline=False)
                    break 

    if not encontrou:
        t = f"📅 Sem jogos encontrados para {titulo}."
        if msg: await msg.edit(content=t)
        else: await canal_ou_ctx.send(t)
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

@tasks.loop(time=time(hour=9, minute=0, tzinfo=timezone.utc))
async def notificacao_diaria():
    canal = bot.get_channel(ID_CANAL_NOTIFICACOES)
    if canal:
        # Hoje em Portugal (aproximado via UTC+1)
        hoje_date = (datetime.now(timezone.utc) + timedelta(hours=1)).date()
        await gerar_agenda_data(canal, hoje_date, "Agenda de Hoje")

# ================= COMANDOS =================

@bot.command()
async def hoje(ctx): 
    hoje_date = (datetime.now(timezone.utc) + timedelta(hours=1)).date()
    await gerar_agenda_data(ctx, hoje_date, "Agenda de Hoje")

@bot.command()
async def amanha(ctx): 
    # Calculamos amanhã com base na hora de Portugal (UTC+1)
    amanha_date = (datetime.now(timezone.utc) + timedelta(hours=1) + timedelta(days=1)).date()
    await gerar_agenda_data(ctx, amanha_date, "Agenda de Amanhã")

@bot.command()
async def champions(ctx):
    # Mostra os próximos jogos da Champions (filtro flexível)
    await gerar_agenda_data(ctx, None, "Próximos Jogos: UEFA Champions League", filtrar_liga="Champions League")

@bot.command()
async def premier(ctx): 
    await gerar_agenda_data(ctx, None, "Próximos Jogos: Premier League", filtro_lista=EQUIPAS_PREMIER, filtrar_liga="Premier League")

@bot.command(aliases=['ligaportugal'])
async def liga(ctx): 
    await gerar_agenda_data(ctx, None, "Próximos Jogos: Liga Portugal", filtro_lista=EQUIPAS_LIGA, filtrar_liga="Liga Portugal")

async def comando_equipa(ctx, chave):
    info = EQUIPAS[chave]
    await ctx.send(f"🔍 A consultar agenda do **{info['nome']}**...")
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        eventos = await buscar_jogos_async(session, info["id"], info["nome"])
        if not eventos: return await ctx.send(f"⚠️ Sem jogos futuros para {info['nome']}.")
        
        embed = discord.Embed(title=f"🥅 Próximos Jogos: {info['nome']}", color=info["cor"])
        for j in eventos[:3]:
            ts = j.get("startTimestamp")
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_f = dt.strftime('%d/%m %H:%M') if not (dt.hour == 12 and dt.minute == 0) else dt.strftime('%d/%m (TBD)')
            embed.add_field(name=f"🏆 {j.get('tournament', {}).get('name')}", value=f"📅 `{dt_f}`\n**{j['homeTeam']['name']}** vs **{j['awayTeam']['name']}**", inline=False)
        await ctx.send(embed=embed)

@bot.command()
async def benfica(ctx): await comando_equipa(ctx, "benfica")
@bot.command()
async def porto(ctx): await comando_equipa(ctx, "porto")
@bot.command()
async def sporting(ctx): await comando_equipa(ctx, "sporting")
@bot.command()
async def braga(ctx): await comando_equipa(ctx, "braga")
@bot.command()
async def liverpool(ctx): await comando_equipa(ctx, "liverpool")
@bot.command()
async def manunited(ctx): await comando_equipa(ctx, "manunited")
@bot.command()
async def mancity(ctx): await comando_equipa(ctx, "mancity")
@bot.command()
async def arsenal(ctx): await comando_equipa(ctx, "arsenal")
@bot.command()
async def chelsea(ctx): await comando_equipa(ctx, "chelsea")
@bot.command()
async def tottenham(ctx): await comando_equipa(ctx, "tottenham")
@bot.command()
async def realmadrid(ctx): await comando_equipa(ctx, "realmadrid")
@bot.command()
async def barcelona(ctx): await comando_equipa(ctx, "barcelona")
@bot.command()
async def psg(ctx): await comando_equipa(ctx, "psg")
@bot.command()
async def bayern(ctx): await comando_equipa(ctx, "bayern")
@bot.command()
async def portugal(ctx): await comando_equipa(ctx, "portugal")

@bot.command()
async def verificar(ctx, *, equipa: str):
    equipa = equipa.lower().strip()
    chave = next((k for k in EQUIPAS if k in equipa or equipa in k), None)
    if not chave: return await ctx.send(f"❌ Equipa '{equipa}' não listada.")
    
    info = EQUIPAS[chave]
    msg = await ctx.send(f"🔍 Verificando **{info['nome']}**...")
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        eventos = await buscar_jogos_async(session, info["id"], info["nome"])
        if not eventos: return await msg.edit(content=f"⚠️ Sem jogos na API.")
        prox = eventos[0]
        dt = datetime.fromtimestamp(prox['startTimestamp'], tz=timezone.utc)
        await msg.edit(content=f"📊 **{info['nome']}**\n⚽ {prox['homeTeam']['name']} vs {prox['awayTeam']['name']}\n📅 {dt.strftime('%d/%m %H:%M UTC')}")

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha` (Inclui Champions e todas as equipas)", inline=False)
    embed.add_field(name="🏆 Competições", value="`!liga`, `!premier`, `!champions` (Próximos grandes jogos)", inline=False)
    embed.add_field(name="⚽ Equipas", value=", ".join([f"`!{k}`" for k in EQUIPAS.keys()]), inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'✅ Bot Online e Estável: {bot.user}')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

bot.run(DISCORD_TOKEN)