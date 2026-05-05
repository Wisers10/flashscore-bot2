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

# Fuso horário de Portugal (UTC+1 para Verão / UTC+0 para Inverno)
# Usamos +1 como padrão para o horário de Verão atual
TZ_PT = timezone(timedelta(hours=1))

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
    """Cria um evento agendado no Discord com segurança"""
    # Converter para o fuso horário de Portugal para exibição correta
    data_inicio_pt = data_inicio.astimezone(TZ_PT)
    agora_pt = datetime.now(TZ_PT)

    # Ignorar se o jogo já começou ou for TBD (12:00 UTC costuma ser placeholder)
    if data_inicio_pt < agora_pt or (data_inicio.hour == 12 and data_inicio.minute == 0):
        return False

    try:
        try:
            eventos_atuais = await guild.fetch_scheduled_events()
        except discord.Forbidden:
            return False

        # Verifica se já existe um evento para este jogo no mesmo dia
        for e in eventos_atuais:
            if e.name == nome_jogo and e.start_time.astimezone(TZ_PT).date() == data_inicio_pt.date():
                return False

        data_fim = data_inicio_pt + timedelta(hours=2)
        canal_voz = None
        if ID_CANAL_VOZ_STR:
            try:
                canal_voz = guild.get_channel(int(ID_CANAL_VOZ_STR))
            except:
                canal_voz = None

        if canal_voz and isinstance(canal_voz, discord.VoiceChannel):
            await guild.create_scheduled_event(
                name=nome_jogo,
                description=f"🏆 {liga} - Vamos comentar o jogo no canal de voz!",
                start_time=data_inicio_pt,
                end_time=data_fim,
                entity_type=discord.EntityType.voice,
                channel=canal_voz,
                privacy_level=discord.PrivacyLevel.guild_only
            )
        else:
            await guild.create_scheduled_event(
                name=nome_jogo,
                description=f"🏆 {liga} - Acompanha o jogo!",
                start_time=data_inicio_pt,
                end_time=data_fim,
                entity_type=discord.EntityType.external,
                location="Televisão / Estádio",
                privacy_level=discord.PrivacyLevel.guild_only
            )
        print(f"✅ Evento criado: {nome_jogo}")
        return True
    except Exception as e:
        print(f"❌ Erro ao criar evento: {e}")
        return False

# ================= AGENDAS E TAREFAS =================

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo, filtro_lista=None, filtrar_liga=None):
    # Feedback inicial para o utilizador
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🔍 A consultar a base de dados para: **{titulo}**...")
    
    embed = discord.Embed(title=f"⚽ {titulo}", color=0xf1c40f)
    encontrou = False
    jogos_adicionados = set()
    
    # Define quais equipas pesquisar
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
                    # Converter timestamp para datetime em Portugal
                    dt_jogo_pt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(TZ_PT)
                    liga_nome = j.get("tournament", {}).get("name", "Competição")
                    
                    # Filtro de data: compara apenas o dia/mês/ano
                    if data_alvo and dt_jogo_pt.date() != data_alvo:
                        continue
                    
                    # Filtro de liga (opcional, ex: para !champions)
                    if filtrar_liga:
                        palavras = filtrar_liga.lower().split()
                        if not all(p in liga_nome.lower() for p in palavras):
                            continue

                    home = j.get("homeTeam", {}).get("name", "N/A")
                    away = j.get("awayTeam", {}).get("name", "N/A")
                    nome_jogo = f"{home} vs {away}"
                    
                    # Evitar duplicados no mesmo embed
                    jogo_id = f"{nome_jogo}_{dt_jogo_pt.strftime('%Y%m%d')}"
                    if jogo_id in jogos_adicionados:
                        continue
                    
                    encontrou = True
                    jogos_adicionados.add(jogo_id)
                    
                    # Criar evento no Discord se estivermos num servidor
                    if canal_ou_ctx.guild:
                        await criar_evento_discord(canal_ou_ctx.guild, nome_jogo, dt_jogo_pt, liga_nome)

                    hora_f = dt_jogo_pt.strftime('%H:%M') if not (dt_jogo_pt.hour == 12 and dt_jogo_pt.minute == 0) else dt_jogo_pt.strftime('%d/%m (TBD)')
                    data_exibicao = "" if data_alvo else f"📅 {dt_jogo_pt.strftime('%d/%m')} "
                    
                    embed.add_field(
                        name=f"🥅 {nome_jogo}", 
                        value=f"🏆 {liga_nome}\n🕒 {data_exibicao}**{hora_f}**", 
                        inline=False
                    )
                    # Encontramos o jogo desta equipa para este critério, passamos à próxima equipa
                    break 

    if not encontrou:
        aviso = f"📅 Não foram encontrados jogos das tuas equipas para **{titulo}**."
        if msg: await msg.edit(content=aviso)
        else: await canal_ou_ctx.send(aviso)
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

@tasks.loop(time=time(hour=9, minute=0, tzinfo=timezone.utc))
async def notificacao_diaria():
    canal = bot.get_channel(ID_CANAL_NOTIFICACOES)
    if canal:
        hoje_pt = datetime.now(TZ_PT).date()
        await gerar_agenda_data(canal, hoje_pt, "Agenda de Hoje")

# ================= COMANDOS =================

@bot.command()
async def hoje(ctx): 
    hoje_pt = datetime.now(TZ_PT).date()
    await gerar_agenda_data(ctx, hoje_pt, "Agenda de Hoje")

@bot.command()
async def amanha(ctx): 
    amanha_pt = (datetime.now(TZ_PT) + timedelta(days=1)).date()
    await gerar_agenda_data(ctx, amanha_pt, "Agenda de Amanhã")

@bot.command()
async def champions(ctx):
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
            dt_pt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(TZ_PT)
            dt_f = dt_pt.strftime('%d/%m %H:%M') if not (dt_pt.hour == 12 and dt_pt.minute == 0) else dt_pt.strftime('%d/%m (TBD)')
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
        dt_pt = datetime.fromtimestamp(prox['startTimestamp'], tz=timezone.utc).astimezone(TZ_PT)
        await msg.edit(content=f"📊 **{info['nome']}**\n⚽ {prox['homeTeam']['name']} vs {prox['awayTeam']['name']}\n📅 {dt_pt.strftime('%d/%m %H:%M %Z')}")

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