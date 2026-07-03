import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from datetime import datetime, timedelta, time, timezone
import os
import time as time_module
import re
import csv
import unicodedata

# ================= CONFIGURAÇÕES =================
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')

ID_CANAL_NOTIFICACOES = 1501014726111395850
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

OFFSET_PT = timedelta(hours=1)
CACHE_EXPIRY = 300 
cache_jogos = {}

MUNDIAL_DEMO = [
    {"grupo": "A", "fase": "J1", "data": "11/06/2026", "dia": "Quinta", "hora": "20:00", "jogo": "México x África do Sul", "canal": "RTP 1 / LiveModeTV"}
]

SELECOES_MUNDIAL = {
    "portugal": "Portugal", "espanha": "Espanha", "franca": "França", "frança": "França",
    "brasil": "Brasil", "argentina": "Argentina", "alemanha": "Alemanha", "inglaterra": "Inglaterra",
    "italia": "Itália", "itália": "Itália", "belgica": "Bélgica", "bélgica": "Bélgica",
    "holanda": "Países Baixos", "paises_baixos": "Países Baixos", "croacia": "Croácia", "croácia": "Croácia",
    "suica": "Suíça", "suíça": "Suíça", "uruguai": "Uruguai", "colombia": "Colômbia", "colômbia": "Colômbia",
    "equador": "Equador", "usa": "Estados Unidos", "eua": "Estados Unidos", "mexico": "México",
    "méxico": "México", "canada": "Canadá", "canadá": "Canadá", "marrocos": "Marrocos",
    "senegal": "Senegal", "japao": "Japão", "japão": "Japão", "coreia": "Coreia do Sul",
    "coreia_do_sul": "Coreia do Sul", "australia": "Austrália", "austrália": "Austrália", "arabia": "Arábia Saudita",
    "arabia_saudita": "Arábia Saudita", "arábia_saudita": "Arábia Saudita", "camaroes": "Camarões",
    "camarões": "Camarões", "nigeria": "Nigéria", "nigéria": "Nigéria", "egito": "Egito",
    "argelia": "Argélia", "argélia": "Argélia", "tunisia": "Tunísia", "tunísia": "Tunísia",
    "costa_rica": "Costa Rica", "jamaica": "Jamaica", "nova_zelandia": "Nova Zelândia",
    "nova_zelândia": "Nova Zelândia", "catar": "Catar", "irao": "Irão", "irão": "Irão",
    "chequia": "Chéquia", "chéquia": "Chéquia", "polonia": "Polónia", "polónia": "Polónia",
    "turquia": "Turquia", "austria": "Áustria", "áustria": "Áustria", "dinamarca": "Dinamarca",
    "suecia": "Suécia", "suécia": "Suécia", "ucrania": "Ucrânia", "ucrânia": "Ucrânia",
    "paraguai": "Paraguai", "chile": "Chile", "peru": "Peru", "venezuela": "Venezuela",
    "gana": "Gana", "africa_do_sul": "África do Sul", "áfrica_do_sul": "África do Sul",
    "haiti": "Haiti", "escocia": "Escócia", "escócia": "Escócia",
    "curacau": "Curaçau", "curaçau": "Curaçau",
    "costa_do_marfim": "Costa do Marfim", "rd_congo": "RD Congo", "rdcongo": "RD Congo", "dr_congo": "RD Congo",
    "uzbequistao": "Uzbequistão", "uzbequistão": "Uzbequistão",
    "iraque": "Iraque", "eslovaquia": "Eslováquia", "eslovaquia": "Eslováquia",
    "eslovenia": "Eslovénia", "eslovenia": "Eslovénia", "romenia": "Roménia", "roménia": "Roménia",
    "noruega": "Noruega", "cabo_verde": "Cabo Verde"
}

if not DISCORD_TOKEN:
    print("❌ ERRO: DISCORD_TOKEN não encontrado nas variáveis de ambiente.")
    exit()

api_semaphore = asyncio.Semaphore(1)
intents = discord.Intents.default()
intents.message_content = True
intents.guild_scheduled_events = True 
bot = commands.Bot(command_prefix='!', intents=intents)

HEADERS_API = {
    'x-rapidapi-host': "sofasport.p.rapidapi.com",
    'x-rapidapi-key': API_KEY
}

