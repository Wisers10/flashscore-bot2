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
# Chave de API SofaSport da RapidAPI
API_KEY = os.getenv('API_KEY', '6d06a69f23msh5f3ad35148c8b68p1235b8jsnb94b0198382b')

# ID do canal para notificações diárias automáticas à meia-noite
ID_CANAL_NOTIFICACOES = 1501014726111395850
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

# Fuso horário de Portugal Continental (Ajuste de +1 hora sobre o UTC)
OFFSET_PT = timedelta(hours=1)
CACHE_EXPIRY = 300 
cache_jogos = {}

MUNDIAL_DEMO = [
    {"grupo": "A", "fase": "J1", "data": "11/06/2026", "dia": "Quinta", "hora": "20:00", "jogo": "México x África do Sul", "canal": "RTP 1 / LiveModeTV"}
]

# Dicionário completo de atalhos e traduções das seleções participantes
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

# ================= LEITURA DOS FICHEIROS CSV =================

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
                
                # Garantia absoluta de largura de linha contra crashes de IndexError
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

# ================= TRADUÇÕES E NORMALIZAÇÃO DE STRINGS =================

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

# ================= COMUNICAÇÃO ROBUSTA COM A API SOFASPORT =================

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
    """Obtém os resultados do Sofasport de forma robusta e garante que são sempre retornadas listas."""
    agora = time_module.time()
    if "api_events" in cache_jogos and agora - cache_jogos["api_events"]["timestamp"] < CACHE_EXPIRY:
        return cache_jogos["api_events"]["data"]
        
    url = "https://sofasport.p.rapidapi.com/v1/seasons/events"
    
    async def fetch(course):
        try:
            async with session.get(url, headers=HEADERS_API, params={"seasons_id": str(season_id), "unique_tournament_id": "16", "course_events": course, "page": "0"}, timeout=12) as r:
                if r.status == 200:
                    res = await r.json()
                    
                    # Validação de tipo de dados ultra robusta
                    if isinstance(res, list):
                        return res
                    elif isinstance(res, dict):
                        data_val = res.get("data")
                        if isinstance(data_val, list):
                            return data_val
                        elif isinstance(data_val, dict):
                            events_val = data_val.get("events") or data_val.get("rows")
                            if isinstance(events_val, list):
                                return events_val
                        
                        events_val = res.get("events")
                        if isinstance(events_val, list):
                            return events_val
        except Exception as e:
            print(f"⚠️ Erro ao procurar eventos ({course}): {e}")
        return []

    l_events, n_events = await asyncio.gather(fetch("last"), fetch("next"))
    
    # Prevenção absoluta do TypeError de soma de Dicionários
    if not isinstance(l_events, list): l_events = []
    if not isinstance(n_events, list): n_events = []
    
    completos = []
    vistos = set()
    for ev in (l_events + n_events):
        if isinstance(ev, dict) and ev.get("id") and ev.get("id") not in vistos:
            vistos.add(ev["id"])
            completos.append(ev)
            
    cache_jogos["api_events"] = {"data": completos, "timestamp": agora}
    return completos

async def obter_incidentes_api(session, event_id):
    """Descarrega os incidentes do jogo em direto e valida a estrutura da lista."""
    url = "https://sofasport.p.rapidapi.com/v1/events/incidents"
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params={"event_id": str(event_id)}, timeout=10) as r:
                if r.status == 200:
                    res = await r.json()
                    if isinstance(res, list):
                        return res
                    elif isinstance(res, dict):
                        data_val = res.get("data")
                        if isinstance(data_val, list):
                            return data_val
                        elif isinstance(data_val, dict):
                            inc_val = data_val.get("incidents")
                            if isinstance(inc_val, list):
                                return inc_val
                        
                        inc_val = res.get("incidents")
                        if isinstance(inc_val, list):
                            return inc_val
        except: pass
    return []

