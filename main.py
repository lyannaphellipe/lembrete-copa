import requests
import os
import schedule
import time
import threading
from datetime import datetime, timedelta
from supabase import create_client
from flask import Flask, request

RESEND_API_KEY = os.environ.get("RESEND_API_KEY")
FOOTBALLDATA_KEY = os.environ.get("FOOTBALLDATA_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
MODO_TESTE = os.environ.get("TEST", "false").lower() == "true"
MODO_TESTE_ALL = os.environ.get("TEST_ALL", "false").lower() == "true"
BASE_URL = os.environ.get("BASE_URL", "https://lembrete-copa-production.up.railway.app")

TRANSMISSOES = {
    "Brazil": ["Globo", "SporTV", "CazéTV"],
    "Mexico": ["SporTV", "CazéTV"],
    "USA": ["SporTV", "CazéTV"],
    "Canada": ["SporTV", "CazéTV"],
    "default": ["SporTV", "CazéTV"]
}

BANDEIRAS = {
    "Brazil": "🇧🇷", "Argentina": "🇦🇷", "France": "🇫🇷", "Germany": "🇩🇪",
    "Spain": "🇪🇸", "Portugal": "🇵🇹", "England": "🇬🇧", "Uruguay": "🇺🇾",
    "Mexico": "🇲🇽", "USA": "🇺🇸", "Canada": "🇨🇦", "Japan": "🇯🇵",
    "South Korea": "🇰🇷", "Morocco": "🇲🇦", "Netherlands": "🇳🇱",
    "Belgium": "🇧🇪", "Croatia": "🇭🇷", "Senegal": "🇸🇳",
    "Ecuador": "🇪🇨", "Switzerland": "🇨🇭", "Serbia": "🇷🇸",
    "Costa Rica": "🇨🇷", "Paraguay": "🇵🇾", "Chile": "🇨🇱",
    "Colombia": "🇨🇴", "Venezuela": "🇻🇪", "Peru": "🇵🇪",
    "Saudi Arabia": "🇸🇦", "Iran": "🇮🇷", "Qatar": "🇶🇦",
    "Australia": "🇦🇺", "Poland": "🇵🇱", "Denmark": "🇩🇰",
    "Bosnia and Herzegovina": "🇧🇦", "South Africa": "🇿🇦",
    "Czech Republic": "🇨🇿", "Haiti": "🇭🇹", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Albania": "🇦🇱", "Austria": "🇦🇹", "Hungary": "🇭🇺",
    "Romania": "🇷🇴", "Slovakia": "🇸🇰", "Slovenia": "🇸🇮",
    "Ukraine": "🇺🇦", "Turkey": "🇹🇷", "Greece": "🇬🇷",
    "Nigeria": "🇳🇬", "Egypt": "🇪🇬", "Cameroon": "🇨🇲",
    "Ghana": "🇬🇭", "Tunisia": "🇹🇳", "Algeria": "🇩🇿",
    "New Zealand": "🇳🇿", "Indonesia": "🇮🇩", "China PR": "🇨🇳",
    "default": "🏳️"
}

app = Flask(__name__)

def bandeira(pais):
    return BANDEIRAS.get(pais, BANDEIRAS["default"])

def headers_api():
    return {"X-Auth-Token": FOOTBALLDATA_KEY}

def data_brasilia(delta_dias=0):
    agora_br = datetime.utcnow() - timedelta(hours=3)
    alvo = agora_br + timedelta(days=delta_dias)
    return alvo.strftime("%Y-%m-%d")

def buscar_jogos_por_dia_brasilia(data_br):
    # Busca cobrindo o dia inteiro em Brasília = UTC-3
    # Um dia em Brasília vai de 03:00 UTC até 03:00 UTC do dia seguinte
    date_from = data_br  # 00:00 Brasília = 03:00 UTC = ainda data_br em UTC
    # Para cobrir até meia-noite de Brasília precisamos pegar o dia seguinte em UTC
    dt = datetime.strptime(data_br, "%Y-%m-%d")
    date_to_utc = (dt + timedelta(days=1)).strftime("%Y-%m-%d")

    url = f"https://api.football-data.org/v4/competitions/WC/matches?dateFrom={data_br}&dateTo={date_to_utc}"
    try:
        r = requests.get(url, headers=headers_api(), timeout=15)
        print(f"API status: {r.status_code} para {data_br}")
        if r.status_code == 200:
            todos = r.json().get("matches", [])
            # Filtra apenas jogos cujo horário em Brasília cai no dia correto
            jogos_do_dia = []
            for j in todos:
                utc_str = j.get("utcDate", "")
                try:
                    dt_utc = datetime.strptime(utc_str[:19], "%Y-%m-%dT%H:%M:%S")
                    dt_br = dt_utc - timedelta(hours=3)
                    if dt_br.strftime("%Y-%m-%d") == data_br:
                        jogos_do_dia.append(j)
                except:
                    pass
            print(f"Jogos em horário Brasília para {data_br}: {len(jogos_do_dia)}")
            return jogos_do_dia
        else:
            print(f"Erro API: {r.status_code} - {r.text[:300]}")
    except Exception as e:
        print(f"Erro ao buscar {data_br}: {e}")
    return []

def converter_horario_utc(utc_str):
    try:
        dt = datetime.strptime(utc_str[:19], "%Y-%m-%dT%H:%M:%S")
        dt_br = dt - timedelta(hours=3)
        return dt_br.strftime("%Hh%M")
    except:
        return "horário a confirmar"

def montar_resumo_jogo(jogo):
    status = jogo.get("status", "")
    if status != "FINISHED":
        return ""
    home = jogo.get("homeTeam", {}).get("name", "")
    away = jogo.get("awayTeam", {}).get("name", "")
    ft = jogo.get("score", {}).get("fullTime", {})
    gols_home = ft.get("home", 0) or 0
    gols_away = ft.get("away", 0) or 0
    gols_home_lista = []
    gols_away_lista = []
    for g in jogo.get("goals", []):
        if g.get("type") == "OWN_GOAL":
            continue
        scorer = g.get("scorer", {}).get("name", "")
        minuto = g.get("minute", "")
        team = g.get("team", {}).get("name", "")
        entrada = f"{scorer} ({minuto}')"
        if team == home:
            gols_home_lista.append(entrada)
        else:
            gols_away_lista.append(entrada)
    html = f"""
    <div style="margin-bottom:14px;padding:14px 16px;background:#f8f9fa;border-radius:8px;border-left:4px solid #1a73e8;">
        <p style="margin:0 0 4px;font-size:15px;font-weight:bold;">
            {bandeira(home)} {home} {gols_home} x {gols_away} {away} {bandeira(away)}
        </p>"""
    if gols_home_lista:
        html += f'<p style="margin:2px 0;font-size:12px;color:#555;">⚽ {", ".join(gols_home_lista)}</p>'
    if gols_away_lista:
        html += f'<p style="margin:2px 0;font-size:12px;color:#555;">⚽ {", ".join(gols_away_lista)}</p>'
    html += "</div>"
    return html

def montar_jogo_programado(jogo):
    status = jogo.get("status", "")
    if status == "FINISHED":
        return ""
    home = jogo.get("homeTeam", {}).get("name", "")
    away = jogo.get("awayTeam", {}).get("name", "")
    horario = converter_horario_utc(jogo.get("utcDate", ""))
    venue = jogo.get("venue", "") or ""
    canais = TRANSMISSOES.get("Brazil") if "Brazil" in [home, away] else TRANSMISSOES["default"]
    return f"""
    <div style="margin-bottom:12px;padding:14px 16px;background:#fff;border-radius:8px;border:1px solid #e0e0e0;">
        <p style="margin:0 0 4px;font-size:15px;font-weight:bold;">
            {bandeira(home)} {home} x {away} {bandeira(away)}
        </p>
        <p style="margin:2px 0;font-size:12px;color:#555;">🕐 {horario} · {"📍 " + venue + " · " if venue else ""}📺 {" · ".join(canais)}</p>
    </div>"""

def montar_secao(titulo, cor, blocos):
    if not blocos:
        return ""
    n = len(blocos)
    plural = "s" if n > 1 else ""
    return f"""
    <h2 style="font-size:15px;font-weight:bold;color:#333;border-bottom:2px solid {cor};padding-bottom:6px;margin-top:24px;margin-bottom:12px;">
        {titulo} ({n} jogo{plural})
    </h2>{"".join(blocos)}"""

def montar_email(jogos_ontem, jogos_hoje, jogos_amanha, email_destinatario):
    hoje_br = datetime.utcnow() - timedelta(hours=3)
    meses = ["janeiro","fevereiro","março","abril","maio","junho",
             "julho","agosto","setembro","outubro","novembro","dezembro"]
    data_str = f"{hoje_br.day} de {meses[hoje_br.month-1]} de {hoje_br.year}"
    modo = " <em style='color:#e67e22;'>[TESTE]</em>" if (MODO_TESTE or MODO_TESTE_ALL) else ""
    link_cancelar = f"{BASE_URL}/cancelar?email={email_destinatario}"

    blocos_ontem = [b for b in [montar_resumo_jogo(j) for j in jogos_ontem] if b]
    blocos_hoje = [b for b in [montar_jogo_programado(j) for j in jogos_hoje] if b]
    blocos_amanha = [b for b in [montar_jogo_programado(j) for j in jogos_amanha] if b]

    secao_ontem = montar_secao("📋 Resultados de ontem", "#1a73e8", blocos_ontem) or '<p style="color:#888;font-size:13px;">Não houve jogos ontem.</p>'
    secao_hoje = montar_secao("⚽ Jogos de hoje", "#27ae60", blocos_hoje) or '<p style="color:#888;font-size:13px;margin-top:16px;">Sem jogos hoje.</p>'
    secao_amanha = montar_secao("📅 Jogos de amanhã", "#e67e22", blocos_amanha)

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:580px;margin:auto;padding:20px;color:#222;">
        <div style="background:linear-gradient(135deg,#1a73e8,#27ae60);padding:18px 20px;border-radius:10px;margin-bottom:20px;">
            <h1 style="color:white;margin:0;font-size:20px;">🏆 Copa do Mundo 2026{modo}</h1>
            <p style="color:rgba(255,255,255,0.9);margin:4px 0 0;font-size:14px;">Bom dia! Hoje é <strong>{data_str}</strong></p>
        </div>
        {secao_ontem}
        {secao_hoje}
        {secao_amanha}
        <p style="font-size:11px;color:#bbb;margin-top:28px;border-top:1px solid #eee;padding-top:10px;">
            Projeto Lembrete Copa 2026 · <a href="{link_cancelar}" style="color:#bbb;">Cancelar inscrição</a>
        </p>
    </div>"""

def buscar_emails():
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        result = supabase.table("subscribers").select("email").eq("ativo", True).execute()
        return [row["email"] for row in result.data]
    except Exception as e:
        print(f"Erro ao buscar emails: {e}")
        return []

def enviar_email(destinatario, html):
    hoje_br = datetime.utcnow() - timedelta(hours=3)
    meses = ["jan","fev","mar","abr","mai","jun","jul","ago","set","out","nov","dez"]
    assunto = f"⚽ Copa 2026 — {hoje_br.day} de {meses[hoje_br.month-1]}"
    if MODO_TESTE or MODO_TESTE_ALL:
        assunto += " [TESTE]"
    response = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json={"from": "Copa 2026 <onboarding@resend.dev>", "to": [destinatario], "subject": assunto, "html": html}
    )
    if response.status_code == 200:
        print(f"Enviado para {destinatario}")
        return True
    else:
        print(f"Erro {destinatario}: {response.status_code} - {response.text[:200]}")
        return False

def executar():
    print(f"\n=== RODANDO BR: {datetime.utcnow() - timedelta(hours=3)} ===")
    data_ontem = data_brasilia(-1)
    data_hoje = data_brasilia(0)
    data_amanha = data_brasilia(1)
    print(f"Buscando: ontem={data_ontem} hoje={data_hoje} amanha={data_amanha}")

    jogos_ontem = buscar_jogos_por_dia_brasilia(data_ontem)
    jogos_hoje = buscar_jogos_por_dia_brasilia(data_hoje)
    jogos_amanha = buscar_jogos_por_dia_brasilia(data_amanha)

    if MODO_TESTE:
        emails = [os.environ.get("EMAIL_DESTINATARIO")]
    else:
        emails = buscar_emails()
        if MODO_TESTE_ALL:
            print(f"TEST_ALL: {len(emails)} cadastrados")

    print(f"Enviando para {len(emails)} email(s)...")
    ok = 0
    for email in emails:
        html = montar_email(jogos_ontem, jogos_hoje, jogos_amanha, email)
        if enviar_email(email, html):
            ok += 1
    print(f"Resultado: {ok}/{len(emails)} enviados")

@app.route("/")
def home():
    return "Lembrete Copa 2026 rodando."

@app.route("/cancelar")
def cancelar():
    email = request.args.get("email", "").strip().lower()
    if not email or "@" not in email:
        return "<html><body style='font-family:Arial;text-align:center;padding:60px;'><h2>Link inválido</h2></body></html>", 400
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        supabase.table("subscribers").update({"ativo": False}).eq("email", email).execute()
        return f"<html><body style='font-family:Arial;text-align:center;padding:60px;color:#222;'><h2>✅ Cancelamento confirmado</h2><p>{email} removido da lista.</p></body></html>"
    except Exception as e:
        return "<html><body style='font-family:Arial;text-align:center;padding:60px;'><h2>Erro ao cancelar</h2></body></html>", 500

def rodar_scheduler():
    schedule.every().day.at("11:00").do(executar)
    print("Scheduler: 11:00 UTC = 08:00 Brasília")
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    executar()
    t = threading.Thread(target=rodar_scheduler, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
