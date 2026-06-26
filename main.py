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

# ID do canal de notificações automáticas (Tua escolha)
ID_CANAL_NOTIFICACOES = 1501014726111395850
ID_CANAL_VOZ_STR = os.getenv('ID_CANAL_VOZ', '813485447719813207') 

# Fuso horário de Portugal (Ajuste manual de +1h sobre o UTC)
OFFSET_PT = timedelta(hours=1)

CACHE_EXPIRY = 300 # Cache rápido de 5 minutos para os resultados em direto da API
cache_jogos = {}

# Dados de salvaguarda (Caso o mundial.csv ainda não esteja na pasta)
MUNDIAL_DEMO = [
    {"grupo": "A", "fase": "J1", "data": "11/06/2026", "dia": "Quinta", "hora": "20:00", "jogo": "México x África do Sul", "canal": "RTP 1 / LiveModeTV"},
    {"grupo": "A", "fase": "J1", "data": "12/06/2026", "dia": "Sexta", "hora": "03:00", "jogo": "Coreia do Sul x Chéquia", "canal": "Sport TV 2"},
    {"grupo": "A", "fase": "J2", "data": "18/06/2026", "dia": "Quinta", "hora": "17:00", "jogo": "Chéquia x África do Sul", "canal": "Sport TV 1"},
    {"grupo": "A", "fase": "J2", "data": "19/06/2026", "dia": "Sexta", "hora": "02:00", "jogo": "México x Coreia do Sul", "canal": "Sport TV 1"},
    {"grupo": "A", "fase": "J3", "data": "25/06/2026", "dia": "Quinta", "hora": "02:00", "jogo": "Chéquia x México", "canal": "Sport TV 1"},
    {"grupo": "A", "fase": "J3", "data": "25/06/2026", "dia": "Quinta", "hora": "02:00", "jogo": "África do Sul x Coreia do Sul", "canal": "Sport TV 2"}
]

# Dicionário de todas as Seleções Participantes e Atalhos do Mundial 2026
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
    "eslovenia": "Eslovénia", "eslovenia": "Eslovénia", "romenia": "Roménia", "roménia": "Roménia"
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

# ================= CARREGAMENTO DO CSV DO EXCEL =================

