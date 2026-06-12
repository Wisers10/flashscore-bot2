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
    "gana": "Gana", "africa_do_sul": "África do Sul", "áfrica_do_sul": "África do Sul"
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
    """Lê o mundial.csv preservando índices vazios de forma estrita"""
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
                        canal_str = row[8] if row[8] else "Por definir"
                        
                        jogos.append({
                            "grupo": current_group,
                            "fase": row[0] if row[0] else "",
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
        "United States": "Estados Unidos"
    }
    for k, v in traducoes.items():
        if k.lower() == nome.lower():
            return v
    return nome

def simplificar_nome_busca(nome):
    """Prepara o nome para comparação interna de strings (Fuzzy match)"""
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome) if unicodedata.category(c) != 'Mn')
    nome = nome.lower()
    traducoes_busca = {
        "republica checa": "czechia", "chequia": "czechia", "czech republic": "czechia",
        "coreia do sul": "south korea", "korea republic": "south korea",
        "alemanha": "germany", "espanha": "spain", "franca": "france",
        "belgica": "belgium", "inglaterra": "england", "suica": "switzerland",
        "suecia": "sweden", "marrocos": "morocco", "camaroes": "cameroon",
        "croacia": "croatia", "brasil": "brazil", "estados unidos": "usa",
        "united states": "usa", "arabia saudita": "saudi arabia", "africa do sul": "south africa",
        "bosnia e herzegovina": "bosnia and herzegovina", "bosnia & herzegovina": "bosnia and herzegovina",
        "catar": "qatar", "irao": "iran", "japao": "japan", "polonia": "poland", "turquia": "turkey",
        "austria": "austria", "ucrania": "ukraine", "italia": "italy", "paises baixos": "netherlands"
    }
    for k, v in traducoes_busca.items():
        nome = nome.replace(k, v)
    for termo in ["fc", "sl", "sc", "cp", "real", "st", "club", "atletico", "de", "do", "da"]:
        nome = re.sub(rf'\b{termo}\b', '', nome)
    return nome.strip()

def equipas_correspondem(csv_casa, csv_fora, api_casa, api_fora):
    if not csv_casa or not csv_fora or not api_casa or not api_fora:
        return False
    c_casa = simplificar_nome_busca(csv_casa)
    c_fora = simplificar_nome_busca(csv_fora)
    a_casa = simplificar_nome_busca(api_casa)
    a_fora = simplificar_nome_busca(api_fora)
    
    if not c_casa or not c_fora or not a_casa or not a_fora:
        return False
        
    palavras_c_casa = set(c_casa.split())
    palavras_c_fora = set(c_fora.split())
    palavras_a_casa = set(a_casa.split())
    palavras_a_fora = set(a_fora.split())
    
    match_casa = bool(palavras_c_casa & palavras_a_casa) or c_casa in a_casa or a_casa in c_casa
    match_fora = bool(palavras_c_fora & palavras_a_fora) or c_fora in a_fora or a_fora in c_fora
    return match_casa and match_fora

def equipa_no_jogo(nome_selecao, jogo_csv):
    """Verifica se a seleção pesquisada faz parte do confronto estipulado no CSV"""
    partes = [p.strip() for p in re.split(r'\s*[\s\xa0]+(?:[xX×]|vs\.?|[-–—])[\s\xa0]+\s*', jogo_csv)]
    if len(partes) != 2:
        return False
    
    s_selecao = simplificar_nome_busca(nome_selecao)
    s_casa = simplificar_nome_busca(partes[0])
    s_fora = simplificar_nome_busca(partes[1])
    
    return s_selecao in s_casa or s_casa in s_selecao or s_selecao in s_fora or s_fora in s_selecao

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
                    seasons = []
                    if isinstance(res, dict):
                        seasons = res.get("data", []) or res.get("seasons", [])
                    elif isinstance(res, list):
                        seasons = res
                        
                    for s in seasons:
                        if "2026" in s.get("name", "") or s.get("year") == "2026":
                            sid = s.get("id")
                            cache_jogos["season_id"] = {"data": sid, "timestamp": agora}
                            return sid
                    if seasons:
                        sid = seasons[0].get("id")
                        cache_jogos["season_id"] = {"data": sid, "timestamp": agora}
                        return sid
        except Exception as e:
            print(f"⚠️ Erro ao procurar season_id na API: {e}")
    return 52561