async def obter_tabela_api(session, season_id, letra_grupo):
    """Obtém a tabela classificativa atualizada do grupo desejado."""
    url = "https://sofasport.p.rapidapi.com/v1/seasons/standings"
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params={"seasons_id": str(season_id), "unique_tournament_id": "16", "standing_type": "total"}, timeout=15) as r:
                if r.status == 200:
                    res = await r.json()
                    standings_list = []
                    if isinstance(res, list):
                        standings_list = res
                    elif isinstance(res, dict):
                        data_val = res.get("data")
                        if isinstance(data_val, list):
                            standings_list = data_val
                        elif isinstance(data_val, dict):
                            standings_list = data_val.get("standings", []) or []
                        else:
                            standings_list = res.get("standings", []) or []
                            
                    if isinstance(standings_list, list):
                        for g in standings_list:
                            if isinstance(g, dict):
                                name_val = g.get("name", "").upper()
                                if f"GROUP {letra_grupo.upper()}" in name_val:
                                    return g
        except: pass
    return None

# ================= CRIAÇÃO DE EVENTOS DO DISCORD =================

async def criar_evento_discord(guild, nome_jogo, data_inicio_utc, liga, tv_info=None):
    data_pt = data_inicio_utc.replace(tzinfo=timezone.utc).astimezone(timezone(OFFSET_PT))
    agora_pt = datetime.now(timezone(OFFSET_PT))
    if data_pt < agora_pt: return False
    
    try:
        eventos_atuais = await guild.fetch_scheduled_events()
        for e in eventos_atuais:
            if e.name == nome_jogo and e.start_time.astimezone(timezone(OFFSET_PT)).date() == data_pt.date(): return False
        
        desc = f"🏆 {liga}\n📺 Transmissão: **{tv_info if tv_info else 'Não listado'}**\n\nVamos comentar o jogo no canal de voz!"
        data_fim = data_pt + timedelta(hours=2)
        canal_voz = guild.get_channel(int(ID_CANAL_VOZ_STR)) if ID_CANAL_VOZ_STR else None
        
        if canal_voz:
            await guild.create_scheduled_event(name=nome_jogo, description=desc, start_time=data_pt, end_time=data_fim, entity_type=discord.EntityType.voice, channel=canal_voz, privacy_level=discord.PrivacyLevel.guild_only)
        else:
            await guild.create_scheduled_event(name=nome_jogo, description=desc, start_time=data_pt, end_time=data_fim, entity_type=discord.EntityType.external, location="Televisão", privacy_level=discord.PrivacyLevel.guild_only)
        return True
    except: return False

# ================= CRIAÇÃO DE AGENDAS E CALENDÁRIO =================

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
            
            # Tenta criar evento agendado automaticamente no servidor do Discord se for guilda
            if canal_ou_ctx.guild and j["hora"] != "TBD":
                try:
                    dia, mes, ano = map(int, j["data"].split('/'))
                    hora_h, hora_m = map(int, j["hora"].split(':'))
                    dt_pt = datetime(ano, mes, dia, hora_h, hora_m, tzinfo=timezone(OFFSET_PT))
                    await criar_evento_discord(canal_ou_ctx.guild, j["jogo"], dt_pt.astimezone(timezone.utc), "Mundial 2026", j["canal"])
                except: pass

    await canal_ou_ctx.send(embed=embed)

async def gerar_agenda_selecao(canal_ou_ctx, nome_selecao):
    jogos_csv = carregar_calendario_hibrido()
    jogos_filtrados = [j for j in jogos_csv if equipa_no_jogo(nome_selecao, j["jogo"])]
    if not jogos_filtrados:
        return await canal_ou_ctx.send(f"⚠️ Não encontrei nenhum jogo agendado para **{nome_selecao}**.")
        
    embed = discord.Embed(title=f"⚽ Calendário: {nome_selecao.upper()}", color=0x3498db)
    async with aiohttp.ClientSession() as session:
        sid = await obter_season_id(session)
        events = await obter_resultados_api(session, sid)
        for j in jogos_filtrados:
            partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', j["jogo"])]
            score = j["jogo"]
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                gc, gf = j.get("golos_casa"), j.get("golos_fora")
                for ev in events:
                    if equipas_correspondem(casa, fora, ev.get("homeTeam", {}).get("name", ""), ev.get("awayTeam", {}).get("name", "")):
                        api_gc, api_gf = ev.get("homeScore", {}).get("current"), ev.get("awayScore", {}).get("current")
                        if api_gc is not None: gc, gf = api_gc, api_gf
                        break
                score = f"**{casa} [{gc}]** vs **{fora} [{gf}]**" if gc is not None else f"**{casa}** vs **{fora}**"
            name_f = f"📅 {j['data']} @ {j['hora']} ({j['fase']})"
            embed.add_field(name=name_f, value=f"📺 Canal/Estádio: **{j['canal']}**\n⚔️ {score}", inline=False)
    await canal_ou_ctx.send(embed=embed)

