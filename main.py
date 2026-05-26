import requests
import json
import os
import schedule
import time
import threading
from datetime import datetime, timedelta
from supabase import create_client
from flask import Flask, request, jsonify

# --- CONFIGURAÇÕES ---
RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
APISPORTS_KEY = os.environ.get("APISPORTS_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
MODO_TESTE = os.environ.get("TEST", "false").lower() == "true"
MODO_TESTE_ALL = os.environ.get("TEST_ALL", "false").lower() == "true"
BASE_URL = os.environ.get("BASE_URL", "https://lembrete-copa.up.railway.app")

WORLD_CUP_LEAGUE = 1
WORLD_CUP_SEASON = 2026

TRANSMISSOES = {
    "Brazil": ["Globo", "SporTV", "CazéTV"],
    "default": ["SporTV", "CazéTV"]
}

BANDEIRAS = {
    "Brazil": "🇧🇷", "Argentina": "🇦🇷", "France": "🇫🇷", "Germany": "🇩🇪",
    "Spain": "🇪🇸", "Portugal": "🇵🇹", "England": "🇬🇧", "Uruguay": "🇺🇾",
    "Mexico": "🇲🇽", "USA": "🇺🇸", "Canada": "🇨🇦", "Japan": "🇯🇵",
    "South Korea": "🇰🇷", "Morocco": "🇲🇦", "Netherlands": "🇳🇱",
    "Belgium": "🇧🇪", "Croatia": "🇭🇷", "Senegal": "🇸🇳",
    "default": "🏳️"
}

app = Flask(__name__)

# --- FLASK ROUTES ---

@app.route("/")
def home():
    return "Lembrete Copa 2026 rodando."

@app.route("/cancelar")
def cancelar():
    email = request.args.get("email", "").strip().lower()
    if not email or "@" not in email:
        return """
        <html><body style="font-family:Arial;text-align:center;padding:60px;">
        <h2>❌ Link inválido</h2>
        <p>Email não encontrado. Tente novamente.</p>
        </body></html>
        """, 400

    try:
        service_key = os.environ.get("SUPABASE_SERVICE_KEY")
        supabase = create_client(SUPABASE_URL, service_key)
        supabase.table("subscribers").update({"ativo": False}).eq("email", email).execute()
        return f"""
        <html><body style="font-family:Arial;text-align:center;padding:60px;color:#222;">
        <h2>✅ Cancelamento confirmado</h2>
        <p>O email <strong>{email}</strong> foi removido da lista.</p>
        <p style="color:#888;font-size:13px;">Você não receberá mais emails do Lembrete Copa 2026.</p>
        </body></html>
        """
    except Exception as e:
        return f"""
        <html><body style="font-family:Arial;text-align:center;padding:60px;">
        <h2>❌ Erro ao cancelar</h2>
        <p>Tente novamente mais tarde.</p>
        </body></html>
        """, 500

# --- FUNÇÕES ---

def bandeira(pais):
    return BANDEIRAS.get(pais, BANDEIRAS["default"])

def headers_api():
    return {
        "x-apisports-key": APISPORTS_KEY,
        "x-rapidapi-host": "v3.football.api-sports.io"
    }

def buscar_jogos_ontem():
    ontem = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?league={WORLD_CUP_LEAGUE}&season={WORLD_CUP_SEASON}&date={ontem}"
    r = requests.get(url, headers=headers_api(), timeout=10)
    if r.status_code == 200:
        return r.json().get("response", [])
    return []

def buscar_jogos_hoje():
    hoje = datetime.now().strftime("%Y-%m-%d")
    url = f"https://v3.football.api-sports.io/fixtures?league={WORLD_CUP_LEAGUE}&season={WORLD_CUP_SEASON}&date={hoje}"
    r = requests.get(url, headers=headers_api(), timeout=10)
    if r.status_code == 200:
        return r.json().get("response", [])
    return []

def buscar_eventos_jogo(fixture_id):
    url = f"https://v3.football.api-sports.io/fixtures/events?fixture={fixture_id}"
    r = requests.get(url, headers=headers_api(), timeout=10)
    if r.status_code == 200:
        return r.json().get("response", [])
    return []

def converter_horario(utc_str):
    try:
        dt = datetime.strptime(utc_str[:19], "%Y-%m-%dT%H:%M:%S")
        dt_brasilia = dt - timedelta(hours=3)
        return dt_brasilia.strftime("%Hh%M")
    except:
        return "horário a confirmar"

def montar_resumo_jogo(jogo):
    fixture = jogo.get("fixture", {})
    teams = jogo.get("teams", {})
    goals = jogo.get("goals", {})

    home = teams.get("home", {}).get("name", "")
    away = teams.get("away", {}).get("name", "")
    gols_home = goals.get("home", 0) or 0
    gols_away = goals.get("away", 0) or 0
    fixture_id = fixture.get("id")

    eventos = buscar_eventos_jogo(fixture_id)

    gols_home_lista = []
    gols_away_lista = []
    cartoes = []

    for e in eventos:
        tipo = e.get("type", "")
        detalhe = e.get("detail", "")
        minuto = e.get("time", {}).get("elapsed", "")
        jogador = e.get("player", {}).get("name", "")
        team_id = e.get("team", {}).get("id")
        home_id = teams.get("home", {}).get("id")

        if tipo == "Goal" and detalhe != "Missed Penalty":
            entrada = f"{jogador} ({minuto}')"
            if team_id == home_id:
                gols_home_lista.append(entrada)
            else:
                gols_away_lista.append(entrada)

        if tipo == "Card":
            emoji = "🟨" if "Yellow" in detalhe else "🟥"
            cartoes.append(f"{emoji} {jogador} ({minuto}')")

    gols_home_str = ", ".join(gols_home_lista) if gols_home_lista else ""
    gols_away_str = ", ".join(gols_away_lista) if gols_away_lista else ""
    cartoes_str = " | ".join(cartoes) if cartoes else ""

    html = f"""
    <div style="margin-bottom:20px;padding:16px;background:#f8f9fa;border-radius:8px;border-left:4px solid #1a73e8;">
        <p style="margin:0 0 6px;font-size:16px;font-weight:bold;">
            {bandeira(home)} {home} {gols_home} x {gols_away} {bandeira(away)} {away}
        </p>"""

    if gols_home_str:
        html += f'<p style="margin:2px 0;font-size:13px;color:#555;">⚽ {gols_home_str}</p>'
    if gols_away_str:
        html += f'<p style="margin:2px 0;font-size:13px;color:#555;">⚽ {gols_away_str}</p>'
    if cartoes_str:
        html += f'<p style="margin:4px 0;font-size:12px;color:#888;">{cartoes_str}</p>'

    html += "</div>"
    return html

def montar_jogo_hoje(jogo):
    fixture = jogo.get("fixture", {})
    teams = jogo.get("teams", {})
    home = teams.get("home", {}).get("name", "")
    away = teams.get("away", {}).get("name", "")
    horario_utc = fixture.get("date", "")
    horario = converter_horario(horario_utc)
    venue = fixture.get("venue", {}).get("name", "")
    city = fixture.get("venue", {}).get("city", "")

    canais = TRANSMISSOES.get("Brazil") if "Brazil" in [home, away] else TRANSMISSOES["default"]
    canais_str = " · ".join(canais)

    return f"""
    <div style="margin-bottom:16px;padding:16px;background:#fff;border-radius:8px;border:1px solid #e0e0e0;">
        <p style="margin:0 0 4px;font-size:15px;font-weight:bold;">
            {bandeira(home)} {home} x {bandeira(away)} {away}
        </p>
        <p style="margin:2px 0;font-size:13px;color:#555;">🕐 {horario} (horário de Brasília)</p>
        <p style="margin:2px 0;font-size:13px;color:#555;">📍 {venue}, {city}</p>
        <p style="margin:4px 0;font-size:13px;color:#1a73e8;">📺 {canais_str}</p>
    </div>"""

def montar_email(jogos_ontem, jogos_hoje, email_destinatario):
    hoje = datetime.now()
    meses = ["janeiro","fevereiro","março","abril","maio","junho",
             "julho","agosto","setembro","outubro","novembro","dezembro"]
    data_str = f"{hoje.day} de {meses[hoje.month-1]} de {hoje.year}"
    modo = " <em style='color:#e67e22;'>[TESTE]</em>" if MODO_TESTE else ""

    link_cancelar = f"{BASE_URL}/cancelar?email={email_destinatario}"

    secao_ontem = ""
    if jogos_ontem:
        blocos = "".join(montar_resumo_jogo(j) for j in jogos_ontem)
        secao_ontem = f"""
        <h2 style="font-size:16px;color:#333;border-bottom:2px solid #1a73e8;padding-bottom:6px;">
            📋 Resultados de ontem
        </h2>{blocos}"""
    else:
        secao_ontem = '<p style="color:#888;">Não houve jogos ontem.</p>'

    secao_hoje = ""
    if jogos_hoje:
        blocos = "".join(montar_jogo_hoje(j) for j in jogos_hoje)
        secao_hoje = f"""
        <h2 style="font-size:16px;color:#333;border-bottom:2px solid #27ae60;padding-bottom:6px;margin-top:28px;">
            ⚽ Jogos de hoje ({len(jogos_hoje)} jogo{'s' if len(jogos_hoje) > 1 else ''})
        </h2>{blocos}"""
    else:
        secao_hoje = '<p style="color:#888;margin-top:20px;">Não há jogos programados para hoje.</p>'

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;color:#222;">
        <div style="background:linear-gradient(135deg,#1a73e8,#27ae60);padding:20px;border-radius:10px;margin-bottom:24px;">
            <h1 style="color:white;margin:0;font-size:22px;">🏆 Copa do Mundo 2026{modo}</h1>
            <p style="color:rgba(255,255,255,0.9);margin:4px 0 0;">Bom dia! Hoje é <strong>{data_str}</strong></p>
        </div>
        {secao_ontem}
        {secao_hoje}
        <p style="font-size:11px;color:#aaa;margin-top:32px;border-top:1px solid #eee;padding-top:12px;">
            Projeto Lembrete Copa 2026 · 
            <a href="{link_cancelar}" style="color:#aaa;">Cancelar inscrição</a>
        </p>
    </div>"""

def buscar_emails():
    service_key = os.environ.get("SUPABASE_SERVICE_KEY")
    supabase = create_client(SUPABASE_URL, service_key)
    result = supabase.table("subscribers").select("email").eq("ativo", True).execute()
    return [row["email"] for row in result.data]

def enviar_email(destinatario, html):
    hoje = datetime.now()
    meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
    assunto = f"⚽ Copa 2026 — {hoje.day} de {meses[hoje.month-1]}"

    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={
            "from": "Copa 2026 <onboarding@resend.dev>",
            "to": [destinatario],
            "subject": assunto + (" [TESTE]" if MODO_TESTE else ""),
            "html": html
        }
    )
    return response.status_code == 200

def executar():
    print(f"Rodando em {datetime.now()} | Modo teste: {MODO_TESTE}")

    jogos_ontem = buscar_jogos_ontem()
    jogos_hoje = buscar_jogos_hoje()

    print(f"Jogos ontem: {len(jogos_ontem)} | Jogos hoje: {len(jogos_hoje)}")

    if MODO_TESTE:
        emails = [os.environ.get("EMAIL_DESTINATARIO")]
    elif MODO_TESTE_ALL:
        emails = buscar_emails()
        print(f"Modo TEST_ALL: enviando para todos os {len(emails)} cadastrados")
    else:
        emails = buscar_emails()

    print(f"Enviando para {len(emails)} email(s)...")
    ok = 0
    for email in emails:
        html = montar_email(jogos_ontem, jogos_hoje, email)
        if enviar_email(email, html):
            ok += 1
    print(f"Enviados: {ok}/{len(emails)}")

# --- AGENDAMENTO EM THREAD SEPARADA ---

def rodar_scheduler():
    schedule.every().day.at("08:00").do(executar)
    print("Scheduler iniciado. Rodando às 08:00 todos os dias...")
    while True:
        schedule.run_pending()
        time.sleep(60)

# --- INICIALIZAÇÃO ---

if __name__ == "__main__":
    executar()
    t = threading.Thread(target=rodar_scheduler, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
