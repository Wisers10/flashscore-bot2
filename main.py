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

if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado.")
    exit()

ID_CANAL_NOTIFICACOES = int(ID_CANAL_STR)

# Semáforo para limitar pedidos simultâneos (Evita erro 429 da API)
# Permite apenas 5 pedidos ao mesmo tempo
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

intents = discord.Intents.default()
intents.message_content = True
intents.guild_scheduled_events = True 
bot = commands.Bot(command_prefix='!', intents=intents)

HEADERS = {
    'x-rapidapi-host': "sofasport.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

# ================= FUNÇÕES DE APOIO ASSÍNCRONAS =================

async def buscar_jogos_async(session, team_id):
    """Busca eventos usando um semáforo para não sobrecarregar a API"""
    url = "https://sofasport.p.rapidapi.com/v1/teams/events"
    params = {"team_id": str(team_id), "course_events": "next", "page": "0"}
    
    async with api_semaphore: # Espera a sua vez se já houver 5 pedidos a correr
        try:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("data", {}).get("events", [])
                elif response.status == 429:
                    print(f"⚠️ Rate limit atingido para ID {team_id}. A aguardar...")
                    await asyncio.sleep(2) # Pequena pausa se a API reclamar
                return []
        except Exception as e:
            print(f"Erro ao buscar equipa {team_id}: {e}")
            return []

# ================= FUNÇÕES DE EVENTOS DO DISCORD =================

async def criar_evento_discord(guild, nome_jogo, data_inicio, liga):
    if data_inicio.tzinfo is None:
        data_inicio = data_inicio.replace(tzinfo=timezone.utc)

    agora = datetime.now(timezone.utc)
    if data_inicio < agora or (data_inicio.hour == 12 and data_inicio.minute == 0):
        return

    eventos_atuais = await guild.fetch_scheduled_events()
    for e in eventos_atuais:
        if e.name == nome_jogo and abs((e.start_time - data_inicio).total_seconds()) < 3600:
            return 

    data_fim = data_inicio + timedelta(hours=2)
    canal_voz = guild.get_channel(int(ID_CANAL_VOZ_STR)) if ID_CANAL_VOZ_STR else None

    try:
        if canal_voz:
            await guild.create_scheduled_event(
                name=nome_jogo,
                description=f"🏆 {liga} - Vamos comentar o jogo em direto no canal de voz!",
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
    except Exception as e:
        print(f"❌ Erro ao criar evento {nome_jogo}: {e}")

# ================= SINCRONIZAÇÃO EM MASSA =================

async def sincronizar_todos_os_eventos(guild):
    if not guild: return
    print(f"🔄 Sincronização controlada iniciada para: {guild.name}")
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tarefas = [buscar_jogos_async(session, info["id"]) for info in EQUIPAS.values()]
        resultados = await asyncio.gather(*tarefas)

        for eventos in resultados:
            for j in eventos:
                ts = j.get("startTimestamp")
                if ts:
                    dt_jogo = datetime.fromtimestamp(ts, tz=timezone.utc)
                    home = j.get("homeTeam", {}).get("name", "N/A")
                    away = j.get("awayTeam", {}).get("name", "N/A")
                    liga_nome = j.get("tournament", {}).get("name", "Competição")
                    await criar_evento_discord(guild, f"{home} vs {away}", dt_jogo, liga_nome)

# ================= TAREFAS E COMANDOS =================

@tasks.loop(hours=6)
async def task_sincronizacao_global():
    for guild in bot.guilds:
        await sincronizar_todos_os_eventos(guild)

@tasks.loop(time=time(hour=9, minute=0, tzinfo=timezone.utc))
async def notificacao_diaria():
    canal = bot.get_channel(ID_CANAL_NOTIFICACOES)
    if canal:
        hoje_data = datetime.now(timezone.utc).date()
        await gerar_agenda_data(canal, hoje_data, "Hoje")

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo):
    msg = await canal_ou_ctx.send(f"🚀 A processar agenda para {titulo} (Modo Otimizado)...") if isinstance(canal_ou_ctx, commands.Context) else None
    
    embed = discord.Embed(title=f"⚽ Agenda: {titulo}", color=0xf1c40f)
    encontrou = False
    
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        ids = [info["id"] for info in EQUIPAS.values()]
        nomes = [info["nome"] for info in EQUIPAS.values()]
        tarefas = [buscar_jogos_async(session, team_id) for team_id in ids]
        
        resultados = await asyncio.gather(*tarefas)

        for nome_equipa, eventos in zip(nomes, resultados):
            for j in eventos:
                ts = j.get("startTimestamp")
                if ts:
                    dt_jogo = datetime.fromtimestamp(ts, tz=timezone.utc)
                    if dt_jogo.date() == data_alvo:
                        encontrou = True
                        home = j.get("homeTeam", {}).get("name", "N/A")
                        away = j.get("awayTeam", {}).get("name", "N/A")
                        liga_nome = j.get("tournament", {}).get("name", "Competição")
                        hora_f = dt_jogo.strftime('%H:%M') if not (dt_jogo.hour == 12 and dt_jogo.minute == 0) else dt_jogo.strftime('%d/%m (TBD)')
                        
                        embed.add_field(
                            name=f"🥅 {nome_equipa}",
                            value=f"🏆 {liga_nome}\n🕒 **{hora_f}**\n**{home}** vs **{away}**",
                            inline=False
                        )
                        break

    if not encontrou:
        texto = f"📅 Sem jogos para {titulo}."
        if msg: await msg.edit(content=texto)
        else: await canal_ou_ctx.send(texto)
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

@bot.command()
async def hoje(ctx): await gerar_agenda_data(ctx, datetime.now(timezone.utc).date(), "Hoje")

@bot.command()
async def sincronizar(ctx):
    await ctx.send("🚀 Sincronização segura iniciada...")
    await sincronizar_todos_os_eventos(ctx.guild)
    await ctx.send("✅ Sincronização concluída com sucesso!")

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha`", inline=False)
    embed.add_field(name="🔄 Eventos", value="`!sincronizar` - Atualiza eventos de forma segura.", inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'✅ Bot Online e com Proteção de Rate Limit!')
    if not notificacao_diaria.is_running(): notificacao_diaria.start()
    if not task_sincronizacao_global.is_running(): task_sincronizacao_global.start()
    for guild in bot.guilds: asyncio.create_task(sincronizar_todos_os_eventos(guild))

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)