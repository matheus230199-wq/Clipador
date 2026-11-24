"""Banco de dados (SQLite) compartilhado entre a Torre, o modo ao vivo e o painel."""
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).parent / "torre.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS estado (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS canais_estado (
    plataforma TEXT, canal TEXT, nome TEXT, ao_vivo INTEGER, espectadores INTEGER,
    jogo TEXT, titulo TEXT, url TEXT, iniciada_em TEXT, status TEXT,
    chat_por_min REAL, atualizado REAL, PRIMARY KEY (plataforma, canal));
CREATE TABLE IF NOT EXISTS amostras (
    ts REAL, plataforma TEXT, canal TEXT, ao_vivo INTEGER, espectadores INTEGER, chat_por_min REAL);
CREATE TABLE IF NOT EXISTS chat_minuto (
    ts REAL, plataforma TEXT, canal TEXT, mensagens INTEGER);
CREATE INDEX IF NOT EXISTS idx_chat_minuto ON chat_minuto (plataforma, canal, ts);
CREATE TABLE IF NOT EXISTS momentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, plataforma TEXT, canal TEXT,
    origem TEXT, nota REAL, pasta TEXT, status TEXT);
"""


def conectar():
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(ESQUEMA)
    return con


def _exec(sql, params=()):
    con = conectar()
    try:
        cur = con.execute(sql, params)
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def set_estado(chave, valor):
    _exec("INSERT OR REPLACE INTO estado VALUES (?, ?)", (chave, str(valor)))


def get_estado(chave, padrao=None):
    con = conectar()
    try:
        r = con.execute("SELECT valor FROM estado WHERE chave=?", (chave,)).fetchone()
        return r["valor"] if r else padrao
    finally:
        con.close()


def set_canal(plataforma, canal, nome, info, status, chat_por_min=None):
    _exec("""INSERT OR REPLACE INTO canais_estado
             (plataforma, canal, nome, ao_vivo, espectadores, jogo, titulo, url, iniciada_em, status, chat_por_min, atualizado)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
          (plataforma, canal, nome, int(bool(info.get("ao_vivo"))), int(info.get("espectadores") or 0),
           info.get("jogo", ""), info.get("titulo", ""), info.get("url", ""), info.get("iniciada_em", ""),
           status, chat_por_min, time.time()))


def add_amostra(plataforma, canal, info, chat_por_min=None):
    _exec("INSERT INTO amostras VALUES (?,?,?,?,?,?)",
          (time.time(), plataforma, canal, int(bool(info.get("ao_vivo"))), int(info.get("espectadores") or 0), chat_por_min))


def add_momento(plataforma, canal, origem, nota, pasta=None, status="sinal"):
    return _exec("INSERT INTO momentos (ts, plataforma, canal, origem, nota, pasta, status) VALUES (?,?,?,?,?,?,?)",
                 (time.time(), plataforma, canal, origem, float(nota), pasta, status))


def set_status_momento(pasta, status):
    _exec("UPDATE momentos SET status=? WHERE pasta=?", (status, pasta))


def consultar(sql, params=()):
    con = conectar()
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def add_chat_minuto(plataforma, canal, ts, mensagens):
    """Total de mensagens do chat em 1 minuto (base para usar o chat na nota dos cortes)."""
    _exec("INSERT INTO chat_minuto VALUES (?,?,?,?)", (ts, plataforma, canal, int(mensagens)))


def limpar(dias=30):
    """Apaga amostras e chat com mais de N dias, para o banco não crescer sem parar."""
    limite = time.time() - dias * 86400
    con = conectar()
    try:
        for tabela in ("amostras", "chat_minuto"):
            con.execute(f"DELETE FROM {tabela} WHERE ts < ?", (limite,))
        con.commit()
    finally:
        con.close()


def sincronizar_canais(chaves):
    """Remove do painel os canais que não estão mais na lista (chaves = [(plataforma, canal), ...])."""
    manter = {(p, c.lower()) for p, c in chaves}
    con = conectar()
    try:
        for r in con.execute("SELECT plataforma, canal FROM canais_estado").fetchall():
            if (r["plataforma"], r["canal"].lower()) not in manter:
                con.execute("DELETE FROM canais_estado WHERE plataforma=? AND canal=?", (r["plataforma"], r["canal"]))
        con.commit()
    finally:
        con.close()


def set_pasta_momento(id_momento, pasta, status="renderizando"):
    """Liga um sinal (ex.: explosão do chat) ao corte que foi gerado a partir dele."""
    _exec("UPDATE momentos SET pasta=?, status=? WHERE id=?", (pasta, status, id_momento))