def carregar_mundial_csv():
    """Lê o mundial.csv preservando índices vazios de forma estrita, suportando fase de grupos e eliminatórias"""
    caminho_csv = "mundial.csv"
    if not os.path.exists(caminho_csv):
        print("ℹ️ [SISTEMA] 'mundial.csv' não encontrado. A usar dados padrão de teste (Grupo A).")
        return MUNDIAL_DEMO
    
    jogos = []
    current_group = None
    try:
        with open(caminho_csv, mode='r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            for row in reader:
                # Remove espaços das pontas, mas PRESERVA as células vazias intactas (evita shifting de colunas)
                row = [cell.strip() for cell in row]
                if not any(row): continue
                
                # Deteta se a linha é um cabeçalho de Grupo
                grupo_encontrado = False
                for cell in row:
                    if not cell: continue
                    m = re.search(r'GRUPO\s+([A-L])', cell, re.IGNORECASE)
                    if m:
                        current_group = m.group(1).upper()
                        grupo_encontrado = True
                        break
                if grupo_encontrado: continue
                
                # Garante que a linha tem sempre pelo menos 9 colunas para evitar desalinhamento nas leituras
                row = row + [""] * (9 - len(row))
                
                fase_str = row[0] if row[0] else ""
                fase_simp = simplificar_nome_busca(fase_str)
                is_knockout = any(f in fase_simp for f in ["r32", "r16", "qf", "sf", "1/16", "1/8", "1/4", "1/2", "oitav", "quart", "meia", "final"])
                
                # Garante que a linha tem os campos mínimos e uma data válida na coluna 1
                if (current_group or is_knockout) and len(row) >= 5:
                    data_str = row[1]
                    if re.match(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{4}', data_str):
                        jogo_str = row[4]
                        # A coluna 8 (Canal) agora estará sempre na posição correta
                        canal_str = row[8] if row[8] else "Por definir"
                        
                        jogos.append({
                            "grupo": "KO" if is_knockout else current_group,
                            "fase": fase_str,
                            "data": data_str,
                            "dia": row[2] if row[2] else "",
                            "hora": row[3] if row[3] else "",
                            "jogo": jogo_str,
                            "canal": canal_str
                        })
        return jogos
    except Exception as e:
        print(f"❌ [SISTEMA] Erro ao carregar mundial.csv: {e}")
        return MUNDIAL_DEMO

# ================= INTELIGÊNCIA DE NOMES E ABREVIAÇÕES =================

def abreviar_nome(nome, max_len=10):
    """Garante que equipas compridas são abreviadas elegantemente para a tabela do Discord"""
    nome_traduzido = traduzir_nome_equipa(nome)
    if len(nome_traduzido) <= max_len:
        return nome_traduzido
        
    substituicoes = {
        "Bósnia e Herzegovina": "Bósnia & H.",
        "África do Sul": "África Sul",
        "Coreia do Sul": "Coreia Sul",
        "República Checa": "R. Checa",
        "Arábia Saudita": "A. Saudita",
        "Estados Unidos": "EUA",
        "United States": "USA"
    }
    for original, novo in substituicoes.items():
        if original.lower() in nome_traduzido.lower():
            return novo
            
    return nome_traduzido[:max_len-1] + "."

def traduzir_nome_equipa(nome):
    """Traduz os nomes de equipas em inglês provenientes da API para Português"""
    traducoes = {
        "South Africa": "África do Sul",
        "Czechia": "Chéquia",
        "Czech Republic": "Chéquia",
        "South Korea": "Coreia do Sul",
        "Korea Republic": "Coreia do Sul",
        "Saudi Arabia": "Arábia Saudita",
        "Switzerland": "Suíça",
        "Bosnia and Herzegovina": "Bósnia e Herzegovina",
        "Bosnia & Herzegovina": "Bósnia e Herzegovina",
        "Canada": "Canadá",
        "Qatar": "Catar",
        "Germany": "Alemanha",
        "Spain": "Espanha",
        "France": "França",
        "Belgium": "Bélgica",
        "England": "Inglaterra",
        "Morocco": "Marrocos",
        "Cameroon": "Camarões",
        "Croatia": "Croácia",
        "Brazil": "Brasil",
        "USA": "Estados Unidos",
        "United States": "Estados Unidos",
        "Netherlands": "Países Baixos",
        "Iran": "Irão",
        "Japan": "Japão",
        "Poland": "Polónia",
        "Turkey": "Turquia",
        "Austria": "Áustria",
        "Ukraine": "Ucrânia",
        "Italy": "Itália",
        "Scotland": "Escócia",
        "Paraguay": "Paraguai",
        "Türkiye": "Turquia",
        "Turkiye": "Turquia",
        "Curacao": "Curaçau",
        "Curaçao": "Curaçau",
        "Ivory Coast": "Costa do Marfim",
        "Cote d'Ivoire": "Costa do Marfim",
        "Côte d'Ivoire": "Costa do Marfim",
        "Egypt": "Egito",
        "New Zealand": "Nova Zelândia",
        "Uruguay": "Uruguai",
        "DR Congo": "RD Congo",
        "Democratic Republic of the Congo": "RD Congo",
        "Haiti": "Haiti",
        "Ecuador": "Equador",
        "Colombia": "Colômbia",
        "Panama": "Panamá",
        "Algeria": "Argélia",
        "Tunisia": "Tunísia",
        "Sweden": "Suécia",
        "Denmark": "Dinamarca",
        "Ghana": "Gana",
        "Chile": "Chile",
        "Peru": "Peru",
        "Venezuela": "Venezuela",
        "Uzbekistan": "Uzbequistão",
        "Iraq": "Iraque",
        "Slovakia": "Eslováquia",
        "Slovenia": "Eslovénia",
        "Romania": "Roménia"
    }
    for k, v in traducoes.items():
        if k.lower() == nome.lower():
            return v
    return nome

def simplificar_nome_busca(nome):
    """Prepara o nome para comparação interna de strings com mapeamento unificado (Fuzzy match)"""
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    nome = nome.lower()
    traducoes_busca = {
        "republica checa": "czechia", "chequia": "czechia", "czech republic": "czechia",
        "coreia": "south korea", "coreia do sul": "south korea", "coreia_do_sul": "south korea", "korea republic": "south korea",
        "alemanha": "germany", "espanha": "spain", "franca": "france", "frança": "france",
        "belgica": "belgium", "bélgica": "belgium", "inglaterra": "england", "suica": "switzerland", "suíça": "switzerland",
        "suecia": "sweden", "suécia": "sweden", "marrocos": "morocco", "camaroes": "cameroon", "camarões": "cameroon",
        "croacia": "croatia", "croácia": "croatia", "brasil": "brazil", "estados unidos": "usa",
        "united states": "usa", "eua": "usa", "arabia": "saudi arabia", "arabia saudita": "saudi arabia", "arábia_saudita": "saudi arabia", "africa do sul": "south africa", "áfrica do sul": "south africa",
        "bosnia": "bosnia", "bosnia e herzegovina": "bosnia", "bosnia and herzegovina": "bosnia", "bosnia & herzegovina": "bosnia",
        "bosnia & h.": "bosnia", "bosnia & h": "bosnia", "bosnia and h": "bosnia", "bosnia and h.": "bosnia",
        "holanda": "netherlands", "paises baixos": "netherlands", "países baixos": "netherlands",
        "catar": "qatar", "irao": "iran", "irão": "iran", "japao": "japan", "japão": "japan", "polonia": "poland", "polónia": "poland",
        "turquia": "turkey", "turkiye": "turkey", "austria": "austria", "áustria": "austria", "ucrania": "ukraine", "ucrânia": "ukraine", "italia": "italy", "itália": "italy",
        "escocia": "scotland", "escócia": "scotland",
        "paraguai": "paraguay",
        "curacau": "curacao", "curaçau": "curacao",
        "costa do marfim": "ivory coast", "cote divoire": "ivory coast", "cote d'ivoire": "ivory coast",
        "egito": "egypt",
        "nova zelandia": "new zealand", "nova zelândia": "new zealand",
        "uruguai": "uruguay",
        "rd congo": "dr congo", "democratic republic of the congo": "dr congo", "republica democratica do congo": "dr congo",
        "equador": "ecuador",
        "colombia": "colombia", "colômbia": "colombia",
        "panama": "panama", "panamá": "panama",
        "argelia": "algeria", "argélia": "algeria",
        "tunisia": "tunisia", "tunísia": "tunisia",
        "dinamarca": "denmark",
        "gana": "ghana",
        "uzbequistao": "uzbekistan", "uzbequistão": "uzbekistan",
        "iraque": "iraq",
        "eslovaquia": "slovakia", "eslováquia": "slovakia",
        "eslovenia": "slovenia", "eslovénia": "slovenia",
        "romenia": "romania", "roménia": "romania"
    }
    for k, v in traducoes_busca.items():
        nome = nome.replace(k, v)
    for termo in ["fc", "sl", "sc", "cp", "real", "st", "club", "atletico", "de", "do", "da"]:
        nome = re.sub(rf'\b{termo}\b', '', nome)
    return nome.strip()

def equipas_correspondem(csv_casa, csv_fora, api_casa, api_fora):
    """Compara as equipas com correspondência estrita para evitar emparelhamentos falsos por palavras comuns (ex: 'Sul')"""
    c_casa = simplificar_nome_busca(csv_casa)
    c_fora = simplificar_nome_busca(csv_fora)
    a_casa = simplificar_nome_busca(api_casa)
    a_fora = simplificar_nome_busca(api_fora)
    
    # Validação estrita por igualdade de nomes ou se um nome está totalmente contido no outro
    match_direto_casa = (c_casa == a_casa) or (c_casa in a_casa) or (a_casa in c_casa)
    match_direto_fora = (c_fora == a_fora) or (c_fora in a_fora) or (a_fora in c_fora)
    if match_direto_casa and match_direto_fora:
        return True
        
    # Verificação adicional invertida (para o caso de a API inverter a ordem de casa/fora)
    match_inv_casa = (c_casa == a_fora) or (c_casa in a_fora) or (a_fora in c_casa)
    match_inv_fora = (c_fora == a_casa) or (c_fora in a_casa) or (a_casa in c_fora)
    return match_inv_casa and match_inv_fora

def equipa_no_jogo(nome_selecao, jogo_csv):
    """Verifica se a seleção pesquisada faz parte do confronto estipulado no CSV com correspondência estrita."""
    partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', jogo_csv)]
    if len(partes) != 2:
        return False
    
    s_selecao = simplificar_nome_busca(nome_selecao)
    s_casa = simplificar_nome_busca(partes[0])
    s_fora = simplificar_nome_busca(partes[1])
    
    return s_selecao in s_casa or s_selecao in s_fora

def normalizar_fase_ko(fase):
    """Normaliza o nome da fase a eliminar para uma categoria estandardizada."""
    f = simplificar_nome_busca(fase)
    if "r32" in f or "1/16" in f or "32" in f or "dezasseis" in f:
        return "Dezasseis-avos-de-final (R32)"
    if "r16" in f or "1/8" in f or "16" in f or "oitav" in f:
        return "Oitavos-de-final (R16)"
    if "qf" in f or "1/4" in f or "quart" in f or "8" in f:
        return "Quartos-de-final (QF)"
    if "sf" in f or "1/2" in f or "meia" in f or "4" in f:
        return "Meias-finais (SF)"
    if "final" in f or "f" == f or "2" in f:
        return "Grande Final"
    return "Dezasseis-avos-de-final (R32)"

# ================= INTEGRAÇÃO COM A API SOFASPORT =================

async def obter_season_id(session):
    agora = time_module.time()
    if "season_id" in cache_jogos:
        if agora - cache_jogos["season_id"]["timestamp"] < 86400:
            return cache_jogos["season_id"]["data"]

    url = "https://sofasport.p.rapidapi.com/v1/unique-tournaments/seasons"
    params = {"unique_tournament_id": "16"}
    
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params=params, timeout=10) as r:
                if r.status == 200:
                    res = await r.json()
                    seasons = res.get("data", [])
                    for s in seasons:
                        if "2026" in s.get("name", "") or s.get("year") == "2026":
                            sid = s.get("id")
                            if sid:
                                cache_jogos["season_id"] = {"data": sid, "timestamp": agora}
                                return sid
                    if seasons:
                        sid = seasons[0].get("id")
                        if sid:
                            cache_jogos["season_id"] = {"data": sid, "timestamp": agora}
                            return sid
        except Exception as e:
            print(f"⚠️ Erro ao procurar season_id na API: {e}")
    return 52561

async def obter_resultados_api(session, season_id):
    """Procura os eventos passados e futuros de forma simultânea (Gather), resolvendo o erro 422 ao enviar 'course_events'."""
    agora = time_module.time()
    if "api_events" in cache_jogos:
        if agora - cache_jogos["api_events"]["timestamp"] < CACHE_EXPIRY:
            return cache_jogos["api_events"]["data"]

    url = "https://sofasport.p.rapidapi.com/v1/seasons/events"
    
    async def fetch_events(course):
        params = {
            "seasons_id": str(season_id),
            "unique_tournament_id": "16",
            "course_events": course,
            "page": "0"
        }
        try:
            async with session.get(url, headers=HEADERS_API, params=params, timeout=12) as r:
                print(f"ℹ️ [SISTEMA] API Seasons Events chamada ({course}). Status: {r.status}")
                if r.status == 200:
                    res = await r.json()
                    return res.get("data", {}).get("events", []) or res.get("data", []) or res.get("events", []) or res
                else:
                    # Tentar alternativa sem plural
                    params_alt = {
                        "season_id": str(season_id),
                        "unique_tournament_id": "16",
                        "course_events": course,
                        "page": "0"
                    }
                    async with session.get(url, headers=HEADERS_API, params=params_alt, timeout=12) as r_alt:
                        if r_alt.status == 200:
                            res_alt = await r_alt.json()
                            return res_alt.get("data", {}).get("events", []) or res_alt.get("data", []) or res_alt.get("events", []) or res_alt
        except Exception as e:
            print(f"⚠️ Erro ao aceder a eventos do tipo '{course}': {e}")
        return []

    # Fazemos duas chamadas em paralelo para cobrir os jogos terminados ("last") e agendados ("next")
    eventos_last, eventos_next = await asyncio.gather(
        fetch_events("last"),
        fetch_events("next")
    )
    
    eventos_completos = []
    ids_vistos = set()
    
    # Unir e remover potenciais duplicados
    for ev in (eventos_last + eventos_next):
        if isinstance(ev, dict):
            ev_id = ev.get("id")
            if ev_id and ev_id not in ids_vistos:
                ids_vistos.add(ev_id)
                eventos_completos.append(ev)
            elif not ev_id:
                eventos_completos.append(ev)

    cache_jogos["api_events"] = {"data": eventos_completos, "timestamp": agora}
    return eventos_completos

async def obter_incidentes_api(session, event_id):
    """Descarrega os incidentes e a cronologia do jogo de forma extremamente robusta com caminhos e parâmetros alternativos."""
    cache_key = f"incidents_{event_id}"
    agora = time_module.time()
    if cache_key in cache_jogos:
        if agora - cache_jogos[cache_key]["timestamp"] < 60: # Cache rápido de 60 segundos para eventos ao vivo
            return cache_jogos[cache_key]["data"]

    # Tentativas de combinações de URLs e Parâmetros (singular/plural) para contornar variações da API
    tentativas = [
        ("https://sofasport.p.rapidapi.com/v1/events/incidents", {"event_id": str(event_id)}),
        ("https://sofasport.p.rapidapi.com/v1/event/incidents", {"event_id": str(event_id)}),
        ("https://sofasport.p.rapidapi.com/v1/events/incidents", {"events_id": str(event_id)}),
        ("https://sofasport.p.rapidapi.com/v1/event/incidents", {"events_id": str(event_id)}),
    ]
    
    async with api_semaphore:
        for i, (url, params) in enumerate(tentativas, 1):
            try:
                async with session.get(url, headers=HEADERS_API, params=params, timeout=10) as r:
                    print(f"ℹ️ [SISTEMA] Tentativa de incidentes {i}/4 (Status: {r.status}) na URL: {url} com params {list(params.keys())}")
                    if r.status == 200:
                        res = await r.json()
                        incidents = []
                        if isinstance(res, list):
                            incidents = res
                        elif isinstance(res, dict):
                            if "data" in res:
                                data = res["data"]
                                if isinstance(data, list):
                                    incidents = data
                                elif isinstance(data, dict):
                                    incidents = data.get("incidents", []) or data.get("events", []) or data.get("rows", [])
                            else:
                                incidents = res.get("incidents", []) or res.get("data", []) or res.get("events", [])
                        
                        # Filtro de segurança para garantir que temos uma lista válida
                        if isinstance(incidents, list) and len(incidents) > 0:
                            # Ordenar de forma ascendente por tempo de jogo
                            try:
                                incidents = sorted(incidents, key=lambda x: x.get("time", 0))
                            except:
                                pass
                            print(f"✅ [SISTEMA] Incidentes obtidos com sucesso! ({len(incidents)} itens na tentativa {i})")
                            cache_jogos[cache_key] = {"data": incidents, "timestamp": agora}
                            return incidents
                        elif isinstance(incidents, list):
                            print(f"ℹ️ [SISTEMA] API retornou lista vazia de incidentes para o evento {event_id}.")
                            cache_jogos[cache_key] = {"data": [], "timestamp": agora}
                            return []
            except Exception as e:
                print(f"⚠️ Erro ao tentar obter incidentes na tentativa {i}: {e}")
                
    return []

async def obter_tabela_api(session, season_id, letra_grupo):
    cache_key = f"standings_{letra_grupo.upper()}"
    agora = time_module.time()
    if cache_key in cache_jogos:
        if agora - cache_jogos[cache_key]["timestamp"] < CACHE_EXPIRY:
            return cache_jogos[cache_key]["data"]

    url = "https://sofasport.p.rapidapi.com/v1/seasons/standings"
    params = {"seasons_id": str(season_id), "unique_tournament_id": "16", "standing_type": "total"}
    
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params=params, timeout=15) as r:
                if r.status == 200:
                    res = await r.json()
                    grupos_data = res.get("data", []) or res.get("data", {}).get("standings", [])
                    for g in grupos_data:
                        nome_grupo = g.get("name", "").upper()
                        if f"GROUP {letra_grupo.upper()}" in nome_grupo or f"GRUPO {letra_grupo.upper()}" in nome_grupo or nome_grupo.endswith(f" {letra_grupo.upper()}"):
                            cache_jogos[cache_key] = {"data": g, "timestamp": agora}
                            return g
        except Exception as e:
            print(f"⚠️ Erro ao obter standings da API: {e}")
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

