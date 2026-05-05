import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime, timedelta, time, timezone
import asyncio
import os

# ================= CONFIGURAÇÕES =================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')
ID_CANAL_NOTIFICACOES_STR = os.getenv('ID_CANAL_NOTIFICACOES', '1501014726111395850')

# ID do canal de voz associado aos eventos (813485447719813207)
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

# SEGURANÇA: Servidores autorizados
ALLOWED_GUILDS_STR = os.getenv('ALLOWED_GUILDS', '') 
ALLOWED_GUILDS = [int(g.strip()) for g in ALLOWED_GUILDS_STR.split(',') if g.strip().isdigit()]

if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado.")
    exit()

ID_CANAL_NOTIFICACOES = int(ID_CANAL_NOTIFICACOES_STR)

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

# Host configurado para sofascore6
HEADERS = {
    'x-rapidapi-host': "sofascore6.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

# ================= FILTRO DE PRIVACIDADE =================

@bot.check
async def is_guild_allowed(ctx):
    if not ALLOWED_GUILDS: return True
    return ctx.guild and ctx.guild.id in ALLOWED_GUILDS

# ================= FUNÇÕES DE EVENTOS DO DISCORD =================

async def criar_evento_discord(guild, nome_jogo, data_inicio, liga):
    if data_inicio.tzinfo is None:
        data_inicio = data_inicio.replace(tzinfo=timezone.utc)

    agora = datetime.now(timezone.utc)
    if data_inicio < agora or (data_inicio.hour == 12 and data_inicio.minute == 0):
        return False

    try:
        try:
            eventos_atuais = await guild.fetch_scheduled_events()
        except discord.Forbidden:
            print(f"🚫 [EVENTO] Sem permissão para ler eventos no servidor: {guild.name}")
            return False

        for e in eventos_atuais:
            if e.name == nome_jogo and e.start_time.date() == data_inicio.date():
                return False

        data_fim = data_inicio + timedelta(hours=2)
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
        print(f"✅ [EVENTO] Criado: {nome_jogo} em {guild.name}")
        return True
    except Exception as e:
        print(f"❌ [ERRO EVENTO] Falha ao criar {nome_jogo}: {e}")
        return False

# ================= FUNÇÕES DE API =================

def buscar_jogos_sofasport(team_id, nome_equipa="Equipa", retries=2):
    """
    Função resiliente que tenta diferentes caminhos comuns para o Host sofascore6.
    """
    # Lista de endpoints possíveis para tentar resolver o erro 404
    endpoints = [
        f"https://sofascore6.p.rapidapi.com/api/v1/team/{team_id}/events",
        f"https://sofascore6.p.rapidapi.com/api/v1/team/{team_id}/matches",
        f"https://sofascore6.p.rapidapi.com/api/sofascore/v1/team/{team_id}/events"
    ]
    
    for url in endpoints:
        for i in range(retries):
            print(f"🌐 [API] A consultar: {nome_equipa} em {url} (Tentativa {i+1})")
            try:
                r = requests.get(url, headers=HEADERS, timeout=10)
                
                if r.status_code == 200:
                    data = r.json()
                    # Tenta extrair a lista de eventos de chaves comuns
                    eventos = data.get("events", [])
                    if not eventos:
                        eventos = data.get("data", {}).get("events", [])
                    
                    if eventos:
                        print(f"✅ [API] Sucesso para {nome_equipa}: {len(eventos)} eventos.")
                        return eventos
                
                if r.status_code == 429:
                    wait_time = (i + 1) * 3
                    print(f"⚠️ [API] Rate Limit. Esperando {wait_time}s...")
                    import time
                    time.sleep(wait_time)
                    continue
                
                if r.status_code == 404:
                    print(f"❌ [API] Erro 404 para {nome_equipa} no URL {url}.")
                    break # Tenta o próximo URL na lista
                    
            except Exception as e:
                print(f"❌ [API] Erro de conexão: {e}")
                break
                
    return []

# ================= AGENDAS E TAREFAS =================

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo, filtro_lista=None, filtrar_liga=None):
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🔍 A consultar a agenda para {titulo}...")
    
    print(f"📅 [AGENDA] A iniciar: {data_alvo} ({titulo})")
    embed = discord.Embed(title=f"⚽ Agenda: {titulo}", color=0xf1c40f)
    encontrou = False
    jogos_adicionados = set()
    
    # Define quais equipas pesquisar
    equipas_alvo = {k: EQUIPAS[k] for k in filtro_lista if k in EQUIPAS} if filtro_lista else EQUIPAS

    for chave, info in equipas_alvo.items():
        eventos = buscar_jogos_sofasport(info["id"], info["nome"])
        for j in eventos:
            ts = j.get("startTimestamp")
            if ts:
                dt_jogo = datetime.fromtimestamp(ts, tz=timezone.utc)
                liga_nome = j.get("tournament", {}).get("name", "Competição")
                
                # Filtro de data (se data_alvo for None, ignora este filtro para comandos de liga)
                if data_alvo and dt_jogo.date() != data_alvo:
                    continue
                
                # Filtro de liga (ex: para !champions)
                if filtrar_liga and filtrar_liga.lower() not in liga_nome.lower():
                    continue

                home = j.get("homeTeam", {}).get("name", "N/A")
                away = j.get("awayTeam", {}).get("name", "N/A")
                nome_jogo = f"{home} vs {away}"
                
                # Evitar duplicados no embed
                jogo_id = f"{nome_jogo}_{dt_jogo.strftime('%Y%m%d')}"
                if jogo_id in jogos_adicionados:
                    continue
                
                encontrou = True
                jogos_adicionados.add(jogo_id)

                if canal_ou_ctx.guild:
                    await criar_evento_discord(canal_ou_ctx.guild, nome_jogo, dt_jogo, liga_nome)

                hora_f = dt_jogo.strftime('%H:%M') if not (dt_jogo.hour == 12 and dt_jogo.minute == 0) else dt_jogo.strftime('%d/%m (TBD)')
                data_str = "" if data_alvo else f"📅 {dt_jogo.strftime('%d/%m')} "
                
                embed.add_field(
                    name=f"🥅 {nome_jogo}", 
                    value=f"🏆 {liga_nome}\n🕒 {data_str}**{hora_f}**", 
                    inline=False
                )
                break 
        # Delay fixo para respeitar Rate Limit
        await asyncio.sleep(1.5)

    if not encontrou:
        aviso = f"📅 Não foram encontrados jogos das tuas equipas para {titulo}."
        if msg: await msg.edit(content=aviso)
        else: await canal_ou_ctx.send(aviso)
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

