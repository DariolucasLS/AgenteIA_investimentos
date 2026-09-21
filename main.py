import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai
import yfinance as yf

# ==========================================
# 1. CONFIGURAÇÕES E PARÂMETROS
# ==========================================
TICKERS = ["PETR4.SA", "VALE3.SA", "ITUB4.SA"]
RECEIVERS = ["lima.poliane90@gmail.com", "darilis1337@gmail.com"]

# No GitHub Actions, lemos as variáveis do sistema (os.environ)
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


# ==========================================
# 2. COLETA E PROCESSAMENTO DOS DADOS (MATEMÁTICA PRECISA)
# ==========================================
def processar_dados_acoes(tickers):
    dados_acoes = []
    texto_resumo_ia = ""

    for ticker in tickers:
        acao = yf.Ticker(ticker)
        hist = acao.history(period="5d")

        if len(hist) >= 2:
            preco_atual = hist["Close"].iloc[-1]
            preco_anterior = hist["Close"].iloc[-2]
            variacao = ((preco_atual - preco_anterior) / preco_anterior) * 100
            volume = hist["Volume"].iloc[-1]
            mm5 = hist["Close"].mean()
            diff_mm5 = ((preco_atual - mm5) / mm5) * 100

            vol_str = (
                f"{volume/1e6:.1f}M" if volume >= 1e6 else f"{volume/1e3:.1f}K"
            )
            status_mm5 = "Acima" if preco_atual >= mm5 else "Abaixo"

            item = {
                "ticker": ticker,
                "preco_atual": preco_atual,
                "variacao": variacao,
                "volume_str": vol_str,
                "mm5": mm5,
                "diff_mm5": diff_mm5,
                "status_mm5": status_mm5,
            }
            dados_acoes.append(item)

            texto_resumo_ia += (
                f"Ativo: {ticker} | Preço: R$ {preco_atual:.2f} | "
                f"Variação: {variacao:+.2f}% | Vol: {vol_str} | "
                f"MM5: R$ {mm5:.2f} ({status_mm5} {diff_mm5:+.2f}%)\n"
            )

    return dados_acoes, texto_resumo_ia