# ================= AGENDAS =================

async def gerar_agenda_data(canal_ou_ctx, data_alvo_pt, titulo):
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🚀 A ligar ao motor híbrido (CSV + API em direto)...")
    
    embed = discord.Embed(title=f"🏆 {titulo}", color=0xe67e22)
    encontrou = False
    
    data_str_pesquisa = data_alvo_pt.strftime("%d/%m/%Y") if data_alvo_pt else None
    jogos_csv = carregar_mundial_csv()
    jogos_do_dia = [j for j in jogos_csv if not data_str_pesquisa or j["data"] == data_str_pesquisa]
    
    if not jogos_do_dia:
        aviso = f"📅 Sem jogos do Mundial agendados para {titulo}."
        if msg: await msg.edit(content=aviso)
        else: await canal_ou_ctx.send(aviso)
        return

    # Ordenar jogos de forma estritamente cronológica por hora de Portugal
    # Jogos com hora "TBD" (Por definir) são empurrados para o fim da lista
    jogos_do_dia = sorted(
        jogos_do_dia, 
        key=lambda x: x["hora"] if x["hora"] and x["hora"].upper() != "TBD" else "99:99"
    )

    async with aiohttp.ClientSession() as session:
        season_id = await obter_season_id(session)
        eventos_api = await obter_resultados_api(session, season_id)
        
        for j_csv in jogos_do_dia:
            encontrou = True
            nome_jogo = j_csv["jogo"]
            hora = j_csv["hora"]
            canal = j_csv["canal"]
            
            partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', nome_jogo)]
            status_direto = ""
            
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                match_api = None
                for ev in eventos_api:
                    api_casa = ev.get("homeTeam", {}).get("name", "")
                    api_fora = ev.get("awayTeam", {}).get("name", "")
                    if equipas_correspondem(casa, fora, api_casa, api_fora):
                        match_api = ev
                        break
                
                if match_api:
                    gc = match_api.get("homeScore", {}).get("current")
                    gf = match_api.get("awayScore", {}).get("current")
                    
                    # Formato Premium: Seleção [Golos] vs Seleção [Golos]
                    if gc is not None and gf is not None:
                        status_type = match_api.get("status", {}).get("type", "")
                        status_desc = match_api.get("status", {}).get("description", "")
                        if status_type == "inprogress":
                            status_direto = f" 🟢 *({status_desc})*"
                        elif status_type == "finished":
                            status_direto = " 🔴 *(Terminado)*"
                        nome_jogo_formatado = f"**{casa} [{gc}]** vs **{fora} [{gf}]**{status_direto}"
                    else:
                        nome_jogo_formatado = f"**{casa}** vs **{fora}**"
                else:
                    nome_jogo_formatado = f"**{casa}** vs **{fora}**"
            else:
                nome_jogo_formatado = f"**{nome_jogo}**"
            
            # Formatação premium para eliminatórias ou grupos
            nome_campo = f"🏆 {j_csv['fase']}" if j_csv['grupo'] == "KO" else f"🥅 Grupo {j_csv['grupo']} — {j_csv['fase']}"
            
            embed.add_field(
                name=nome_campo,
                value=f"🕒 **{hora}** | 📺 **{canal}**\n⚔️ {nome_jogo_formatado}",
                inline=False
            )
            
            if canal_ou_ctx.guild and hora != "TBD":
                try:
                    dia, mes, ano = map(int, j_csv["data"].split('/'))
                    hora_h, hora_m = map(int, hora.split(':'))
                    dt_jogo_pt = datetime(ano, mes, dia, hora_h, hora_m, tzinfo=timezone(OFFSET_PT))
                    dt_jogo_utc = dt_jogo_pt.astimezone(timezone.utc)
                    await criar_evento_discord(canal_ou_ctx.guild, nome_jogo, dt_jogo_utc, f"Mundial 2026 (Grupo {j_csv['grupo']})", canal)
                except: pass

    if msg: await msg.edit(content=None, embed=embed)
    else: await canal_ou_ctx.send(embed=embed)