@tasks.loop(time=time(hour=9, minute=0, tzinfo=timezone.utc))
async def notificacao_diaria():
    canal = bot.get_channel(ID_CANAL_NOTIFICACOES)
    if canal:
        hoje_data = datetime.now(timezone.utc).date()
        await gerar_agenda_data(canal, hoje_data, "Hoje")

# ================= COMANDOS =================

@bot.command()
async def hoje(ctx):
    await gerar_agenda_data(ctx, datetime.now(timezone.utc).date(), "Hoje")

@bot.command()
async def amanha(ctx):
    amanha_data = (datetime.now(timezone.utc) + timedelta(days=1)).date()
    await gerar_agenda_data(ctx, amanha_data, "Amanhã")

@bot.command()
async def champions(ctx):
    await gerar_agenda_data(ctx, None, "Próximos Jogos: UEFA Champions League", filtrar_liga="Champions")

@bot.command()
async def premier(ctx):
    await gerar_agenda_data(ctx, None, "Próximos Jogos: Premier League", filtro_lista=EQUIPAS_PREMIER, filtrar_liga="Premier")

@bot.command(aliases=['ligaportugal'])
async def liga(ctx):
    await gerar_agenda_data(ctx, None, "Próximos Jogos: Liga Portugal", filtro_lista=EQUIPAS_LIGA, filtrar_liga="Portugal")

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha` (Cria eventos automaticamente)", inline=False)
    embed.add_field(name="🏆 Competições", value="`!liga`, `!premier`, `!champions`", inline=False)
    embed.add_field(name="⚽ Equipas", value=", ".join([f"!{k}" for k in EQUIPAS.keys()]), inline=False)
    await ctx.send(embed=embed)

async def cmd_equipa(ctx, chave):
    info = EQUIPAS[chave]
    print(f"💬 [COMANDO] !{chave} usado por {ctx.author}.")
    eventos = buscar_jogos_sofasport(info["id"], info["nome"])
    if not eventos: return await ctx.send(f"📅 Sem jogos para {info['nome']}.")
    
    embed = discord.Embed(title=f"🥅 Agenda: {info['nome']}", color=info["cor"])
    for j in eventos[:3]:
        ts = j.get("startTimestamp")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_f = dt.strftime('%d/%m %H:%M') if not (dt.hour == 12 and dt.minute == 0) else dt.strftime('%d/%m (TBD)')
        embed.add_field(name=f"🏆 {j.get('tournament', {}).get('name')}", value=f"📅 `{dt_f}`\n**{j['homeTeam']['name']}** vs **{j['awayTeam']['name']}**", inline=False)
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
async def psg(ctx): await cmd_equipa(ctx, "psg")
@bot.command()
async def bayern(ctx): await cmd_equipa(ctx, "bayern")
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
async def portugal(ctx): await cmd_equipa(ctx, "portugal")

@bot.event
async def on_ready():
    print(f'✅ [SISTEMA] Bot Online: {bot.user}')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)