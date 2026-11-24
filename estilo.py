"""Aparência do painel: cores, cartões, abas e componentes visuais."""
import html as _html

import streamlit as st

PLAT_COR = {"twitch": "#9146FF", "kick": "#53FC18", "youtube": "#FF4444"}
PLAT_NOME = {"twitch": "Twitch", "kick": "Kick", "youtube": "YouTube"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter', 'Segoe UI', system-ui, sans-serif; }
.stApp { background: radial-gradient(1200px 500px at 85% -10%, rgba(124,92,255,.16), transparent 60%), #0B0E17; }
.block-container { padding-top: 1.4rem; max-width: 1280px; }
header[data-testid="stHeader"] { background: transparent; }
h1, h2, h3 { letter-spacing: -0.02em; }
h2 { font-weight: 800 !important; }
h3 { font-weight: 700 !important; margin-top: .6rem; }

/* topo */
.hero { background: linear-gradient(135deg, #1c1547 0%, #11295a 55%, #0b4157 100%); border: 1px solid #2c3a66;
  border-radius: 20px; padding: 22px 28px; margin-bottom: 14px; display: flex; align-items: center; gap: 18px;
  box-shadow: 0 10px 40px rgba(20,10,70,.35); }
.hero .logo { font-size: 2.4rem; filter: drop-shadow(0 4px 14px rgba(124,92,255,.6)); }
.hero h1 { margin: 0; font-size: 1.85rem; font-weight: 800; color: #fff; }
.hero p { margin: 2px 0 0; color: #a9b8dd; font-size: .95rem; }

/* abas */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #222b40; }
.stTabs [data-baseweb="tab"] { height: 46px; padding: 0 16px; border-radius: 12px 12px 0 0; font-weight: 600; color: #9aa6c4; }
.stTabs [aria-selected="true"] { color: #fff; background: linear-gradient(180deg, rgba(124,92,255,.22), rgba(124,92,255,0)); }
.stTabs [data-baseweb="tab-highlight"] { background: linear-gradient(90deg, #7c5cff, #19c3fb); height: 3px; border-radius: 3px; }

/* métricas */
div[data-testid="stMetric"] { background: linear-gradient(180deg, #151b2c, #111624); border: 1px solid #232d47;
  border-radius: 16px; padding: 14px 16px; }
div[data-testid="stMetricLabel"] p { color: #94a0be; font-weight: 500; font-size: .82rem; }
div[data-testid="stMetricValue"] { font-weight: 800; letter-spacing: -0.02em; }

/* botões */
.stButton > button, .stDownloadButton > button, [data-testid="stFormSubmitButton"] > button {
  border-radius: 12px; font-weight: 600; border: 1px solid #2c3a66; background: #141a2b; transition: all .15s ease; }
.stButton > button:hover, .stDownloadButton > button:hover { border-color: #7c5cff; transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(124,92,255,.25); }
button[kind="primary"], button[data-testid="stBaseButton-primary"], [data-testid="stFormSubmitButton"] > button[kind="primaryFormSubmit"] {
  background: linear-gradient(135deg, #7c5cff, #19c3fb) !important; border: 0 !important; color: #fff !important; }

/* caixas */
[data-testid="stExpander"] { border: 1px solid #232d47; border-radius: 16px; background: #0f1422; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 18px; }
div[data-testid="stForm"] { border: 1px solid #232d47; border-radius: 18px; background: #0f1422; padding: 18px; }
[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; border: 1px solid #232d47; }
input, textarea, [data-baseweb="select"] > div { border-radius: 10px !important; }
div[data-testid="stAlert"] { border-radius: 14px; }

/* chips */
.chip { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; font-size: .74rem;
  font-weight: 700; letter-spacing: .01em; border: 1px solid transparent; }
.chip.ok { background: rgba(46,204,113,.14); color: #3ddc84; border-color: rgba(46,204,113,.35); }
.chip.warn { background: rgba(245,165,36,.14); color: #ffb84d; border-color: rgba(245,165,36,.35); }
.chip.err { background: rgba(255,93,93,.14); color: #ff7b7b; border-color: rgba(255,93,93,.35); }
.chip.live { background: rgba(255,68,68,.14); color: #ff6b6b; border-color: rgba(255,68,68,.35); }
.chip.live::before, .chip.ok::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor;
  animation: pulso 1.6s infinite; }
@keyframes pulso { 0%,100% { opacity: 1; } 50% { opacity: .25; } }

/* lista de verificação */
.check { display: flex; align-items: center; gap: 12px; padding: 10px 14px; margin: 6px 0; background: #111726;
  border: 1px solid #222c45; border-radius: 14px; }
.check .t { flex: 1; font-weight: 600; }
.check .d { color: #94a0be; font-size: .85rem; }

/* esteira */
.flow { display: flex; align-items: stretch; gap: 6px; flex-wrap: wrap; margin: 6px 0 12px; }
.flow .step { flex: 1; min-width: 120px; background: #111726; border: 1px solid #232d47; border-radius: 14px; padding: 10px 14px; }
.flow .step b { display: block; font-size: 1.5rem; font-weight: 800; color: #5b6685; }
.flow .step span { color: #94a0be; font-size: .76rem; font-weight: 600; }
.flow .step.on { border-color: rgba(124,92,255,.6); background: linear-gradient(180deg, rgba(124,92,255,.16), #111726); }
.flow .step.on b { color: #fff; }
.flow .seta { align-self: center; color: #3a4666; font-size: 1.3rem; }

/* grade de lives */
.live-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 14px; margin: 8px 0 16px; }
.live-card { position: relative; background: linear-gradient(180deg, #151b2c, #0f1422); border: 1px solid #232d47;
  border-radius: 18px; padding: 16px; overflow: hidden; transition: transform .15s, border-color .15s; }
.live-card:hover { transform: translateY(-2px); border-color: var(--cor); }
.live-card::before { content: ""; position: absolute; left: 0; top: 0; right: 0; height: 3px; background: var(--cor); }
.live-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.plat { padding: 3px 10px; border-radius: 8px; font-size: .72rem; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; }
.live-nome { font-size: 1.15rem; font-weight: 800; color: #fff; }
.live-jogo { color: #b7c2e0; font-size: .85rem; font-weight: 600; margin-top: 2px; }
.live-titulo { color: #7f8bab; font-size: .8rem; margin: 6px 0 12px; height: 2.4em; overflow: hidden; }
.live-stats { display: flex; gap: 22px; margin-bottom: 12px; }
.live-stats b { display: block; font-size: 1.2rem; font-weight: 800; color: #fff; }
.live-stats span { color: #7f8bab; font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.live-link { color: #8fa0ff; font-weight: 600; font-size: .82rem; text-decoration: none; }
.live-link:hover { color: #fff; }

/* espaçamentos compatíveis */
.hero .logo { margin-right: 6px; }
.check .chip { margin-right: 12px; }
.live-stats > div { margin-right: 24px; }
.live-stats span { display: block; }
.chip.live::before, .chip.ok::before { margin-right: 6px; }

/* passos */
.passos { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin: 8px 0 14px; }
.passo { background: linear-gradient(180deg, #151b2c, #0f1422); border: 1px solid #232d47; border-radius: 18px; padding: 16px 18px; }
.passo .n { display: inline-flex; width: 28px; height: 28px; align-items: center; justify-content: center; border-radius: 9px;
  background: linear-gradient(135deg, #7c5cff, #19c3fb); font-weight: 800; color: #fff; margin-bottom: 8px; }
.passo b { display: block; color: #fff; margin-bottom: 2px; }
.passo span { color: #94a0be; font-size: .86rem; }
.rodape { text-align: center; color: #56627f; font-size: .78rem; margin: 28px 0 6px; }
</style>
"""


def esc(x):
    return _html.escape(str(x if x is not None else ""))


def aplicar():
    st.markdown(CSS, unsafe_allow_html=True)


def topo(subtitulo="Cortes virais automáticos das lives, da detecção à publicação"):
    st.markdown(f'<div class="hero"><div class="logo">🎬</div><div><h1>Clipador GTA VI</h1>'
                f'<p>{esc(subtitulo)}</p></div></div>', unsafe_allow_html=True)


def chip(texto, tipo="ok"):
    return f'<span class="chip {tipo}">{esc(texto)}</span>'


def checagem(titulo, ok, dica="", opcional=False):
    tipo, rotulo = ("ok", "ok") if ok else (("warn", "opcional") if opcional else ("err", "pendente"))
    detalhe = "" if ok else f'<div class="d">{esc(dica)}</div>'
    st.markdown(f'<div class="check">{chip(rotulo, tipo)}<div class="t">{esc(titulo)}{detalhe}</div></div>',
                unsafe_allow_html=True)


def passos(lista):
    itens = "".join(f'<div class="passo"><div class="n">{i}</div><b>{esc(t)}</b><span>{esc(d)}</span></div>'
                    for i, (t, d) in enumerate(lista, 1))
    st.markdown(f'<div class="passos">{itens}</div>', unsafe_allow_html=True)


def esteira(etapas):
    """etapas: lista de (nome, quantidade)."""
    partes = []
    for i, (nome, n) in enumerate(etapas):
        partes.append(f'<div class="step{" on" if n else ""}"><b>{n}</b><span>{esc(nome)}</span></div>')
        if i < len(etapas) - 1:
            partes.append('<div class="seta">›</div>')
    st.markdown(f'<div class="flow">{"".join(partes)}</div>', unsafe_allow_html=True)


def grade_lives(canais):
    cards = []
    for c in canais:
        cor = PLAT_COR.get(c["plataforma"], "#7c5cff")
        gravando = "Ouvindo" in (c.get("status") or "")
        status = chip("gravando", "ok") if gravando else chip("ao vivo", "live")
        espect = f"{int(c['espectadores']):,}".replace(",", ".")
        chat = f"{c['chat_por_min']:.0f}/min" if c.get("chat_por_min") is not None else "—"
        link = esc(c.get("url") or "#")
        cards.append(
            f'<div class="live-card" style="--cor:{cor}"><div class="live-top">'
            f'<span class="plat" style="background:{cor}22;color:{cor}">{PLAT_NOME.get(c["plataforma"], c["plataforma"])}</span>{status}</div>'
            f'<div class="live-nome">{esc(c["nome"])}</div><div class="live-jogo">{esc(c.get("jogo") or "—")}</div>'
            f'<div class="live-titulo">{esc(c.get("titulo"))}</div>'
            f'<div class="live-stats"><div><b>{espect}</b><span>espectadores</span></div>'
            f'<div><b>{chat}</b><span>chat</span></div></div>'
            f'<a class="live-link" href="{link}" target="_blank">abrir live ↗</a></div>')
    st.markdown(f'<div class="live-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def rodape():
    st.markdown('<div class="rodape">Clipador GTA VI • cortes aprovados por você antes de qualquer publicação</div>',
                unsafe_allow_html=True)