# ================= AGENDAS DE SELEÇÕES NACIONAIS =================

async def gerar_agenda_selecao(canal_ou_ctx, nome_selecao):
    """Filtra e mostra todos os jogos de uma seleção nacional específica com resultados em tempo real"""
    msg = None
    if isinstance(canal_ou_ctx, commands.Context):
        msg = await canal_ou_ctx.send(f"🚀 A procurar calendário para **{nome_selecao}**...")
        
    jogos_csv = carregar_mundial_csv()
    # Filtra os jogos do CSV onde a seleção joga (Casa ou Fora)
    jogos_filtrados = [j for j in jogos_csv if equipa_no_jogo(nome_selecao, j["jogo"])]
    
    if not jogos_filtrados:
        aviso = f"⚠️ Não encontrei nenhum jogo agendado para a seleção de **{nome_selecao}** no calendário do Mundial."
        if msg: await msg.edit(content=aviso)
        else: await canal_ou_ctx.send(aviso)
        return

    # Ordenar os jogos cronologicamente por data e hora
    def parse_datetime(j):
        try:
            dia, mes, ano = map(int, j["data"].split('/'))
            hora_str = j["hora"]
            if not hora_str or hora_str.upper() == "TBD":
                hora_h, hora_m = 23, 59
            else:
                hora_h, hora_m = map(int, hora_str.split(':'))
            return datetime(ano, mes, dia, hora_h, hora_m)
        except:
            return datetime(9999, 12, 31, 23, 59)

    jogos_filtrados = sorted(jogos_filtrados, key=parse_datetime)

    # Determinar a cor estética com base no nome do país pesquisado
    cor_embed = 0x3498db
    p_lower = nome_selecao.lower()
    if "portugal" in p_lower: cor_embed = 0xe74c3c
    elif "brasil" in p_lower or "brazil" in p_lower: cor_embed = 0xf1c40f
    elif "espanha" in p_lower or "spain" in p_lower: cor_embed = 0xc0392b
    elif "franca" in p_lower or "french" in p_lower: cor_embed = 0x2980b9

    embed = discord.Embed(title=f"⚽ Calendário: {nome_selecao.upper()}", color=cor_embed)
    
    async with aiohttp.ClientSession() as session:
        season_id = await obter_season_id(session)
        eventos_api = await obter_resultados_api(session, season_id)
        
        # CORREÇÃO DO NameError: Alterada a variável de 'juegos_filtrados' para 'jogos_filtrados'
        for j_csv in jogos_filtrados:
            nome_jogo = j_csv["jogo"]
            hora = j_csv["hora"]
            canal = j_csv["canal"]
            data = j_csv["data"]
            
            partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', nome_jogo)]
            status_direto = ""
            
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                match_api = None
                for ev in eventos_api:
                    api_casa = ev.get("homeTeam", {}).get("name", "")
                    api_fora = ev.get("awayTeam", {}).get("name", "")
                    if equipas_correspondem(casa, fora, api_casa, api_fora):
                        match_api = ev
                        break
                
                if match_api:
                    gc = match_api.get("homeScore", {}).get("current")
                    gf = match_api.get("awayScore", {}).get("current")
                    if gc is not None and gf is not None:
                        status_type = match_api.get("status", {}).get("type", "")
                        status_desc = match_api.get("status", {}).get("description", "")
                        if status_type == "inprogress":
                            status_direto = f" 🟢 *({status_desc})*"
                        elif status_type == "finished":
                            status_direto = " 🔴 *(Terminado)*"
                        nome_jogo_formatado = f"**{casa} [{gc}]** vs **{fora} [{gf}]**{status_direto}"
                    else:
                        nome_jogo_formatado = f"**{casa}** vs **{fora}**"
                else:
                    nome_jogo_formatado = f"**{casa}** vs **{fora}**"
            else:
                nome_jogo_formatado = f"**{nome_jogo}**"
            
            nome_campo = f"📅 {data} @ {hora} ({j_csv['fase']})" if j_csv['grupo'] == "KO" else f"📅 {data} @ {hora} (Grupo {j_csv['grupo']})"
            
            embed.add_field(
                name=nome_campo,
                value=f"📺 Canal: **{canal}**\n⚔️ {nome_jogo_formatado}",
                inline=False
            )
            
    if msg: await msg.edit(content=None, embed=embed)
    else: await canal_ou_ctx.send(embed=embed)

