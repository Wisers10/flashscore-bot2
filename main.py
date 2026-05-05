import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime, timedelta, time, timezone
import asyncio
import os

# ================= CONFIGURAÇÕES =================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')
ID_CANAL_STR = os.getenv('ID_CANAL_NOTIFICACOES', '123456789012345678')

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
intents.guild_scheduled_events = True # NOVA INTENT NECESSÁRIA
bot = commands.Bot(command_prefix='!', intents=intents)

HEADERS = {
    'x-rapidapi-host': "sofasport.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

# ================= FUNÇÕES DE EVENTOS DO DISCORD =================

async def criar_evento_discord(guild, nome_jogo, data_inicio, liga):
    """Cria um evento agendado no servidor se ele ainda não existir"""
    # Verifica se já existe um evento com o mesmo nome para evitar duplicados
    eventos_atuais = await guild.fetch_scheduled_events()
    for e in eventos_atuais:
        if e.name == nome_jogo and e.start_time.date() == data_inicio.date():
            return # Já existe

    # Define fim do evento (2h depois do início)
    data_fim = data_inicio + timedelta(hours=2)

    try:
        await guild.create_scheduled_event(
            name=nome_jogo,
            description=f"🏆 {liga} - Acompanha o jogo aqui no servidor!",
            start_time=data_inicio,
            end_time=data_fim,
            entity_type=discord.EntityType.external,
            location="Campo de Futebol / TV",
            privacy_level=discord.PrivacyLevel.guild_only
        )
        print(f"✅ Evento criado: {nome_jogo}")
    except Exception as e:
        print(f"❌ Erro ao criar evento: {e}")

# ================= FUNÇÕES DE API =================

def buscar_jogos_sofasport(team_id):
    url = "https://sofasport.p.rapidapi.com/v1/teams/events"
    params = {"team_id": str(team_id), "course_events": "next", "page": "0"}
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if r.status_code == 200:
            return r.json().get("data", {}).get("events", [])
        return []
    except:
        return []

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo, criar_eventos=False):
    msg = None
    guild = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🔍 A consultar a agenda para {titulo}...")
        guild = canal_ou_ctx.guild
    else:
        guild = canal_ou_ctx.guild # No caso da task automática

    embed = discord.Embed(title=f"⚽ Agenda: {titulo}", color=0xf1c40f)
    encontrou = False
    
    for chave, info in EQUIPAS.items():
        eventos = buscar_jogos_sofasport(info["id"])
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

                    # Criação de evento no Discord (se a hora não for TBD/12h00)
                    if criar_eventos and guild and not (dt_jogo.hour == 12 and dt_jogo.minute == 0):
                        await criar_evento_discord(guild, nome_jogo, dt_jogo, liga_nome)

                    if dt_jogo.hour == 12 and dt_jogo.minute == 0:
                        hora_f = dt_jogo.strftime('%d/%m (Hora a definir)')
                    else:
                        hora_f = dt_jogo.strftime('%H:%M')
                    
                    embed.add_field(
                        name=f"🥅 {info['nome']}",
                        value=f"🏆 {liga_nome}\n🕒 **{hora_f}**\n**{home}** vs **{away}**",
                        inline=False
                    )
                    break
        await asyncio.sleep(0.4)

    if not encontrou:
        if msg: await msg.edit(content=f"📅 Não foram encontrados jogos das tuas equipas para {titulo}.")
    else:
        if msg: await msg.edit(content=None, embed=embed)
        else: await canal_ou_ctx.send(embed=embed)

# ================= TAREFAS E COMANDOS =================

@tasks.loop(time=time(hour=9, minute=0, tzinfo=timezone.utc))
async def notificacao_diaria():
    canal = bot.get_channel(ID_CANAL_NOTIFICACOES)
    if canal:
        hoje_data = datetime.now(timezone.utc).date()
        # Aqui ativamos o criar_eventos=True
        await gerar_agenda_data(canal, hoje_data, "Hoje", criar_eventos=True)

@bot.command()
async def hoje(ctx):
    await gerar_agenda_data(ctx, datetime.now(timezone.utc).date(), "Hoje", criar_eventos=True)

@bot.command()
async def amanha(ctx):
    await gerar_agenda_data(ctx, (datetime.now(timezone.utc) + timedelta(days=1)).date(), "Amanhã", criar_eventos=True)

# ... (restante dos comandos como !liga e !benfica permanecem iguais)

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha` (Estes criam eventos no Discord)", inline=False)
    embed.add_field(name="🏆 Ligas", value="`!liga`, `!premier`", inline=False)
    embed.add_field(name="⚽ Equipas", value=", ".join([f"!{k}" for k in EQUIPAS.keys()]), inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'✅ Bot Online com suporte a Eventos!')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)