# ================= COMANDO DE CLASSIFICAÇÃO DE GRUPOS =================

def abreviar_nome(nome, max_len=10):
    nome_tr = traduzir_nome_equipa(nome)
    if len(nome_tr) <= max_len: return nome_tr
    return nome_tr[:max_len-1] + "."

async def processar_comando_grupo(ctx, letra_grupo):
    letra_grupo = letra_grupo.upper()
    await ctx.send(f"📊 A aceder à tabela classificativa para o **Grupo {letra_grupo}**...")
    async with aiohttp.ClientSession() as session:
        sid = await obter_season_id(session)
        tabela = await obter_tabela_api(session, sid, letra_grupo)
        if not tabela:
            return await ctx.send(f"⚠️ Não consegui carregar as classificações atuais para o **Grupo {letra_grupo}**.")
            
        embed = discord.Embed(title=f"🏆 MUNDIAL 2026 — GRUPO {letra_grupo}", color=0x2ecc71)
        linhas = [f" #  {'Equipa':<10} J  V-E-D   DG Pts"]
        linhas.append("────────────────────────────────")
        for idx, r in enumerate(tabela.get("rows", [])):
            nome = abreviar_nome(r.get("team", {}).get("name", "N/A"))
            j = r.get("matches", 0)
            v = r.get("wins", 0)
            e = r.get("draws", 0)
            d = r.get("losses", 0)
            gm = r.get("scoresFor", 0) or r.get("goalsFor", 0)
            gs = r.get("scoresAgainst", 0) or r.get("goalsAgainst", 0)
            dg = gm - gs
            dg_str = f"{dg:+2}" if dg != 0 else " 0"
            linhas.append(f" {idx+1}º {nome:<10} {j:<1}  {v}-{e}-{d:<3} {dg_str:>3} {r.get('points', 0):>3}")
            
        embed.add_field(name="📊 Tabela Clasificativa", value=f"```\n" + "\n".join(linhas) + "\n```", inline=False)
        await ctx.send(embed=embed)

# ================= DETALHES DE JOGO EM DIRETO (INCIDENTES) =================

def obter_codigo_selecao(nome):
    nome_clean = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-zA-Z]', '', nome_clean)[:3].upper()

