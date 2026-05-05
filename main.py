import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta, time, timezone
import os

# ================= CONFIGURAÇÕES =================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')

# IDs dos canais de notificações (Configurado para suportar os dois canais pedidos)
ID_CANAIS_STR = os.getenv('ID_CANAL_NOTIFICACOES', '1500947090560389304,1501014726111395850')
CANAIS_NOTIFICACOES = [int(i.strip()) for i in ID_CANAIS_STR.split(',') if i.strip().isdigit()]

# ID do canal de voz associado aos eventos (813485447719813207)
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado nas variáveis de ambiente.")
    exit()

# Limita o número de pedidos simultâneos para evitar o Erro 429 (Rate Limit)
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

# Grupos para comandos de liga
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

# ================= FUNÇÕES ASSÍNCRONAS (VELOCIDADE) =================

async def buscar_jogos_async(session, team_id, nome_equipa="Equipa"):
    """Consulta a API de forma assíncrona respeitando o semáforo de tráfego"""
    url = "https://sofasport.p.rapidapi.com/v1/teams/events"
    params = {"team_id": str(team_id), "course_events": "next", "page": "0"}
    
    async with api_semaphore:
        try:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    eventos = data.get("data", {}).get("events", [])
                    print(f"📊 [API] {nome_equipa}: {len(eventos)} eventos recebidos.")
                    return eventos
                elif response.status == 429:
                    print(f"⚠️ [API] Rate Limit para {nome_equipa}. A tentar processar mais tarde.")
                    return []
                return []
        except Exception as e:
            print(f"❌ [API] Falha em {nome_equipa}: {e}")
            return []

async def criar_evento_discord(guild, nome_jogo, data_inicio, liga):
    """Cria um evento agendado no canal de voz definido"""
    if data_inicio.tzinfo is None:
        data_inicio = data_inicio.replace(tzinfo=timezone.utc)

    agora = datetime.now(timezone.utc)
    if data_inicio < agora or (data_inicio.hour == 12 and data_inicio.minute == 0):
        return False

    try:
        eventos_atuais = await guild.fetch_scheduled_events()
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
            print(f"✅ [EVENTO] Criado no Canal de Voz: {nome_jogo}")
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
            print(f"✅ [EVENTO] Criado Externo: {nome_jogo}")
        return True
    except Exception as e:
        print(f"❌ [ERRO EVENTO] {e}")
        return False

# ================= AGENDAS =================

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo, filtro_lista=None, filtrar_liga=None):
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🚀 A consultar agenda para {titulo} (Modo Turbo)...")
    
    print(f"📅 [AGENDA] Início da consulta: {titulo}")
    embed = discord.Embed(title=f"⚽ {titulo}", color=0xf1c40f)
    encontrou = False
    
    equipas_alvo = {k: EQUIPAS[k] for k in filtro_lista if k in EQUIPAS} if filtro_lista else EQUIPAS

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Cria todas as tarefas para serem executadas ao mesmo tempo
        tarefas = [buscar_jogos_async(session, info["id"], info["nome"]) for info in equipas_alvo.values()]
        resultados = await asyncio.gather(*tarefas)

        # Processa os resultados de forma organizada
        for (chave, info), eventos in zip(equipas_alvo.items(), resultados):
            for j in eventos:
                ts = j.get("startTimestamp")
                if ts:
                    dt_jogo = datetime.fromtimestamp(ts, tz=timezone.utc)
                    liga_nome = j.get("tournament", {}).get("name", "Competição")
                    
                    if data_alvo and dt_jogo.date() != data_alvo:
                        continue
                    
                    if filtrar_liga and filtrar_liga.lower() not in liga_nome.lower():
                        continue

                    encontrou = True
                    home = j.get("homeTeam", {}).get("name", "N/A")
                    away = j.get("awayTeam", {}).get("name", "N/A")
                    nome_jogo = f"{home} vs {away}"

                    if canal_ou_ctx.guild:
                        await criar_evento_discord(canal_ou_ctx.guild, nome_jogo, dt_jogo, liga_nome)

                    hora_f = dt_jogo.strftime('%H:%M') if not (dt_jogo.hour == 12 and dt_jogo.minute == 0) else dt_jogo.strftime('%d/%m (TBD)')
                    data_str = "" if data_alvo else f"📅 {dt_jogo.strftime('%d/%m')} "
                    
                    embed.add_field(
                        name=f"🥅 {info['nome']}",
                        value=f"🏆 {liga_nome}\n🕒 {data_str}**{hora_f}**\n**{home}** vs **{away}**",
                        inline=False
                    )
                    break 

    if not encontrou:
        t = f"📅 Não encontrei jogos para {titulo}."
        if msg: await msg.edit(content=t)
        else: await canal_ou_ctx.send(t)
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