# ================= COMANDO DE GRUPO (CLASSIFICAÇÃO COMPACTA PREMIUM) =================

async def processar_comando_grupo(ctx, letra_grupo):
    letra_grupo = letra_grupo.upper()
    await ctx.send(f"📊 A aceder à tabela oficial da API para o **Grupo {letra_grupo}**...")
    
    async with aiohttp.ClientSession() as session:
        season_id = await obter_season_id(session)
        tabela_data = await obter_tabela_api(session, season_id, letra_grupo)
        
        if not tabela_data:
            return await ctx.send(f"⚠️ Não foi possível obter as classificações em direto para o **Grupo {letra_grupo}**.")

        embed = discord.Embed(title=f"🏆 MUNDIAL 2026 — GRUPO {letra_grupo}", color=0x2ecc71)
        
        # Desenha a tabela com formato premium de alta legibilidade (Fina, limpa e ideal para telemóveis)
        linhas_tabela = [f" #  {'Equipa':<10} J  V-E-D   DG Pts"]
        linhas_tabela.append("────────────────────────────────")
        
        rows = tabela_data.get("rows", [])
        for idx, r in enumerate(rows):
            nome_original = r.get("team", {}).get("name", "N/A")
            nome_f = abreviar_nome(nome_original, 10)
            nome_f = f"{nome_f:<10}"
            
            pts = r.get("points", 0)
            j = r.get("matches", 0)
            v = r.get("wins", 0)
            e = r.get("draws", 0)
            d = r.get("losses", 0)
            
            # Correção Cirúrgica: Chaves oficiais da SofaSport para golos marcados e sofridos
            gm = r.get("scoresFor") if r.get("scoresFor") is not None else r.get("goalsFor", 0)
            gs = r.get("scoresAgainst") if r.get("scoresAgainst") is not None else r.get("goalsAgainst", 0)
            dg = gm - gs
            
            # Formatação limpa do saldo de golos (+0, +2, -3)
            dg_str = f"{dg:+2}" if dg != 0 else " 0"
            ved_str = f"{v}-{e}-{d}"
            
            # Linha alinhada de forma perfeita e limpa
            linha = f" {idx+1}º {nome_f} {j:<1}  {ved_str:<5} {dg_str:>3} {pts:>3}"
            linhas_tabela.append(linha)
            
        tabela_texto = "```\n" + "\n".join(linhas_tabela) + "\n```"
        embed.add_field(name="📊 Tabela Classificativa (Em Direto)", value=tabela_texto, inline=False)
        
        # Mostra o calendário e canais do Excel corrigidos
        eventos_api = await obter_resultados_api(session, season_id)
        jogos_csv = carregar_mundial_csv()
        jogos_grupo = [jg for jg in jogos_csv if jg["grupo"] == letra_grupo]
        
        # Ordenar os jogos do grupo cronologicamente
        def parse_datetime(j):
            try:
                dia, mes, ano = map(int, j["data"].split('/'))
                hora_str = j["hora"]
                if not hora_str or hora_str.upper() == "TBD":
                    hora_h, hora_m = 23, 59
                else:
                    hora_h, hora_m = map(int, hora_str.split(':'))
                return datetime(ano, mes, dia, hora_h, hora_m)
            except:
                return datetime(9999, 12, 31, 23, 59)

        jogos_grupo = sorted(jogos_grupo, key=parse_datetime)

        linhas_jogos = []
        for j_g in jogos_grupo:
            nome_jogo = j_g["jogo"]
            partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', nome_jogo)]
            status_direto = ""
            
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                match_api = None
                for ev in eventos_api:
                    if equipas_correspondem(casa, fora, ev.get("homeTeam", {}).get("name", ""), ev.get("awayTeam", {}).get("name", "")):
                        match_api = ev
                        break
                if match_api:
                    gc = match_api.get("homeScore", {}).get("current")
                    gf = match_api.get("awayScore", {}).get("current")
                    if gc is not None and gf is not None:
                        status_type = match_api.get("status", {}).get("type", "")
                        status_desc = match_api.get("status", {}).get("description", "")
                        if status_type == "inprogress":
                            status_direto = f" 🟢 *({status_desc})*"
                        elif status_type == "finished":
                            status_direto = " 🔴 *(Terminado)*"
                        jogo_f = f"**{casa} [{gc}]** vs **{fora} [{gf}]**{status_direto}"
                    else:
                        jogo_f = f"**{casa}** vs **{fora}**"
                else:
                    jogo_f = f"**{casa}** vs **{fora}**"
            else:
                jogo_f = nome_jogo
                
            linhas_jogos.append(f"📅 {j_g['data']} @ {j_g['hora']} — {jogo_f} *(📺 {j_g['canal']})*")
            
        embed.add_field(name="🥅 Calendário & Resultados", value="\n".join(linhas_jogos), inline=False)
        await ctx.send(embed=embed)