@bot.command(aliases=['jogo', 'info', 'eventos'])
async def detalhes(ctx, *, equipas: str):
    """Mostra os golos, cartões e substituições de um jogo em tempo real."""
    await ctx.send("🔍 A procurar incidentes e detalhes na API...")
    jogos = carregar_calendario_hibrido()
    match_csv = None
    for j in jogos:
        partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', j["jogo"])]
        if len(partes) == 2 and (simplificar_nome_busca(partes[0]) in simplificar_nome_busca(equipas) or simplificar_nome_busca(partes[1]) in simplificar_nome_busca(equipas)):
            match_csv = j
            break
            
    if not match_csv:
        return await ctx.send("❌ Não encontrei nenhum jogo com essa designação no calendário.")
        
    partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', match_csv["jogo"])]
    casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
    
    async with aiohttp.ClientSession() as session:
        sid = await obter_season_id(session)
        events = await obter_resultados_api(session, sid)
        match_api = None
        for ev in events:
            if equipas_correspondem(casa, fora, ev.get("homeTeam", {}).get("name", ""), ev.get("awayTeam", {}).get("name", "")):
                match_api = ev
                break
                
        if not match_api or not match_api.get("id"):
            return await ctx.send(f"⚠️ Encontrei o jogo **{casa} vs {fora}**, mas ele ainda não se encontra ativo ou com dados no SofaSport.")
            
        incidents = await obter_incidentes_api(session, match_api["id"])
        gc = match_api.get("homeScore", {}).get("current")
        gf = match_api.get("awayScore", {}).get("current")
        status = match_api.get("status", {}).get("description", "Agendado")
        
        embed = discord.Embed(title=f"⚽ Incidentes: {casa} [{gc if gc is not None else 0}] vs [{gf if gf is not None else 0}] {fora}", description=f"🏟️ Estado: **{status}** | 📺 Transmissão: **{match_csv['canal']}**", color=0x2ecc71)
        
        cronologia = []
        cod_casa, cod_fora = obter_codigo_selecao(casa), obter_codigo_selecao(fora)
        
        for inc in sorted(incidents, key=lambda x: x.get("time", 0)):
            inc_type = (inc.get("incidentType") or inc.get("type") or "").lower()
            tempo = f"{inc.get('time', 0)}'"
            if inc.get("addedTime"): tempo = f"{inc.get('time', 0)}+{inc.get('addedTime')}'"
            
            is_home = inc.get("isHome") or inc.get("home") or True
            cod_eq = cod_casa if is_home else cod_fora
            p_name = inc.get("player", {}).get("name", "Jogador") if isinstance(inc.get("player"), dict) else "Jogador"
            
            if inc_type == "goal":
                emoji = "❌" if "owngoal" in str(inc.get("class")).lower() else "⚽"
                cronologia.append(f"`{tempo:<5}` {emoji} **GOLO ({cod_eq})** — {p_name}")
            elif inc_type == "card":
                emoji = "🟥" if "red" in str(inc.get("class")).lower() else "🟨"
                cronologia.append(f"`{tempo:<5}` {emoji} **Cartão ({cod_eq})** — {p_name}")
            elif inc_type == "substitution":
                p_in = inc.get("playerIn", {}).get("name", "Entra")
                p_out = inc.get("playerOut", {}).get("name", "Sai")
                cronologia.append(f"`{tempo:<5}` 🔄 **Subst. ({cod_eq})** — ⬇️ {p_out} | ⬆️ {p_in}")
                
        embed.add_field(name="⏱️ Resumo da Partida", value="\n".join(cronologia) if cronologia else "🏟️ Sem golos ou eventos dignos de registo até ao momento.", inline=False)
        await ctx.send(embed=embed)

# ================= COMANDO DE BRACKET DA FASE A ELIMINAR =================

@bot.command(aliases=['faseeliminar', 'eliminatorias', 'esquema', 'fases'])
async def bracket(ctx, *, fase_filtro: str = None):
    await ctx.send("🔍 A carregar a árvore das eliminatórias...")
    jogos_ko = carregar_eliminatorias_csv()
    if not jogos_ko: return await ctx.send("ℹ️ Não foram encontrados jogos das eliminatórias no ficheiro `mundial_fase_eliminatoria.csv`.")
    
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
        # Autodetação da fase ativa
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

# ================= COMANDOS DO BOT =================

@bot.command()
async def hoje(ctx): 
    await gerar_agenda_data(ctx, (datetime.now(timezone.utc) + OFFSET_PT).date(), "Mundial 2026 — Jogos de Hoje")

@bot.command()
async def amanha(ctx): 
    await gerar_agenda_data(ctx, (datetime.now(timezone.utc) + OFFSET_PT + timedelta(days=1)).date(), "Mundial 2026 — Jogos de Amanhã")

@bot.command()
async def mundial(ctx, data_pesquisa: str = None):
    """Mostra os jogos de uma data específica (Ex: !mundial 11/06/2026)"""
    if data_pesquisa:
        try:
            dt = datetime.strptime(data_pesquisa, "%d/%m/%Y").date()
            await gerar_agenda_data(ctx, dt, f"Mundial 2026 — Agenda de {data_pesquisa}")
        except ValueError:
            await ctx.send("❌ Formato inválido. Usa: `DD/MM/AAAA` (Ex: `!mundial 11/06/2026`)")
    else:
        await gerar_agenda_data(ctx, (datetime.now(timezone.utc) + OFFSET_PT).date(), "Mundial 2026 — Jogos de Hoje")

@bot.command()
async def selecao(ctx, *, nome: str):
    await gerar_agenda_selecao(ctx, nome)

