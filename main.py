import discord
from discord.ext import commands, tasks
import requests
from datetime import datetime, timedelta, time, timezone
import asyncio
import os

# ================= CONFIGURAÇÕES DE SEGURANÇA =================
# NUNCA coloques o token diretamente aqui. 
# O bot vai ler o token das "Environment Variables" do teu servidor (Railway/Render/VPS).
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')
ID_CANAL_STR = os.getenv('ID_CANAL_NOTIFICACOES', '123456789012345678')

# Verificação de segurança: O bot para se o Token não estiver configurado no ambiente
if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado nas variáveis de ambiente.")
    exit()

ID_CANAL_NOTIFICACOES = int(ID_CANAL_STR)

# Dicionário de Equipas
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
bot = commands.Bot(command_prefix='!', intents=intents)

HEADERS = {
    'x-rapidapi-host': "sofasport.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

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

async def gerar_agenda_data(canal_ou_ctx, data_alvo, titulo):
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🔍 A consultar a agenda para {titulo}...")
    
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
                    if dt_jogo.hour == 12 and dt_jogo.minute == 0:
                        hora_f = dt_jogo.strftime('%d/%m (Hora a definir)')
                    else:
                        hora_f = dt_jogo.strftime('%H:%M')
                        
                    home = j.get("homeTeam", {}).get("name", "N/A")
                    away = j.get("awayTeam", {}).get("name", "N/A")
                    liga_nome = j.get("tournament", {}).get("name", "Competição")
                    
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
        await gerar_agenda_data(canal, hoje_data, "Hoje")

@bot.command()
async def hoje(ctx):
    await gerar_agenda_data(ctx, datetime.now(timezone.utc).date(), "Hoje")

@bot.command()
async def amanha(ctx):
    await gerar_agenda_data(ctx, (datetime.now(timezone.utc) + timedelta(days=1)).date(), "Amanhã")

@bot.command()
async def premier(ctx):
    msg = await ctx.send("🔍 A procurar jogos da Premier League...")
    embed = discord.Embed(title="🏴󠁧󠁢󠁥󠁮󠁧󠁿 Próximos Jogos: Premier League", color=0x38003C)
    for chave in EQUIPAS_PREMIER:
        info = EQUIPAS[chave]
        partidas = buscar_jogos_sofasport(info["id"])
        jogo = next((j for j in partidas if "premier league" in j.get("tournament", {}).get("name", "").lower()), None)
        if jogo:
            ts = jogo.get("startTimestamp")
            dt_obj = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_f = dt_obj.strftime('%d/%m (Hora a definir)') if (dt_obj.hour == 12 and dt_obj.minute == 0) else dt_obj.strftime('%d/%m %H:%M')
            embed.add_field(name=info["nome"], value=f"📅 `{dt_f}`\n**{jogo['homeTeam']['name']}** vs **{jogo['awayTeam']['name']}**", inline=False)
        else:
            embed.add_field(name=info["nome"], value="📅 Sem jogos agendados.", inline=False)
        await asyncio.sleep(0.4)
    await msg.edit(content=None, embed=embed)

@bot.command(aliases=['ligaportugal'])
async def liga(ctx):
    msg = await ctx.send("🔍 A procurar jogos da Liga Portugal...")
    embed = discord.Embed(title="🇵🇹 Próximos Jogos: Liga Portugal", color=0x006600)
    for chave in EQUIPAS_LIGA:
        info = EQUIPAS[chave]
        partidas = buscar_jogos_sofasport(info["id"])
        jogo = None
        for j in partidas:
            t = j.get("tournament", {})
            if "liga portugal" in t.get("name", "").lower() or t.get("uniqueTournament", {}).get("id") == 238 or t.get("category", {}).get("id") == 44:
                jogo = j
                break
        if jogo:
            ts = jogo.get("startTimestamp")
            dt_obj = datetime.fromtimestamp(ts, tz=timezone.utc)
            dt_f = dt_obj.strftime('%d/%m (Hora a definir)') if (dt_obj.hour == 12 and dt_obj.minute == 0) else dt_obj.strftime('%d/%m %H:%M')
            embed.add_field(name=info["nome"], value=f"📅 `{dt_f}`\n**{jogo['homeTeam']['name']}** vs **{jogo['awayTeam']['name']}**", inline=False)
        else:
            embed.add_field(name=info["nome"], value="📅 Sem jogos agendados.", inline=False)
        await asyncio.sleep(0.4)
    await msg.edit(content=None, embed=embed)

async def comando_equipa(ctx, chave):
    info = EQUIPAS[chave]
    await ctx.send(f"🔍 A consultar a agenda do **{info['nome']}**...")
    partidas = buscar_jogos_sofasport(info["id"])
    if not partidas: return await ctx.send(f"📅 Sem jogos para {info['nome']}.")
    embed = discord.Embed(title=f"🥅 Agenda: {info['nome']}", color=info["cor"])
    for j in partidas[:3]:
        ts = j.get("startTimestamp")
        dt_obj = datetime.fromtimestamp(ts, tz=timezone.utc)
        dt_f = dt_obj.strftime('%d/%m (Hora a definir)') if (dt_obj.hour == 12 and dt_obj.minute == 0) else dt_obj.strftime('%d/%m %H:%M')
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
@bot.command(aliases=['manchesterunited'])
async def manunited(ctx): await comando_equipa(ctx, "manunited")
@bot.command(aliases=['manchestercity'])
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
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos", color=0x3498db)
    embed.add_field(name="⏰ Agendas", value="`!hoje`, `!amanha`", inline=False)
    embed.add_field(name="🏆 Ligas", value="`!liga`, `!premier`", inline=False)
    embed.add_field(name="⚽ Equipas", value=", ".join([f"!{k}" for k in EQUIPAS.keys()]), inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'✅ Bot Online e Seguro!')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)