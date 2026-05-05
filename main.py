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
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado.")
    exit()

ID_CANAL_NOTIFICACOES = int(ID_CANAL_NOTIFICACOES_STR)

# Lista de IDs para filtragem rápida
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

# Criar um set de IDs para busca ultra-rápida
IDS_AUTORIZADOS = {info["id"] for info in EQUIPAS.values()}

intents = discord.Intents.default()
intents.message_content = True
intents.guild_scheduled_events = True 
bot = commands.Bot(command_prefix='!', intents=intents)

HEADERS = {
    'x-rapidapi-host': "sofascore6.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

# ================= FUNÇÕES DE EVENTOS DO DISCORD =================

async def criar_evento_discord(guild, nome_jogo, data_inicio, liga):
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

        if canal_voz:
            await guild.create_scheduled_event(
                name=nome_jogo,
                description=f"🏆 {liga} - Vamos comentar no canal de voz!",
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
                location="Televisão",
                privacy_level=discord.PrivacyLevel.guild_only
            )
        print(f"✅ [SISTEMA] Evento criado: {nome_jogo}")
        return True
    except Exception as e:
        print(f"❌ [ERRO EVENTO] {e}")
        return False

# ================= FUNÇÕES DE API =================

def buscar_agenda_dia(data_str):
    """
    Usa o novo endpoint: /match/list?date=YYYY-MM-DD
    Fabuloso para evitar Rate Limits!
    """
    url = "https://sofascore6.p.rapidapi.com/api/sofascore/v1/match/list"
    params = {"date": data_str, "sport_slug": "football"}
    print(f"🌐 [API] A consultar todos os jogos do dia: {data_str}")
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code == 200:
            return r.json().get("events", [])
        print(f"⚠️ [API] Erro {r.status_code} na agenda diária.")
        return []
    except Exception as e:
        print(f"❌ [API] Falha crítica: {e}")
        return []

def buscar_jogos_equipa(team_id):
    """Usado apenas para comandos individuais (ex: !benfica)"""
    url = "https://sofascore6.p.rapidapi.com/api/sofascore/v1/team/events"
    params = {"id": str(team_id)}
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        return r.json().get("events", []) if r.status_code == 200 else []
    except:
        return []

# ================= AGENDAS E TAREFAS =================

async def processar_agenda(canal_ou_ctx, data_obj, titulo):
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🔍 A consultar agenda para {titulo}...")
    
    data_str = data_obj.strftime('%Y-%m-%d')
    eventos_dia = buscar_agenda_dia(data_str)
    
    if not eventos_dia:
        aviso = f"📅 Não foram encontrados jogos na API para {titulo}."
        if msg: await msg.edit(content=aviso)
        else: await canal_ou_ctx.send(aviso)
        return

    embed = discord.Embed(title=f"⚽ Agenda: {titulo}", color=0xf1c40f)
    encontrou = False
    
    for j in eventos_dia:
        home_id = j.get("homeTeam", {}).get("id")
        away_id = j.get("awayTeam", {}).get("id")
        
        # Verifica se alguma das nossas equipas está a jogar (como Visitado ou Visitante)
        if home_id in IDS_AUTORIZADOS or away_id in IDS_AUTORIZADOS:
            encontrou = True
            ts = j.get("startTimestamp")
            dt_jogo = datetime.fromtimestamp(ts, tz=timezone.utc)
            
            home_name = j.get("homeTeam", {}).get("name", "N/A")
            away_name = j.get("awayTeam", {}).get("name", "N/A")
            liga = j.get("tournament", {}).get("name", "Competição")
            nome_jogo = f"{home_name} vs {away_name}"

            # Criar evento automático
            if canal_ou_ctx.guild:
                await criar_evento_discord(canal_ou_ctx.guild, nome_jogo, dt_jogo, liga)

            hora_f = dt_jogo.strftime('%H:%M') if not (dt_jogo.hour == 12 and dt_jogo.minute == 0) else "TBD"
            
            embed.add_field(
                name=f"🥅 {nome_jogo}",
                value=f"🏆 {liga}\n🕒 **{hora_f}**",
                inline=False
            )

    if not encontrou:
        aviso = f"📅 Nenhuma das tuas equipas joga em {titulo}."
        if msg: await msg.edit(content=aviso)
        else: await canal_ou_ctx.send(aviso)
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

@tasks.loop(time=time(hour=9, minute=0, tzinfo=timezone.utc))
async def notificacao_diaria():
    canal = bot.get_channel(ID_CANAL_NOTIFICACOES)
    if canal:
        await processar_agenda(canal, datetime.now(timezone.utc).date(), "Hoje")

# ================= COMANDOS =================

@bot.command()
async def hoje(ctx):
    await processar_agenda(ctx, datetime.now(timezone.utc).date(), "Hoje")

@bot.command()
async def amanha(ctx):
    amanha_dt = datetime.now(timezone.utc).date() + timedelta(days=1)
    await processar_agenda(ctx, amanha_dt, "Amanhã")

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha` (Rápido e sem erros)", inline=False)
    embed.add_field(name="⚽ Equipas", value="Ex: `!benfica`, `!porto`, `!psg`", inline=False)
    await ctx.send(embed=embed)

async def cmd_equipa(ctx, chave):
    info = EQUIPAS[chave]
    await ctx.send(f"🔍 A consultar próximos jogos de **{info['nome']}**...")
    eventos = buscar_jogos_equipa(info["id"])
    if not eventos: return await ctx.send(f"📅 Sem jogos agendados.")
    
    embed = discord.Embed(title=f"🥅 Agenda: {info['nome']}", color=info["cor"])
    for j in eventos[:3]:
        ts = j.get("startTimestamp")
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        hora = dt.strftime('%d/%m %H:%M') if not (dt.hour == 12 and dt.minute == 0) else dt.strftime('%d/%m (TBD)')
        embed.add_field(name=f"🏆 {j.get('tournament',{}).get('name')}", value=f"🕒 {hora}\n**{j['homeTeam']['name']}** vs **{j['awayTeam']['name']}**", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def benfica(ctx): await cmd_equipa(ctx, "benfica")
@bot.command()
async def porto(ctx): await cmd_equipa(ctx, "porto")
@bot.command()
async def sporting(ctx): await cmd_equipa(ctx, "sporting")
@bot.command()
async def psg(ctx): await cmd_equipa(ctx, "psg")
@bot.command()
async def bayern(ctx): await cmd_equipa(ctx, "bayern")
@bot.command()
async def realmadrid(ctx): await cmd_equipa(ctx, "realmadrid")

@bot.event
async def on_ready():
    print(f'✅ [SISTEMA] Bot Online com Agenda Otimizada: {bot.user}')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)