async def obter_resultados_api(session, season_id):
    """Procura os eventos da época de forma estável, passando todos os parâmetros obrigatórios."""
    agora = time_module.time()
    if "api_events" in cache_jogos:
        if agora - cache_jogos["api_events"]["timestamp"] < CACHE_EXPIRY:
            return cache_jogos["api_events"]["data"]

    url = "https://sofasport.p.rapidapi.com/v1/seasons/events"
    
    # 1ª Tentativa: "seasons_id" (padrão oficial que requer unique_tournament_id)
    params = {
        "seasons_id": str(season_id),
        "unique_tournament_id": "16",
        "page": "0"
    }
    
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params=params, timeout=12) as r:
                print(f"ℹ️ [SISTEMA] API Seasons Events chamada (seasons_id). Status: {r.status}")
                if r.status == 200:
                    res = await r.json()
                    eventos = []
                    if isinstance(res, list):
                        eventos = res
                    elif isinstance(res, dict):
                        if "events" in res and isinstance(res["events"], list):
                            eventos = res["events"]
                        elif "data" in res:
                            data = res["data"]
                            if isinstance(data, list):
                                eventos = data
                            elif isinstance(data, dict):
                                eventos = data.get("events", []) or data.get("rows", [])
                        else:
                            eventos = res.get("rows", []) or res.get("data", [])
                    
                    print(f"✅ [SISTEMA] API retornou {len(eventos)} eventos com sucesso.")
                    cache_jogos["api_events"] = {"data": eventos, "timestamp": agora}
                    return eventos
                elif r.status == 422:
                    # 2ª Tentativa de Redundância: "season_id" (singular) se o plural for rejeitado
                    print(f"⚠️ [SISTEMA] Status 422 recebido. A tentar alternativa limpa com 'season_id'...")
                    params_alt = {
                        "season_id": str(season_id),
                        "unique_tournament_id": "16",
                        "page": "0"
                    }
                    async with session.get(url, headers=HEADERS_API, params=params_alt, timeout=12) as r_alt:
                        print(f"ℹ️ [SISTEMA] API Seasons Events chamada (season_id). Status: {r_alt.status}")
                        if r_alt.status == 200:
                            res_alt = await r_alt.json()
                            eventos = []
                            if isinstance(res_alt, list):
                                eventos = res_alt
                            elif isinstance(res_alt, dict):
                                if "events" in res_alt and isinstance(res_alt["events"], list):
                                    eventos = res_alt["events"]
                                elif "data" in res_alt:
                                    data_alt = res_alt["data"]
                                    if isinstance(data_alt, list):
                                        eventos = data_alt
                                    elif isinstance(data_alt, dict):
                                        eventos = data_alt.get("events", []) or data_alt.get("rows", [])
                                else:
                                    eventos = res_alt.get("rows", []) or res_alt.get("data", [])
                            
                            print(f"✅ [SISTEMA] API retornou {len(eventos)} eventos com sucesso (season_id).")
                            cache_jogos["api_events"] = {"data": eventos, "timestamp": agora}
                            return eventos
                        else:
                            print(f"⚠️ [SISTEMA] Erro na API alternativa (season_id): Código {r_alt.status}")
                else:
                    print(f"⚠️ [SISTEMA] Erro na API principal (seasons_id): Código {r.status}")
        except Exception as e:
            print(f"❌ [SISTEMA] Falha ao aceder à API de eventos: {e}")
    return []