# ================= COMANDO DE DETALHES DE JOGO EM DIRETO (INCIDENTES) =================

def obter_codigo_selecao(nome):
    """Gera um código de 3 letras estrito e limpo sem acentos com base no nome do país."""
    nome_clean = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    nome_clean = re.sub(r'[^a-zA-Z]', '', nome_clean)
    return nome_clean[:3].upper()

def extrair_duas_selecoes(texto):
    """Analisa a string de pesquisa e tenta extrair duas seleções distintas conhecidas em tempo de execução."""
    texto_simp = simplificar_nome_busca(texto)
    
    # Extrai e simplifica todos os atalhos de seleção registados no dicionário global
    lista_selet_simp = []
    for k in SELECOES_MUNDIAL.keys():
        simp = simplificar_nome_busca(k)
        if simp and simp not in lista_selet_simp:
            lista_selet_simp.append(simp)
            
    # Ordenar por comprimento decrescente para priorizar nomes compostos (ex: "ivory coast")
    lista_selet_simp = sorted(lista_selet_simp, key=len, reverse=True)
    
    encontradas = []
    for sel_simp in lista_selet_simp:
        if sel_simp in texto_simp:
            # Evita capturar sub-strings já contidas em algo maior já mapeado
            ja_existe = False
            for enc in encontradas:
                if sel_simp in enc:
                    ja_existe = True
                    break
            if not ja_existe:
                encontradas.append(sel_simp)
                texto_simp = texto_simp.replace(sel_simp, "", 1)
                
    if len(encontradas) >= 2:
        return encontradas[0], encontradas[1]
    return None

@bot.command(aliases=['jogo', 'info', 'eventos'])
async def detalhes(ctx, *, equipas_pesquisa: str):
    """Mostra os incidentes detalhados de um jogo dividido por 1ª e 2ª parte em direto (com códigos de seleção)."""
    await ctx.send("🔍 A descarregar detalhes e incidentes da partida na API...")
    
    # 1. Tentar extração inteligente de duas seleções no texto (ex: "tunisia japao" -> ("tunisia", "japan"))
    selecoes_encontradas = extrair_duas_selecoes(equipas_pesquisa)
    
    jogos_csv = carregar_mundial_csv()
    match_csv = None
    
    if selecoes_encontradas:
        sel1, sel2 = selecoes_encontradas
        for j in jogos_csv:
            if equipa_no_jogo(sel1, j["jogo"]) and equipa_no_jogo(sel2, j["jogo"]):
                match_csv = j
                break
    else:
        # Fallback para o comportamento padrão (pode ser apenas uma seleção ou pesquisa com separador explícito)
        partes = [p.strip() for p in re.split(r'\s+(?:[xX×]|vs\.?|[-–—]|e)\s+', equipas_pesquisa)]
        if len(partes) == 2:
            for j in jogos_csv:
                if equipa_no_jogo(partes[0], j["jogo"]) and equipa_no_jogo(partes[1], j["jogo"]):
                    match_csv = j
                    break
        elif len(partes) == 1:
            for j in jogos_csv:
                if equipa_no_jogo(partes[0], j["jogo"]):
                    match_csv = j
                    break
                
    if not match_csv:
        return await ctx.send("❌ Não encontrei nenhuma partida agendada para essa pesquisa no calendário do Mundial.")
        
    nome_jogo = match_csv["jogo"]
    partes_jogo = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', nome_jogo)]
    if len(partes_jogo) != 2:
        return await ctx.send("❌ Formato de jogo inválido no calendário local.")
        
    casa, fora = traduzir_nome_equipa(partes_jogo[0]), traduzir_nome_equipa(partes_jogo[1])
    
    async with aiohttp.ClientSession() as session:
        season_id = await obter_season_id(session)
        eventos_api = await obter_resultados_api(session, season_id)
        
        match_api = None
        for ev in eventos_api:
            api_casa = ev.get("homeTeam", {}).get("name", "")
            api_fora = ev.get("awayTeam", {}).get("name", "")
            if equipas_correspondem(casa, fora, api_casa, api_fora):
                match_api = ev
                break
                
        if not match_api:
            return await ctx.send(f"⚠️ Encontrei o jogo **{casa} vs {fora}** no calendário local, mas ainda não está sincronizado com o servidor SofaSport.")
            
        event_id = match_api.get("id")
        if not event_id:
            return await ctx.send("❌ Erro ao obter o identificador da partida em direto.")
            
        incidents = await obter_incidentes_api(session, event_id)
        
        gc = match_api.get("homeScore", {}).get("current")
        gf = match_api.get("awayScore", {}).get("current")
        resultado_f = f"**[{gc}]** vs **[{gf}]**" if gc is not None and gf is not None else "vs"
        
        status_desc = match_api.get("status", {}).get("description", "Agendado")
        
        embed = discord.Embed(
            title=f"⚽ Detalhes do Confronto: {casa} {resultado_f} {fora}",
            description=f"🏟️ Estado: **{status_desc}** | 📺 Transmissão: **{match_csv['canal']}**",
            color=0x2ecc71
        )
        
        # Estruturas para as partes do jogo (Cronologia Dividida)
        parte_1 = []
        parte_2 = []
        prolongamento = []
        
        cod_casa = obter_codigo_selecao(casa)
        cod_fora = obter_codigo_selecao(fora)
        
        for inc in incidents:
            # Varredura inteligente de chaves (incidentType vs type)
            inc_type = (inc.get("incidentType") or inc.get("type") or "").lower()
            time_val = inc.get('time', 0)
            tempo = f"{time_val}'"
            if inc.get("addedTime"):
                tempo = f"{time_val}+{inc.get('addedTime')}'"
                
            # Identificação estrita da equipa (isHome / home / isHomeTeam)
            is_home = inc.get("isHome")
            if is_home is None:
                is_home = inc.get("home")
            if is_home is None:
                is_home = True
                
            cod_equipa = cod_casa if is_home else cod_fora
            emoji_equipa = "🟢" if is_home else "🔵"
            
            # Parsing robusto do jogador envolvido
            p_obj = inc.get("player")
            if isinstance(p_obj, dict):
                player_name = p_obj.get("name") or p_obj.get("shortName") or "Jogador"
            elif isinstance(p_obj, str):
                player_name = p_obj
            else:
                player_name = "Jogador"
            
            evento_linha = ""
            
            if inc_type == "goal":
                inc_class = (inc.get("incidentClass") or inc.get("class") or "").lower()
                emoji = "⚽"
                detalhe = "GOLO"
                if inc_class == "penalty":
                    emoji = "🥅"
                    detalhe = "GOLO (p)"
                elif inc_class == "owngoal":
                    emoji = "❌"
                    detalhe = "Auto-Golo"
                    
                # Parsing robusto do jogador da assistência
                assist_obj = inc.get("assist")
                assist_name = None
                if isinstance(assist_obj, dict):
                    assist_name = assist_obj.get("name") or assist_obj.get("shortName")
                elif isinstance(assist_obj, str):
                    assist_name = assist_obj
                    
                assist_str = f" *(p/ {assist_name})*" if assist_name else ""
                evento_linha = f"{emoji_equipa} **[{cod_equipa}]** `{tempo:<5}` {emoji} **{detalhe}!** — *{player_name}*{assist_str}"
                
            elif inc_type == "card":
                inc_class = (inc.get("incidentClass") or inc.get("class") or "").lower()
                if "yellowred" in inc_class or "yellow-red" in inc_class:
                    emoji = "🟨🟥"
                    detalhe = "Duplo Amarelo"
                elif "red" in inc_class:
                    emoji = "🟥"
                    detalhe = "Vermelho!"
                else:
                    emoji = "🟨"
                    detalhe = "Amarelo"
                evento_linha = f"{emoji_equipa} **[{cod_equipa}]** `{tempo:<5}` {emoji} **{detalhe}** — *{player_name}*"
                
            elif inc_type == "substitution":
                p_in_obj = inc.get("playerIn")
                p_out_obj = inc.get("playerOut")
                
                player_in = "Entra"
                if isinstance(p_in_obj, dict):
                    player_in = p_in_obj.get("name") or p_in_obj.get("shortName") or "Jogador"
                elif isinstance(p_in_obj, str):
                    player_in = p_in_obj
                    
                player_out = "Sai"
                if isinstance(p_out_obj, dict):
                    player_out = p_out_obj.get("name") or p_out_obj.get("shortName") or "Jogador"
                elif isinstance(p_out_obj, str):
                    player_out = p_out_obj
                    
                evento_linha = f"{emoji_equipa} **[{cod_equipa}]** `{tempo:<5}` 🔄 *{player_out}* ➡️ *{player_in}*"
            
            # Distribuir os eventos pelas respetivas metades cronológicas
            if evento_linha:
                if time_val <= 45:
                    parte_1.append(evento_linha)
                elif 45 < time_val <= 90:
                    parte_2.append(evento_linha)
                else:
                    prolongamento.append(evento_linha)
        
        # Função auxiliar estrita de formatação de limite seguro de 1024 caracteres
        def formatar_parte(lista_eventos):
            if not lista_eventos:
                return "🏟️ *Sem incidentes registados nesta parte.*"
            texto = ""
            for item in lista_eventos:
                if len(texto) + len(item) + 45 > 1024:
                    texto += "\n*... e mais incidentes.*"
                    break
                if texto:
                    texto += "\n" + item
                else:
                    texto = item
            return texto
            
        # Adicionar as metades separadas cronologicamente ao Embed
        embed.add_field(name="⏱️ 1ª PARTE", value=formatar_parte(parte_1), inline=False)
        embed.add_field(name="⏱️ 2ª PARTE", value=formatar_parte(parte_2), inline=False)
        if prolongamento:
            embed.add_field(name="⏱️ PROLONGAMENTO / PÉNALTIS", value=formatar_parte(prolongamento), inline=False)
            
        await ctx.send(embed=embed)