def carregar_mundial_csv():
    caminho_csv = "mundial.csv"
    if not os.path.exists(caminho_csv):
        return MUNDIAL_DEMO
    jogos = []
    current_group = None
    try:
        with open(caminho_csv, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                row = [cell.strip() for cell in row]
                if not any(row): continue
                grupo_encontrado = False
                for cell in row:
                    if not cell: continue
                    m = re.search(r'GRUPO\s+([A-L])', cell, re.IGNORECASE)
                    if m:
                        current_group = m.group(1).upper()
                        grupo_encontrado = True
                        break
                if grupo_encontrado: continue
                row = row + [""] * (9 - len(row))
                if current_group and len(row) >= 5:
                    data_str = row[1]
                    if re.match(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', data_str):
                        jogo_str = row[4]
                        golos_casa = int(row[5]) if row[5] != "" and row[5].isdigit() else None
                        golos_fora = int(row[7]) if row[7] != "" and row[7].isdigit() else None
                        canal_str = row[8] if row[8] else "Por definir"
                        jogos.append({
                            "grupo": current_group, "fase": row[0], "data": data_str, "dia": row[2], "hora": row[3],
                            "jogo": jogo_str, "golos_casa": golos_casa, "golos_fora": golos_fora, "canal": canal_str, "is_ko": False
                        })
        return jogos
    except Exception as e:
        print(f"❌ Erro ao carregar mundial.csv: {e}")
        return MUNDIAL_DEMO

def carregar_eliminatorias_csv():
    caminho_csv = "mundial_fase_eliminatoria.csv"
    if not os.path.exists(caminho_csv):
        return []
    jogos = []
    try:
        with open(caminho_csv, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                row = [cell.strip() for cell in row]
                if not any(row): continue
                
                # Garantia absoluta: blinda o bot expandindo qualquer linha para no mínimo 10 colunas
                row = row + [""] * (10 - len(row))
                
                fase, num_jogo, data_str = row[0], row[1], row[2]
                if not re.match(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', data_str):
                    continue
                dia, hora, jogo_str = row[3], row[4] if row[4] else "TBD", row[5]
                golos_casa = int(row[6]) if row[6] != "" and row[6].isdigit() else None
                golos_fora = int(row[8]) if row[8] != "" and row[8].isdigit() else None
                estadio_canal = row[9] if row[9] else "A definir"
                jogos.append({
                    "grupo": "KO", "fase": fase, "num_jogo": num_jogo, "data": data_str, "dia": dia, "hora": hora,
                    "jogo": jogo_str, "golos_casa": golos_casa, "golos_fora": golos_fora, "canal": estadio_canal, "is_ko": True
                })
        return jogos
    except Exception as e:
        print(f"❌ Erro ao carregar mundial_fase_eliminatoria.csv: {e}")
        return []

def carregar_calendario_hibrido():
    return carregar_mundial_csv() + carregar_eliminatorias_csv()

def traduzir_nome_equipa(nome):
    traducoes = {
        "South Africa": "África do Sul", "Czechia": "Chéquia", "Czech Republic": "Chéquia",
        "South Korea": "Coreia do Sul", "Korea Republic": "Coreia do Sul", "Saudi Arabia": "Arábia Saudita",
        "Switzerland": "Suíça", "Canada": "Canadá", "Germany": "Alemanha", "Spain": "Espanha",
        "France": "França", "Belgium": "Bélgica", "England": "Inglaterra", "Morocco": "Marrocos",
        "Cameroon": "Camarões", "Croatia": "Croácia", "Brazil": "Brasil", "USA": "Estados Unidos",
        "United States": "Estados Unidos", "Netherlands": "Países Baixos", "Iran": "Irão", "Japan": "Japão",
        "Poland": "Polónia", "Turkey": "Turquia", "Austria": "Áustria", "Ukraine": "Ucrânia", "Italy": "Itália",
        "Scotland": "Escócia", "Paraguay": "Paraguai", "Ivory Coast": "Costa do Marfim", "Egypt": "Egito",
        "New Zealand": "Nova Zelândia", "Uruguay": "Uruguai", "DR Congo": "RD Congo", "Haiti": "Haiti",
        "Ecuador": "Equador", "Colombia": "Colômbia", "Algeria": "Argélia", "Tunisia": "Tunísia",
        "Sweden": "Suécia", "Denmark": "Dinamarca", "Ghana": "Gana", "Uzbekistan": "Uzbequistão",
        "Norway": "Noruega", "Cape Verde": "Cabo Verde"
    }
    for k, v in traducoes.items():
        if k.lower() == nome.lower(): return v
    return nome

def simplificar_nome_busca(nome):
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn').lower()
    traducoes_busca = {
        "coreia": "south korea", "alemanha": "germany", "espanha": "spain", "franca": "france", "frança": "france",
        "belgica": "belgium", "bélgica": "belgium", "inglaterra": "england", "suica": "switzerland", "suíça": "switzerland",
        "suecia": "sweden", "suécia": "sweden", "marrocos": "morocco", "brasil": "brazil", "estados unidos": "usa", "eua": "usa",
        "holanda": "netherlands", "paises baixos": "netherlands", "países baixos": "netherlands", "japao": "japan", "japão": "japan",
        "paraguai": "paraguay", "curacau": "curacao", "curaçau": "curacao", "costa do marfim": "ivory coast", "egito": "egypt",
        "uruguai": "uruguay", "equador": "ecuador", "colombia": "colombia", "colômbia": "colombia", "tunisia": "tunisia",
        "noruega": "norway", "cabo verde": "cape verde", "cabo_verde": "cape verde", "gana": "ghana"
    }
    for k, v in traducoes_busca.items(): nome = nome.replace(k, v)
    return nome.strip()

def equipas_correspondem(csv_casa, csv_fora, api_casa, api_fora):
    c_casa, c_fora = simplificar_nome_busca(csv_casa), simplificar_nome_busca(csv_fora)
    a_casa, a_fora = simplificar_nome_busca(api_casa), simplificar_nome_busca(api_fora)
    return ((c_casa == a_casa or c_casa in a_casa or a_casa in c_casa) and (c_fora == a_fora or c_fora in a_fora or a_fora in c_fora)) or \
           ((c_casa == a_fora or c_casa in a_fora or a_fora in c_casa) and (c_fora == a_casa or c_fora in a_casa or a_casa in c_fora))

def equipa_no_jogo(nome_selecao, jogo_csv):
    partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', jogo_csv)]
    if len(partes) != 2: return False
    s_sel = simplificar_nome_busca(nome_selecao)
    return s_sel in simplificar_nome_busca(partes[0]) or s_sel in simplificar_nome_busca(partes[1])

async def obter_season_id(session):
    url = "https://sofasport.p.rapidapi.com/v1/unique-tournaments/seasons"
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params={"unique_tournament_id": "16"}, timeout=10) as r:
                if r.status == 200:
                    res = await r.json()
                    for s in res.get("data", []):
                        if "2026" in s.get("name", "") or s.get("year") == "2026": return s.get("id", 52561)
        except: pass
    return 52561

async def obter_resultados_api(session, season_id):
    agora = time_module.time()
    if "api_events" in cache_jogos and agora - cache_jogos["api_events"]["timestamp"] < CACHE_EXPIRY:
        return cache_jogos["api_events"]["data"]
    url = "https://sofasport.p.rapidapi.com/v1/seasons/events"
    async def fetch(course):
        try:
            async with session.get(url, headers=HEADERS_API, params={"seasons_id": str(season_id), "unique_tournament_id": "16", "course_events": course, "page": "0"}, timeout=12) as r:
                if r.status == 200:
                    res = await r.json()
                    return res.get("data", []) or res.get("events", []) or []
        except: pass
        return []
    l_events, n_events = await asyncio.gather(fetch("last"), fetch("next"))
    completos = []
    vistos = set()
    for ev in (l_events + n_events):
        if isinstance(ev, dict) and ev.get("id") and ev.get("id") not in vistos:
            vistos.add(ev["id"])
            completos.append(ev)
    cache_jogos["api_events"] = {"data": completos, "timestamp": agora}
    return completos

async def obter_incidentes_api(session, event_id):
    url = "https://sofasport.p.rapidapi.com/v1/events/incidents"
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params={"event_id": str(event_id)}, timeout=10) as r:
                if r.status == 200:
                    res = await r.json()
                    return res.get("data", []) or res.get("incidents", []) or []
        except: pass
    return []

async def obter_tabela_api(session, season_id, letra_grupo):
    url = "https://sofasport.p.rapidapi.com/v1/seasons/standings"
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params={"seasons_id": str(season_id), "unique_tournament_id": "16", "standing_type": "total"}, timeout=15) as r:
                if r.status == 200:
                    res = await r.json()
                    for g in res.get("data", []):
                        if f"GROUP {letra_grupo.upper()}" in g.get("name", "").upper(): return g
        except: pass
    return None

async def gerar_agenda_data(canal_ou_ctx, data_alvo_pt, titulo):
    embed = discord.Embed(title=f"🏆 {titulo}", color=0xe67e22)
    data_str = data_alvo_pt.strftime("%d/%m/%Y")
    jogos = [j for j in carregar_calendario_hibrido() if j["data"] == data_str]
    if not jogos:
        return await canal_ou_ctx.send(f"📅 Sem jogos do Mundial agendados para {titulo}.")
        
    async with aiohttp.ClientSession() as session:
        sid = await obter_season_id(session)
        events = await obter_resultados_api(session, sid)
        for j in jogos:
            partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', j["jogo"])]
            score = f"**{partes[0]}** vs **{partes[1]}**" if len(partes) == 2 else j["jogo"]
            if len(partes) == 2:
                for ev in events:
                    if equipas_correspondem(partes[0], partes[1], ev.get("homeTeam", {}).get("name", ""), ev.get("awayTeam", {}).get("name", "")):
                        gc, gf = ev.get("homeScore", {}).get("current"), ev.get("awayScore", {}).get("current")
                        if gc is not None:
                            status = "🟢" if ev.get("status", {}).get("type") == "inprogress" else "🔴"
                            score = f"**{partes[0]} [{gc}]** vs **{partes[1]} [{gf}]** {status}"
                        break
            name_f = f"🏆 {j['fase']}" if j['is_ko'] else f"🥅 Grupo {j['grupo']} — {j['fase']}"
            embed.add_field(name=name_f, value=f"🕒 **{j['hora']}** | 📺 **{j['canal']}**\n⚔️ {score}", inline=False)
    await canal_ou_ctx.send(embed=embed)

@bot.command(aliases=['faseeliminar', 'eliminatorias', 'esquema', 'fases'])
async def bracket(ctx, *, fase_filtro: str = None):
    await ctx.send("🔍 A carregar a árvore das eliminatórias...")
    jogos_ko = carregar_eliminatorias_csv()
    if not jogos_ko: return await ctx.send("ℹ️ Não foram encontrados jogos das eliminatórias.")
    
    categorias = {"32 avos de final": [], "Oitavos de final": [], "Quartos de final": [], "Meias-finais": [], "Final": []}
    for j in jogos_ko:
        cat = j["fase"].strip().lower()
        if "32" in cat or "1/16" in cat: c_key = "32 avos de final"
        elif "oitav" in cat or "1/8" in cat or "16" in cat: c_key = "Oitavos de final"
        elif "quart" in cat or "1/4" in cat or "qf" in cat: c_key = "Quartos de final"
        elif "meia" in cat or "1/2" in cat or "sf" in cat: c_key = "Meias-finais"
        else: c_key = "Final"
        categorias[c_key].append(j)
        
    fase_alvo = "32 avos de final"
    if fase_filtro:
        f_filt = simplificar_nome_busca(fase_filtro)
        if "32" in f_filt: fase_alvo = "32 avos de final"
        elif "oit" in f_filt: fase_alvo = "Oitavos de final"
        elif "qua" in f_filt: fase_alvo = "Quartos de final"
        elif "mei" in f_filt: fase_alvo = "Meias-finais"
        elif "fin" in f_filt: fase_alvo = "Final"
    else:
        for f_nome in ["32 avos de final", "Oitavos de final", "Quartos de final", "Meias-finais", "Final"]:
            if any(j.get("golos_casa") is None for j in categorias[f_nome]):
                fase_alvo = f_nome
                break

    jogos_fase = categorias[fase_alvo]
    embed = discord.Embed(title=f"🏆 Árvore do Mundial — {fase_alvo.upper()}", color=0xe74c3c)
    
    async with aiohttp.ClientSession() as session:
        sid = await obter_season_id(session)
        events = await obter_resultados_api(session, sid)
        linhas = []
        for j in jogos_fase:
            partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', j["jogo"])]
            jogo_f = j["jogo"]
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                gc, gf = j.get("golos_casa"), j.get("golos_fora")
                for ev in events:
                    if equipas_correspondem(casa, fora, ev.get("homeTeam", {}).get("name", ""), ev.get("awayTeam", {}).get("name", "")):
                        api_gc, api_gf = ev.get("homeScore", {}).get("current"), ev.get("awayScore", {}).get("current")
                        if api_gc is not None: gc, gf = api_gc, api_gf
                        break
                jogo_f = f"**{casa} [{gc}]** vs **{fora} [{gf}]**" if gc is not None else f"**{casa}** vs **{fora}**"
            linhas.append(f"📌 **{j['num_jogo']}** ({j['data']} @ {j['hora']})\n🏟️ {j['canal']}\n⚔️ {jogo_f}\n")
            
        chunk_size = 8
        for i in range(0, len(linhas), chunk_size):
            chunk_texto = "".join(linhas[i:i+chunk_size])
            embed.add_field(name="⚽ Confrontos" if i==0 else "⚽ Confrontos (Cont.)", value=chunk_texto, inline=False)
            
    await ctx.send(embed=embed)

@bot.command()
async def hoje(ctx): await gerar_agenda_data(ctx, (datetime.now(timezone.utc) + OFFSET_PT).date(), "Mundial 2026 — Jogos de Hoje")

@bot.command()
async def amanha(ctx): await gerar_agenda_data(ctx, (datetime.now(timezone.utc) + OFFSET_PT + timedelta(days=1)).date(), "Mundial 2026 — Jogos de Amanhã")

@bot.event
async def on_ready(): print(f'✅ Bot Mundial 2026 Online!')

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)