# ================= COMANDOS =================

@bot.command()
async def hoje(ctx):
    await gerar_agenda_data(ctx, datetime.now(timezone.utc).date(), "Hoje")

@bot.command()
async def amanha(ctx):
    amanha_data = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    await gerar_agenda_data(ctx, amanha_data, "Amanhã")

@bot.command()
async def premier(ctx):
    await gerar_agenda_data(ctx, None, "Próximos Jogos: Premier League", filtro_lista=EQUIPAS_PREMIER, filtrar_liga="Premier")

@bot.command(aliases=['ligaportugal'])
async def liga(ctx):
    await gerar_agenda_data(ctx, None, "Próximos Jogos: Liga Portugal", filtro_lista=EQUIPAS_LIGA, filtrar_liga="Portugal")

@bot.command()
async def champions(ctx):
    await gerar_agenda_data(ctx, None, "Próximos Jogos: Champions League", filtrar_liga="Champions")

async def cmd_equipa(ctx, chave):
    info = EQUIPAS[chave]
    await ctx.send(f"🔍 A consultar agenda do **{info['nome']}**...")
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        eventos = await buscar_jogos_async(session, info["id"], info["nome"])
        if not eventos: return await ctx.send(f"⚠️ Sem jogos para {info['nome']}.")
        
        embed = discord.Embed(title=f"🥅 Agenda: {info['nome']}", color=info["cor"])
        for j in eventos[:3]:
            ts = j.get("startTimestamp")
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_f = dt.strftime('%d/%m %H:%M') if not (dt.hour == 12 and dt.minute == 0) else dt.strftime('%d/%m (TBD)')
            embed.add_field(name=f"🏆 {j.get('tournament',{}).get('name')}", value=f"📅 `{dt_f}`\n**{j['homeTeam']['name']}** vs **{j['awayTeam']['name']}**", inline=False)
        await ctx.send(embed=embed)

@bot.command()
async def benfica(ctx): await cmd_equipa(ctx, "benfica")
@bot.command()
async def porto(ctx): await cmd_equipa(ctx, "porto")
@bot.command()
async def sporting(ctx): await cmd_equipa(ctx, "sporting")
@bot.command()
async def braga(ctx): await cmd_equipa(ctx, "braga")
@bot.command()
async def liverpool(ctx): await cmd_equipa(ctx, "liverpool")
@bot.command()
async def manunited(ctx): await cmd_equipa(ctx, "manunited")
@bot.command()
async def mancity(ctx): await cmd_equipa(ctx, "mancity")
@bot.command()
async def arsenal(ctx): await cmd_equipa(ctx, "arsenal")
@bot.command()
async def chelsea(ctx): await cmd_equipa(ctx, "chelsea")
@bot.command()
async def tottenham(ctx): await cmd_equipa(ctx, "tottenham")
@bot.command()
async def realmadrid(ctx): await cmd_equipa(ctx, "realmadrid")
@bot.command()
async def barcelona(ctx): await cmd_equipa(ctx, "barcelona")
@bot.command()
async def psg(ctx): await cmd_equipa(ctx, "psg")
@bot.command()
async def bayern(ctx): await cmd_equipa(ctx, "bayern")
@bot.command()
async def portugal(ctx): await cmd_equipa(ctx, "portugal")

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha` (Rápido e Automático)", inline=False)
    embed.add_field(name="🏆 Competições", value="`!liga`, `!premier`, `!champions`", inline=False)
    embed.add_field(name="⚽ Equipas", value=", ".join([f"!{k}" for k in EQUIPAS.keys()]), inline=False)
    await ctx.send(embed=embed)

@tasks.loop(time=time(hour=9, minute=0, tzinfo=timezone.utc))
async def notificacao_diaria():
    print(f"⏰ [SISTEMA] A enviar tarefa agendada para {len(CANAIS_NOTIFICACOES)} canais...")
    hoje_dt = datetime.now(timezone.utc).date()
    for id_canal in CANAIS_NOTIFICACOES:
        canal = bot.get_channel(id_canal)
        if canal:
            await gerar_agenda_data(canal, hoje_dt, "Agenda de Hoje")
            await asyncio.sleep(2) # Pequena pausa entre canais por segurança

@bot.event
async def on_ready():
    print(f'✅ [SISTEMA] Bot Online e Otimizado: {bot.user}')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)