# ================= COMANDO DE BRACKET DA FASE A ELIMINAR =================

@bot.command(aliases=['faseeliminar', 'eliminatorias', 'esquema', 'fases'])
async def bracket(ctx, *, fase_filtro: str = None):
    """Mostra os confrontos da fase a eliminar (bracket) sincronizados com os golos da API."""
    await ctx.send("🔍 A carregar a árvore das eliminatórias...")
    
    jogos_csv = carregar_mundial_csv()
    jogos_ko = [j for j in jogos_csv if j["grupo"] == "KO"]
    
    if not jogos_ko:
        return await ctx.send("ℹ️ Não foram encontrados jogos da fase a eliminar no calendário `mundial.csv` de momento.")
        
    # Agrupar por fase normalizada
    categorias = {
        "Dezasseis-avos-de-final (R32)": [],
        "Oitavos-de-final (R16)": [],
        "Quartos-de-final (QF)": [],
        "Meias-finais (SF)": [],
        "Grande Final": []
    }
    
    for j in jogos_ko:
        cat = normalizar_fase_ko(j["fase"])
        if cat in categorias:
            categorias[cat].append(j)
            
    # Determinar qual a fase a mostrar
    fase_alvo = None
    if fase_filtro:
        fase_filtro_simp = simplificar_nome_busca(fase_filtro)
        if any(x in fase_filtro_simp for x in ["32", "1/16", "dezasseis"]):
            fase_alvo = "Dezasseis-avos-de-final (R32)"
        elif any(x in fase_filtro_simp for x in ["16", "1/8", "oitav"]):
            fase_alvo = "Oitavos-de-final (R16)"
        elif any(x in fase_filtro_simp for x in ["8", "1/4", "quart"]):
            fase_alvo = "Quartos-de-final (QF)"
        elif any(x in fase_filtro_simp for x in ["4", "1/2", "meia"]):
            fase_alvo = "Meias-finais (SF)"
        elif any(x in fase_filtro_simp for x in ["final", "f", "decis"]):
            fase_alvo = "Grande Final"
        else:
            return await ctx.send("❌ Fase inválida. Escolhe entre: `R32`, `Oitavos`, `Quartos`, `Meias` ou `Final`.")
    else:
        # Seleção automática da primeira fase que tenha jogos por realizar ou em direto
        for cat, lista in categorias.items():
            if lista:
                fase_alvo = cat
                break
        if not fase_alvo:
            fase_alvo = "Dezasseis-avos-de-final (R32)"
            
    jogos_fase = categorias.get(fase_alvo, [])
    if not jogos_fase:
        return await ctx.send(f"📅 Sem jogos agendados para a fase **{fase_alvo}** de momento.")
        
    # Ordenar cronologicamente
    def parse_datetime(j):
        try:
            dia, mes, ano = map(int, j["data"].split('/'))
            hora_str = j["hora"]
            if not hora_str or hora_str.upper() == "TBD":
                hora_h, hora_m = 23, 59
            else:
                hora_h, hora_m = map(int, hora_str.split(':'))
            return datetime(ano, mes, dia, hora_h, hora_m)
        except:
            return datetime(9999, 12, 31, 23, 59)

    jogos_fase = sorted(jogos_fase, key=parse_datetime)
    
    embed = discord.Embed(
        title=f"🏆 Árvore do Mundial — {fase_alvo.upper()}",
        description="Acompanha o caminho rumo ao topo do mundo! 🌟",
        color=0xe74c3c
    )
    
    async with aiohttp.ClientSession() as session:
        season_id = await obter_season_id(session)
        eventos_api = await obter_resultados_api(session, season_id)
        
        linhas_jogos = []
        for j_csv in jogos_fase:
            nome_jogo = j_csv["jogo"]
            partes = [p.strip() for p in re.split(r'\s+(?:[xX]|vs)\s+', nome_jogo)]
            status_direto = ""
            
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                match_api = None
                for ev in eventos_api:
                    api_casa = ev.get("homeTeam", {}).get("name", "")
                    api_fora = ev.get("awayTeam", {}).get("name", "")
                    if equipas_correspondem(casa, fora, api_casa, api_fora):
                        match_api = ev
                        break
                
                if match_api:
                    gc = match_api.get("homeScore", {}).get("current")
                    gf = match_api.get("awayScore", {}).get("current")
                    if gc is not None and gf is not None:
                        status_type = match_api.get("status", {}).get("type", "")
                        status_desc = match_api.get("status", {}).get("description", "")
                        if status_type == "inprogress":
                            status_direto = f" 🟢 *({status_desc})*"
                        elif status_type == "finished":
                            status_direto = " 🔴 *(Terminado)*"
                        jogo_f = f"**{casa} [{gc}]** vs **{fora} [{gf}]**{status_direto}"
                    else:
                        jogo_f = f"**{casa}** vs **{fora}**"
                else:
                    jogo_f = f"**{casa}** vs **{fora}**"
            else:
                jogo_f = f"**{nome_jogo}**"
                
            linhas_jogos.append(f"📅 **{j_csv['data']} @ {j_csv['hora']}** | 📺 **{j_csv['canal']}**\n⚔️ {jogo_f}\n")
            
        # Dividir em blocos de até 8 confrontos para respeitar os limites de embeds do Discord
        chunk_size = 8
        for i in range(0, len(linhas_jogos), chunk_size):
            chunk = linhas_jogos[i:i+chunk_size]
            field_title = "⚽ Confrontos" if i == 0 else f"⚽ Confrontos (Continuação)"
            embed.add_field(name=field_title, value="".join(chunk), inline=False)
            
    embed.set_footer(text="💡 Usa !bracket <fase> (ex: oitavos, quartos, meias, final) para veres outras fases!")
    await ctx.send(embed=embed)

