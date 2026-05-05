import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime, timedelta, time, timezone
import asyncio
import os

# ================= CONFIGURAÇÕES =================
DISCORD_TOKEN = os.os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')
ID_CANAL_STR = os.getenv('ID_CANAL_NOTIFICACOES', '1501014726111395850')

# ID do canal de voz associado aos eventos (ID fornecido: 813485447719813207)
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

# SEGURANÇA: Servidores autorizados (Opcional)
ALLOWED_GUILDS_STR = os.getenv('ALLOWED_GUILDS', '') 
ALLOWED_GUILDS = [int(g.strip()) for g in ALLOWED_GUILDS_STR.split(',') if g.strip().isdigit()]

if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado.")
    exit()

ID_CANAL_NOTIFICACOES = int(ID_CANAL_STR)

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

HEADERS = {
    'x-rapidapi-host': "sofasport.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

# ================= FILTRO DE PRIVACIDADE =================

@bot.check
async def is_guild_allowed(ctx):
    if not ALLOWED_GUILDS: return True
    return ctx.guild and ctx.guild.id in ALLOWED_GUILDS

# ================= FUNÇÕES DE EVENTOS DO DISCORD =================

async def criar_evento_discord(guild, nome_jogo, data_inicio, liga):
    """Cria um evento agendado no servidor num canal de voz ou externo"""
    if data_inicio.tzinfo is None:
        data_inicio = data_inicio.replace(tzinfo=timezone.utc)

    agora = datetime.now(timezone.utc)
    
    if data_inicio < agora:
        print(f"ℹ️ [EVENTO] Ignorado {nome_jogo}: O jogo já passou.")
        return False
        
    if data_inicio.hour == 12 and data_inicio.minute == 0:
        print(f"ℹ️ [EVENTO] Ignorado {nome_jogo}: Hora TBD (12h UTC).")
        return False

    try:
        # Verifica se já existe um evento para este jogo no mesmo dia
        eventos_atuais = await guild.fetch_scheduled_events()
        for e in eventos_atuais:
            if e.name == nome_jogo and e.start_time.date() == data_inicio.date():
                print(f"ℹ️ [EVENTO] Ignorado {nome_jogo}: Evento já existe.")
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
        print(f"✅ [EVENTO] Criado: {nome_jogo}")
        return True
    except Exception as e:
        print(f"❌ [ERRO] Falha ao criar evento {nome_jogo}: {e}")
        return False

# ================= FUNÇÕES DE API =================

def buscar_jogos_sofasport(team_id, nome_equipa="Equipa"):
    url = "https://sofasport.p.rapidapi.com/v1/teams/events"
    params = {"team_id": str(team_id), "course_events": "next", "page": "0"}
    print(f"🌐 [API] A consultar: {nome_equipa}")
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            return r.json().get("data", {}).get("events", [])
        print(f"⚠️ [API] Erro {r.status_code} para {nome_equipa}")
        return []
    except Exception as e:
        print(f"❌ [API] Erro de conexão: {e}")
        return []

# ================= AGENDAS E TAREFAS =================

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo):
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🔍 A consultar a agenda para {titulo}...")
    
    print(f"📅 [AGENDA] A iniciar: {data_alvo} ({titulo})")
    embed = discord.Embed(title=f"⚽ Agenda: {titulo}", color=0xf1c40f)
    encontrou = False
    
    for chave, info in EQUIPAS.items():
        eventos = buscar_jogos_sofasport(info["id"], info["nome"])
        for j in eventos:
            ts = j.get("startTimestamp")
            if ts:
                dt_jogo = datetime.fromtimestamp(ts, tz=timezone.utc)
                if dt_jogo.date() == data_alvo:
                    encontrou = True
                    home = j.get("homeTeam", {}).get("name", "N/A")
                    away = j.get("awayTeam", {}).get("name", "N/A")
                    liga_nome = j.get("tournament", {}).get("name", "Competição")
                    nome_jogo = f"{home} vs {away}"

                    if canal_ou_ctx.guild:
                        await criar_evento_discord(canal_ou_ctx.guild, nome_jogo, dt_jogo, liga_nome)

                    hora_f = dt_jogo.strftime('%H:%M') if not (dt_jogo.hour == 12 and dt_jogo.minute == 0) else dt_jogo.strftime('%d/%m (TBD)')
                    embed.add_field(name=f"🥅 {info['nome']}", value=f"🏆 {liga_nome}\n🕒 **{hora_f}**\n**{home}** vs **{away}**", inline=False)
                    break 
        await asyncio.sleep(0.5)

    if not encontrou:
        aviso = f"📅 Não foram encontrados jogos para {titulo}."
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
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha` (Cria eventos automaticamente)", inline=False)
    embed.add_field(name="⚽ Equipas", value=", ".join([f"!{k}" for k in EQUIPAS.keys()]), inline=False)
    await ctx.send(embed=embed)

async def cmd_equipa(ctx, chave):
    info = EQUIPAS[chave]
    partidas = buscar_jogos_sofasport(info["id"], info["nome"])
    if not partidas: return await ctx.send(f"📅 Sem jogos para {info['nome']}.")
    embed = discord.Embed(title=f"🥅 Agenda: {info['nome']}", color=info["cor"])
    for j in partidas[:3]:
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
async def realmadrid(ctx): await cmd_equipa(ctx, "realmadrid")
@bot.command()
async def barcelona(ctx): await cmd_equipa(ctx, "barcelona")

@bot.event
async def on_ready():
    print(f'✅ [SISTEMA] Bot Online: {bot.user}')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)