async def obter_tabela_api(session, season_id, letra_grupo):
    cache_key = f"standings_{letra_grupo.upper()}"
    agora = time_module.time()
    if cache_key in cache_jogos:
        if agora - cache_jogos[cache_key]["timestamp"] < CACHE_EXPIRY:
            return cache_jogos[cache_key]["data"]

    url = "https://sofasport.p.rapidapi.com/v1/seasons/standings"
    params = {
        "seasons_id": str(season_id),
        "season_id": str(season_id),
        "unique_tournament_id": "16",
        "standing_type": "total"
    }
    
    async with api_semaphore:
        try:
            async with session.get(url, headers=HEADERS_API, params=params, timeout=15) as r:
                if r.status == 200:
                    res = await r.json()
                    grupos_data = []
                    if isinstance(res, dict):
                        grupos_data = res.get("data", []) or res.get("standings", [])
                        if isinstance(grupos_data, dict):
                            grupos_data = grupos_data.get("standings", []) or [grupos_data]
                    elif isinstance(res, list):
                        grupos_data = res
                        
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

    async with aiohttp.ClientSession() as session:
        season_id = await obter_season_id(session)
        eventos_api = await obter_resultados_api(session, season_id)
        
        for j_csv in jogos_do_dia:
            encontrou = True
            nome_jogo = j_csv["jogo"]
            hora = j_csv["hora"]
            canal = j_csv["canal"]
            
            partes = [p.strip() for p in re.split(r'\s*[\s\xa0]+(?:[xX×]|vs\.?|[-–—])[\s\xa0]+\s*', nome_jogo)]
            resultado_str = "vs"
            status_direto = ""
            
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                match_api = None
                for ev in eventos_api:
                    api_casa = ev.get("homeTeam", {}).get("name") or ev.get("homeTeam", {}).get("shortName") or ""
                    api_fora = ev.get("awayTeam", {}).get("name") or ev.get("awayTeam", {}).get("shortName") or ""
                    
                    # Filtra apenas por jogos de 2026 para evitar colisões com torneios anteriores
                    ts = ev.get("startTimestamp")
                    if ts and datetime.fromtimestamp(ts, tz=timezone.utc).year == 2026:
                        if equipas_correspondem(casa, fora, api_casa, api_fora):
                            match_api = ev
                            break
                
                if match_api:
                    gc_val = match_api.get("homeScore")
                    gf_val = match_api.get("awayScore")
                    
                    gc, gf = None, None
                    if isinstance(gc_val, dict): gc = gc_val.get("current") or gc_val.get("display")
                    elif isinstance(gc_val, (int, str)): gc = gc_val
                        
                    if isinstance(gf_val, dict): gf = gf_val.get("current") or gf_val.get("display")
                    elif isinstance(gf_val, (int, str)): gf = gf_val

                    if gc is not None and gf is not None:
                        resultado_str = f"**{gc}** - **{gf}**"
                        status_type = match_api.get("status", {}).get("type", "")
                        status_desc = match_api.get("status", {}).get("description", "")
                        if status_type == "inprogress":
                            status_direto = f" 🟢 *({status_desc})*"
                        elif status_type == "finished":
                            status_direto = " 🔴 *(Terminado)*"
            
            nome_jogo_formatado = f"**{casa}** {resultado_str} **{fora}**{status_direto}" if len(partes) == 2 else f"**{nome_jogo}**"
            
            embed.add_field(
                name=f"🥅 Grupo {j_csv['grupo']} — {j_csv['fase']}",
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
    jogos_filtrados = [j for j in jogos_csv if equipa_no_jogo(nome_selecao, j["jogo"])]
    
    if not jogos_filtrados:
        aviso = f"⚠️ Não encontrei nenhum jogo agendado para a seleção de **{nome_selecao}** no calendário do Mundial."
        if msg: await msg.edit(content=aviso)
        else: await canal_ou_ctx.send(aviso)
        return

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
        
        for j_csv in jogos_filtrados:
            nome_jogo = j_csv["jogo"]
            hora = j_csv["hora"]
            canal = j_csv["canal"]
            data = j_csv["data"]
            
            partes = [p.strip() for p in re.split(r'\s*[\s\xa0]+(?:[xX×]|vs\.?|[-–—])[\s\xa0]+\s*', nome_jogo)]
            resultado_str = "vs"
            status_direto = ""
            
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                match_api = None
                for ev in eventos_api:
                    api_casa = ev.get("homeTeam", {}).get("name") or ev.get("homeTeam", {}).get("shortName") or ""
                    api_fora = ev.get("awayTeam", {}).get("name") or ev.get("awayTeam", {}).get("shortName") or ""
                    
                    ts = ev.get("startTimestamp")
                    if ts and datetime.fromtimestamp(ts, tz=timezone.utc).year == 2026:
                        if equipas_correspondem(casa, fora, api_casa, api_fora):
                            match_api = ev
                            break
                
                if match_api:
                    gc_val = match_api.get("homeScore")
                    gf_val = match_api.get("awayScore")
                    
                    gc, gf = None, None
                    if isinstance(gc_val, dict): gc = gc_val.get("current") or gc_val.get("display")
                    elif isinstance(gc_val, (int, str)): gc = gc_val
                        
                    if isinstance(gf_val, dict): gf = gf_val.get("current") or gf_val.get("display")
                    elif isinstance(gf_val, (int, str)): gf = gf_val

                    if gc is not None and gf is not None:
                        resultado_str = f"**{gc}** - **{gf}**"
                        status_type = match_api.get("status", {}).get("type", "")
                        status_desc = match_api.get("status", {}).get("description", "")
                        if status_type == "inprogress":
                            status_direto = f" 🟢 *({status_desc})*"
                        elif status_type == "finished":
                            status_direto = " 🔴 *(Terminado)*"
                            
            nome_jogo_formatado = f"**{casa}** {resultado_str} **{fora}**{status_direto}" if len(partes) == 2 else f"**{nome_jogo}**"
            
            embed.add_field(
                name=f"📅 {data} @ {hora} (Grupo {j_csv['grupo']})",
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
            gm = r.get("goalsFor", 0)
            gs = r.get("goalsAgainst", 0)
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
        
        linhas_jogos = []
        for j_g in jogos_grupo:
            nome_jogo = j_g["jogo"]
            partes = [p.strip() for p in re.split(r'\s*[\s\xa0]+(?:[xX×]|vs\.?|[-–—])[\s\xa0]+\s*', nome_jogo)]
            resultado_str = "vs"
            status_direto = ""
            
            if len(partes) == 2:
                casa, fora = traduzir_nome_equipa(partes[0]), traduzir_nome_equipa(partes[1])
                match_api = None
                for ev in eventos_api:
                    api_casa = ev.get("homeTeam", {}).get("name") or ev.get("homeTeam", {}).get("shortName") or ""
                    api_fora = ev.get("awayTeam", {}).get("name") or ev.get("awayTeam", {}).get("shortName") or ""
                    
                    ts = ev.get("startTimestamp")
                    if ts and datetime.fromtimestamp(ts, tz=timezone.utc).year == 2026:
                        if equipas_correspondem(casa, fora, api_casa, api_fora):
                            match_api = ev
                            break
                if match_api:
                    gc_val = match_api.get("homeScore")
                    gf_val = match_api.get("awayScore")
                    
                    gc, gf = None, None
                    if isinstance(gc_val, dict): gc = gc_val.get("current") or gc_val.get("display")
                    elif isinstance(gc_val, (int, str)): gc = gc_val
                        
                    if isinstance(gf_val, dict): gf = gf_val.get("current") or gf_val.get("display")
                    elif isinstance(gf_val, (int, str)): gf = gf_val

                    if gc is not None and gf is not None:
                        resultado_str = f"**{gc}** - **{gf}**"
                        status_type = match_api.get("status", {}).get("type", "")
                        status_desc = match_api.get("status", {}).get("description", "")
                        if status_type == "inprogress":
                            status_direto = f" 🟢 *({status_desc})*"
                        elif status_type == "finished":
                            status_direto = " 🔴 *(Terminado)*"
                        
            jogo_f = f"**{casa}** {resultado_str} **{fora}**{status_direto}" if len(partes) == 2 else nome_jogo
            linhas_jogos.append(f"📅 {j_g['data']} @ {j_g['hora']} — {jogo_f} *(📺 {j_g['canal']})*")
            
        embed.add_field(name="🥅 Calendário & Resultados", value="\n".join(linhas_jogos), inline=False)
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
    embed.add_field(name="⚽ Seleções Nacionais", value="Comandos diretos para TODAS as seleções do Mundial (Ex: `!portugal`, `!brasil`, `!argentina`, `!alemanha`, `!marrocos`, etc.) ou pesquisa genérica: `!selecao <nome>`", inline=False)
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'✅ Bot Mundial 2026 Híbrido Compacto Online!')
    if not notificacao_diaria.is_running():
        notificacao_diaria.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)