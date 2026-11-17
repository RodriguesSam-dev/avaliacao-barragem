import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import re
import os

# ==============================================================================
# 1. CONFIGURAÇÕES DA SUA PLANILHA E MANUAL (AJUSTE ESTAS 5 LINHAS)
# ==============================================================================
URL_PLANILHA = "https://docs.google.com/spreadsheets/d/1tDMOb0KcUkk0pAnzZYnXuryrXC7Vj27vNqdwVnBfRmw/edit?usp=sharing"
ABA_CATALOGO = "catalogo"              # Nome exato da sua aba atual com as barragens
COL_CODIGO_BARRAGEM = "ID_Barragem"         # Nome exato da coluna com o código da barragem
COL_LINK_PDF = "Link_Ficha"            # Nome exato da coluna com o link do PDF
URL_MANUAL = "https://drive.google.com/file/d/10p8Z2BRxSa1o03oPqhKkvScYju3kmAY5/view?usp=sharing"
# ==============================================================================

st.set_page_config(page_title="Avaliação de Barragens", layout="wide")

# --- CONEXÃO COM GOOGLE SHEETS ---
@st.cache_resource
def conectar_planilha():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if os.path.exists("credenciais.json"):
        creds = Credentials.from_service_account_file("credenciais.json", scopes=scopes)
        url = URL_PLANILHA
    else:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], scopes=scopes
        )
        url = st.secrets["planilha_url"]
    client = gspread.authorize(creds)
    return client.open_by_url(url)

sheet = conectar_planilha()

@st.cache_data(ttl=300)
def carregar_catalogo():
    aba = sheet.worksheet(ABA_CATALOGO)
    df = pd.DataFrame(aba.get_all_records())
    df[COL_CODIGO_BARRAGEM] = df[COL_CODIGO_BARRAGEM].astype(str).str.strip()
    return df

@st.cache_data(ttl=120)
def carregar_codigos_validos():
    aba = sheet.worksheet("avaliadores")
    registros = aba.get_all_records()
    if not registros:
        return set()
    df = pd.DataFrame(registros)
    return set(df["codigo"].astype(str).str.strip().str.upper())

def carregar_avaliadas(codigo_avaliador):
    aba = sheet.worksheet("avaliacoes")
    registros = aba.get_all_records()
    if not registros:
        return set()
    df = pd.DataFrame(registros)
    df["avaliador"] = df["avaliador"].astype(str).str.strip().str.upper()
    df["codigo_barragem"] = df["codigo_barragem"].astype(str).str.strip()
    return set(df[df["avaliador"] == codigo_avaliador]["codigo_barragem"])

def converter_link_drive_preview(url):
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", str(url))
    if match:
        return f"https://drive.google.com/file/d/{match.group(1)}/preview"
    return url

# --- BARRA LATERAL: LOGIN POR CÓDIGO E PROGRESSO ---
st.sidebar.title("Acesso do Especialista")
codigo_digitado = st.sidebar.text_input("Código do avaliador:").strip().upper()

if not codigo_digitado:
    st.info("👈 Digite seu código de avaliador na barra lateral para iniciar ou retomar sua avaliação.")
    st.stop()

codigos_validos = carregar_codigos_validos()
if codigo_digitado not in codigos_validos:
    st.sidebar.error("Código não encontrado. Verifique se digitou corretamente.")
    st.stop()

# Reseta o sorteio caso outro avaliador faça login no mesmo navegador
if st.session_state.get("avaliador_ativo") != codigo_digitado:
    st.session_state["avaliador_ativo"] = codigo_digitado
    st.session_state.pop("barragem_atual", None)

# --- CÁLCULO DE PROGRESSO E PENDENTES ---
df_catalogo = carregar_catalogo()
avaliadas = carregar_avaliadas(codigo_digitado)
pendentes = df_catalogo[~df_catalogo[COL_CODIGO_BARRAGEM].isin(avaliadas)]

total = len(df_catalogo)
concluidas = len(avaliadas)

st.sidebar.success(f"Avaliador: **{codigo_digitado}**")
st.sidebar.progress(concluidas / total if total > 0 else 0)
st.sidebar.markdown(f"**Progresso:** {concluidas} de {total} barragens concluídas")

if pendentes.empty:
    st.balloons()
    st.success("🎉 Parabéns! Você concluiu a avaliação de todas as barragens.")
    st.stop()

# --- SORTEIO TRAVADO NA SESSÃO ---
if "barragem_atual" not in st.session_state or st.session_state["barragem_atual"] not in pendentes[COL_CODIGO_BARRAGEM].values:
    sorteada = pendentes.sample(n=1).iloc[0]
    st.session_state["barragem_atual"] = sorteada[COL_CODIGO_BARRAGEM]
    st.session_state["link_atual"] = sorteada[COL_LINK_PDF]

cod_barragem = st.session_state["barragem_atual"]
link_original = st.session_state["link_atual"]
link_preview = converter_link_drive_preview(link_original)
link_manual_preview = converter_link_drive_preview(URL_MANUAL)

# --- TELA PRINCIPAL (PDFs À ESQUERDA | AVALIAÇÃO À DIREITA) ---
col_pdf, col_form = st.columns([0.65, 0.35], gap="large")

with col_pdf:
    aba_ficha, aba_manual = st.tabs([
        f"📄 Ficha Técnica — Barragem {cod_barragem}",
        "📖 Manual de Características"
    ])

    with aba_ficha:
        st.components.v1.iframe(link_preview, height=740, scrolling=True)
        st.caption(f"Não carregou? [Abrir ficha em nova aba]({link_original})")

    with aba_manual:
        st.components.v1.iframe(link_manual_preview, height=740, scrolling=True)
        st.caption(f"Não carregou? [Abrir manual em nova aba]({URL_MANUAL})")

with col_form:
    st.subheader("Classificação")

    st.link_button(
        "↗️ Abrir Manual em Nova Aba (2º Monitor)",
        url=URL_MANUAL,
        use_container_width=True
    )

    st.divider()

    nota = st.slider(
        "Atribua a nota (0 a 100):",
        min_value=0,
        max_value=100,
        value=50,
        step=1,
        key=f"nota_{cod_barragem}"
    )
    st.caption("⬅️ **0:** Menos perigosa  |  **100:** Mais perigosa ➡️")

    if st.button("💾 Salvar e Sortear Próxima", type="primary", use_container_width=True):
        aba_avaliacoes = sheet.worksheet("avaliacoes")
        nova_linha = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            codigo_digitado,
            cod_barragem,
            nota
        ]
        aba_avaliacoes.append_row(nova_linha)
        
        st.session_state.pop("barragem_atual", None)
        st.toast(f"Barragem {cod_barragem} salva com nota {nota}!", icon="✅")
        st.rerun()