# ================= TAREFA AUTOMÁTICA DIÁRIA (MEIA NOITE PORTUGAL) =================

@tasks.loop(time=time(hour=23, minute=0, tzinfo=timezone.utc)) # 23:00 UTC = 00:00 (Meia-Noite) em Portugal (UTC+1)
async def notificacao_diaria():
    print(f"⏰ [AUTOMÁTICO] A enviar agenda diária do Mundial à meia-noite...")
    canal = bot.get_channel(ID_CANAL_NOTIFICACOES)
    if canal:
        hoje_pt = (datetime.now(timezone.utc) + OFFSET_PT).date()
        await gerar_agenda_data(canal, hoje_pt, "Mundial 2026: Agenda de Hoje")

# ================= COMANDOS =================

@bot.command()
async def hoje(ctx):
    hoje_pt = (datetime.now(timezone.utc) + OFFSET_PT).date()
    await gerar_agenda_data(ctx, hoje_pt, "Mundial 2026 — Jogos de Hoje")

@bot.command()
async def amanha(ctx):
    amanha_pt = (datetime.now(timezone.utc) + OFFSET_PT + timedelta(days=1)).date()
    await gerar_agenda_data(ctx, amanha_pt, "Mundial 2026 — Jogos de Amanhã")

@bot.command()
async def mundial(ctx, data_pesquisa: str = None):
    """Mostra os jogos de uma data específica (ex: !mundial 11/06/2026)"""
    if data_pesquisa:
        try:
            data_validada = datetime.strptime(data_pesquisa, "%d/%m/%Y").date()
            await gerar_agenda_data(ctx, data_validada, f"Mundial 2026 — Agenda de {data_pesquisa}")
        except ValueError:
            await ctx.send("❌ Formato de data inválido. Usa: `DD/MM/AAAA` (Ex: `!mundial 11/06/2026`)")
    else:
        hoje_pt = (datetime.now(timezone.utc) + OFFSET_PT).date()
        await gerar_agenda_data(ctx, hoje_pt, "Mundial 2026 — Jogos de Hoje")

# Comandos Rápidos de Grupos (!grupoa, !grupob, etc.)
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
async def group_h(ctx): await processar_comando_grupo(ctx, "H")

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
    """Mostra a tabela e resultados em direto de um grupo (Ex: !grupo A)"""
    await processar_comando_grupo(ctx, letra)

@bot.command(aliases=['país', 'pais'])
async def selecao(ctx, *, nome: str):
    """Mostra todos os jogos de uma seleção específica (Ex: !selecao Argentina)"""
    await gerar_agenda_selecao(ctx, nome)

# ================= REGISTO DINÂMICO DE COMANDOS PARA TODAS AS SELEÇÕES =================

def criar_comando_selecao(nome_exibicao):
    """Função fábrica para evitar problemas de late-binding no loop de comandos"""
    async def _comando(ctx):
        await gerar_agenda_selecao(ctx, nome_exibicao)
    return _comando

# Criação dinâmica de comandos diretos para todas as seleções conhecidas
for cmd_name, display_name in SELECOES_MUNDIAL.items():
    if cmd_name not in bot.all_commands:
        cmd_func = criar_comando_selecao(display_name)
        cmd_obj = commands.Command(
            cmd_func, 
            name=cmd_name, 
            help=f"Mostra a agenda completa e resultados em tempo real de {display_name}"
        )
        bot.add_command(cmd_obj)

# ----------------------------------------------------------------------------------------

@bot.command()
async def comandos(ctx):
    embed = discord.Embed(title="📖 Guia de Comandos — Mundial 2026", color=0x3498db)
    embed.add_field(name="⏰ Agendas Diárias", value="`!hoje`, `!amanha` (Agenda híbrida de canais e resultados em direto)", inline=False)
    embed.add_field(name="📅 Pesquisa de Data", value="`!mundial DD/MM/AAAA` (Ex: `!mundial 11/06/2026`)", inline=False)
    embed.add_field(name="📊 Grupos & Classificações", value="`!grupo A` ou comandos rápidos: `!grupoa` ... `!grupol` (Tabela ultra-compacta para telemóveis)", inline=False)
    embed.add_field(name="🌳 Fase a Eliminar", value="`!bracket <fase>` ou `!bracket` (Mostra os emparelhamentos dos oitavos, quartos, etc. em tempo real)", inline=False)
    embed.add_field(name="⚽ Detalhes do Jogo (Cronologia)", value="`!detalhes <seleção1> <seleção2>` ou `!detalhes <seleção>` (Ex: `!detalhes portugal` ou `!detalhes mexico x africa`)", inline=False)
    embed.add_field(name="⚽ Seleções Nacionais", value="Comandos diretos para TODAS as seleções do Mundial (Ex: `!portugal`, `!brasil`, `!argentina`, `!alemanha`, `!marrocos`, etc.) ou pesquisa genérica: `!selecao <nome>`", inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'✅ Bot Mundial 2026 Híbrido Compacto Online!')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)