# Comandos de Grupos Rápidos (!grupo A, !grupoa, !grupob, etc.)
@bot.command(aliases=['grupoa', 'grupoA'])
async def grupo_a(ctx): await processar_comando_grupo(ctx, "A")

@bot.command(aliases=['grupob', 'grupoB'])
async def grupo_b(ctx): await processar_comando_grupo(ctx, "B")

@bot.command(aliases=['grupoc', 'grupoC'])
async def grupo_c(ctx): await processar_comando_grupo(ctx, "C")

@bot.command(aliases=['grupod', 'grupoD'])
async def grupo_d(ctx): await processar_comando_grupo(ctx, "D")

@bot.command(aliases=['grupoe', 'grupoE'])
async def grupo_e(ctx): await processar_comando_grupo(ctx, "E")

@bot.command(aliases=['grupof', 'grupoF'])
async def grupo_f(ctx): await processar_comando_grupo(ctx, "F")

@bot.command(aliases=['grupog', 'grupoG'])
async def grupo_g(ctx): await processar_comando_grupo(ctx, "G")

@bot.command(aliases=['grupoh', 'grupoH'])
async def grupo_h(ctx): await processar_comando_grupo(ctx, "H")

@bot.command(aliases=['grupoi', 'grupoI'])
async def grupo_i(ctx): await processar_comando_grupo(ctx, "I")

@bot.command(aliases=['grupoj', 'grupoJ'])
async def grupo_j(ctx): await processar_comando_grupo(ctx, "J")

@bot.command(aliases=['grupok', 'grupoK'])
async def grupo_k(ctx): await processar_comando_grupo(ctx, "K")

@bot.command(aliases=['grupol', 'grupoL'])
async def grupo_l(ctx): await processar_comando_grupo(ctx, "L")

@bot.command()
async def grupo(ctx, letra: str):
    await processar_comando_grupo(ctx, letra)

# ================= COMANDOS DINÂMICOS DE SELECÇÕES =================

def criar_comando_selecao(nome_exibicao):
    async def _comando(ctx): await gerar_agenda_selecao(ctx, nome_exibicao)
    return _comando

for cmd_name, display_name in SELECOES_MUNDIAL.items():
    if cmd_name not in bot.all_commands:
        bot.add_command(commands.Command(criar_comando_selecao(display_name), name=cmd_name))

# ================= TAREFA DIÁRIA AUTOMÁTICA (MEIA-NOITE) =================

@tasks.loop(time=time(hour=23, minute=0, tzinfo=timezone.utc)) # 23:00 UTC = 00:00 em Portugal Continental (UTC+1)
async def notificacao_diaria():
    canal = bot.get_channel(ID_CANAL_NOTIFICACOES)
    if canal:
        hoje_pt = (datetime.now(timezone.utc) + OFFSET_PT).date()
        await gerar_agenda_data(canal, hoje_pt, "Mundial 2026: Calendário de Hoje")

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos — Bot Mundial 2026", color=0x3498db)
    embed.add_field(name="⏰ Diários", value="`!hoje`, `!amanha` (Jogos com resultados em tempo real e canais de TV)", inline=False)
    embed.add_field(name="📅 Pesquisa", value="`!mundial DD/MM/AAAA` (Ex: `!mundial 11/06/2026`)", inline=False)
    embed.add_field(name="📊 Grupos", value="`!grupo <Letra>` ou comandos rápidos: `!grupoa` ... `!grupol` (Tabela do SofaScore)", inline=False)
    embed.add_field(name="🌳 Eliminatórias", value="`!bracket` ou `!bracket <fase>` (Mapeia o progresso real dos jogos na árvore)", inline=False)
    embed.add_field(name="⚽ Detalhes", value="`!detalhes <seleção>` (Ex: `!detalhes portugal` ou `!detalhes paraguai x franca` para ver golos, cartões e substituições)", inline=False)
    embed.add_field(name="🇵🇹 Seleções", value="Usa o nome da seleção diretamente! (Ex: `!portugal`, `!brasil`, `!argentina`, `!espanha`...) ou `!selecao <nome>`", inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready(): 
    print(f'✅ Bot Mundial 2026 Híbrido Compacto Online!')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)