# ==========================================
# 3. GERAÇÃO DO CONTEÚDO TEXTUAL VIA GEMINI (JSON)
# ==========================================
def gerar_textos_ia(texto_dados):
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    Você é um analista financeiro sênior. Com base nos dados abaixo, responda EXCLUSIVAMENTE em formato JSON com o seguinte esquema:

    {{
      "altas": [
        {{"ticker": "NOME.SA", "justificativa": "Texto curto justificando a alta com base nos dados"}}
      ],
      "baixas": [
        {{"ticker": "NOME.SA", "justificativa": "Texto curto justificando a baixa com base nos dados"}}
      ],
      "resumo_tecnico_geral": "Uma frase resumindo o comportamento geral do grupo frente à MM5 (ex: Todos os três ativos estão negociando abaixo de suas respectivas MM5...)",
      "ponto_atencao_titulo": "Título em negrito (ex: Cautela com Entradas Imediatas:)",
      "ponto_atencao_texto": "Texto explicativo curto sobre o momento do mercado.",
      "recomendacao": "Orientação clara do que fazer no momento.",
      "destaque_operacional": "Comentário específico focado em 1 ou 2 papéis principais."
    }}

    Dados de hoje:
    {texto_dados}
    """

    config = {"response_mime_type": "application/json", "temperature": 0.1}

    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash", contents=prompt, config=config
        )
        return json.loads(response.text)
    except Exception as e:
        response = client.models.generate_content(
            model="gemini-2.5-pro", contents=prompt, config=config
        )
        return json.loads(response.text)


# ==========================================
# 4. MONTAGEM DO HTML IDENTICO À IMAGEM
# ==========================================
def construir_html_exacto(dados_acoes, dados_ia):
    html_altas = ""
    if dados_ia.get("altas"):
        html_altas += '<li><b style="color: #27ae60;">Alta:</b> '
        itens = []
        for a in dados_ia["altas"]:
            d = next(
                (x for x in dados_acoes if x["ticker"] == a["ticker"]), None
            )
            var_str = (
                f"({d['variacao']:+.2f}% | R$ {d['preco_atual']:.2f})"
                if d
                else ""
            )
            itens.append(
                f'<a href="#" style="color: #0066cc; text-decoration: underline; font-weight: bold;">{a["ticker"]}</a> {var_str} — {a["justificativa"]}'
            )
        html_altas += ", ".join(itens) + "</li>"

    html_baixas = ""
    if dados_ia.get("baixas"):
        html_baixas += '<li><b style="color: #c0392b;">Baixas:</b><ul>'
        for b in dados_ia["baixas"]:
            d = next(
                (x for x in dados_acoes if x["ticker"] == b["ticker"]), None
            )
            var_str = (
                f"({d['variacao']:+.2f}% | R$ {d['preco_atual']:.2f})"
                if d
                else ""
            )
            html_baixas += f'<li><a href="#" style="color: #0066cc; text-decoration: underline; font-weight: bold;">{b["ticker"]}</a> {var_str} — {b["justificativa"]}</li>'
        html_baixas += "</ul></li>"

    linhas_tabela = ""
    for acao in dados_acoes:
        cor_status = (
            "#c0392b" if acao["status_mm5"] == "Abaixo" else "#27ae60"
        )
        linhas_tabela += f"""
        <tr style="border-bottom: 1px solid #eeeeee;">
            <td style="padding: 10px; color: #0066cc; font-weight: bold; text-decoration: underline;">{acao['ticker']}</td>
            <td style="padding: 10px; color: #333333;">R$ {acao['preco_atual']:.2f}</td>
            <td style="padding: 10px; color: #333333;">R$ {acao['mm5']:.2f}</td>
            <td style="padding: 10px; color: {cor_status}; font-weight: bold;">{acao['status_mm5']} ({acao['diff_mm5']:+.2f}%)</td>
        </tr>
        """

    html_final = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: Arial, sans-serif; color: #333333; background-color: #f8f9fa; padding: 20px;">
        <div style="max-width: 680px; margin: 0 auto; background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; border-radius: 6px;">

            <h2 style="color: #0b2545; font-size: 22px; margin-top: 0; margin-bottom: 5px;">Relatório Diário de Análise de Mercado</h2>
            <hr style="border: none; border-top: 2px solid #0b2545; margin-bottom: 15px;">
            <p style="color: #666666; font-size: 12px; margin-top: 0; margin-bottom: 25px;">
                <b>Público-alvo:</b> Investidores monitorando pontos de entrada | <b>Foco:</b> PETR4, VALE3, ITUB4
            </p>

            <h3 style="color: #0056b3; font-size: 16px; margin-bottom: 15px;">1. Destaques do Dia</h3>
            <ul style="font-size: 13px; line-height: 1.6; padding-left: 20px;">
                {html_altas}
                {html_baixas}
            </ul>

            <h3 style="color: #0056b3; font-size: 16px; margin-top: 25px; margin-bottom: 10px;">2. Contexto Técnico Básico (Média Móvel de 5 Dias)</h3>
            <p style="font-size: 13px; color: #333333; line-height: 1.5;">{dados_ia.get('resumo_tecnico_geral', '')}</p>

            <table style="width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 15px; text-align: left;">
                <thead>
                    <tr style="background-color: #f2f2f2; font-weight: bold; color: #333333;">
                        <th style="padding: 10px;">Ação</th>
                        <th style="padding: 10px;">Preço Atual</th>
                        <th style="padding: 10px;">MM5 Dias</th>
                        <th style="padding: 10px;">Status vs MM5</th>
                    </tr>
                </thead>
                <tbody>
                    {linhas_tabela}
                </tbody>
            </table>

            <h3 style="color: #0056b3; font-size: 16px; margin-top: 30px; margin-bottom: 15px;">3. Ponto de Atenção Antes de Comprar</h3>
            <div style="background-color: #fff9e6; border-left: 4px solid #f39c12; padding: 15px; font-size: 13px; line-height: 1.6;">
                <b>{dados_ia.get('ponto_atencao_titulo', '')}</b> {dados_ia.get('ponto_atencao_texto', '')}
                <ul style="margin-top: 10px; margin-bottom: 0; padding-left: 20px;">
                    <li><b>Recomendação:</b> {dados_ia.get('recomendacao', '')}</li>
                    <li><b>Destaque Operacional:</b> {dados_ia.get('destaque_operacional', '')}</li>
                </ul>
            </div>

        </div>
    </body>
    </html>
    """
    return html_final


# ==========================================
# 5. ENVIO DO E-MAIL VIA SMTP
# ==========================================
def enviar_email(corpo_html, destinatarios):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "📈 Relatório Diário de Análise de Mercado"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(destinatarios)

    msg.attach(MIMEText(corpo_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, destinatarios, msg.as_string())
    print("E-mail enviado com sucesso")


# ==========================================
# EXECUÇÃO DO FLUXO
# ==========================================
if __name__ == "__main__":
    dados_acoes, texto_dados = processar_dados_acoes(TICKERS)
    dados_ia = gerar_textos_ia(texto_dados)
    html_pronto = construir_html_exacto(dados_acoes, dados_ia)
    enviar_email(html_pronto, RECEIVERS)