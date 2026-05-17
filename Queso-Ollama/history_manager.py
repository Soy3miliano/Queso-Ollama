"""
history_manager.py
Gestor de historial de conversación persistente usando SQLite.
Compatible con app.py (TARS — Asistente Médico Local).

Funciones exportadas:
    new_session()            → crea sesión nueva, retorna session_id
    get_or_create_session()  → valida o crea sesión
    save_message()           → persiste un turno en la BD
    get_context()            → lista [{role, content}] para pasar a Ollama
    get_context_string()     → texto plano "Usuario: ...\nTARS: ..." para el prompt RAG
    get_session_history()    → historial completo de una sesión
    list_sessions()          → sesiones recientes con conteo de mensajes
    delete_session()         → elimina sesión y sus mensajes
    export_session()         → exporta sesión a JSON o texto plano
    search_history()         → búsqueda por palabra clave en todos los mensajes
    delete_all_history()     → limpia toda la base de datos
"""

from __future__ import annotations

import sqlite3
import uuid
import json
import logging
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

logger = logging.getLogger("TARS.History")

# Configuración
DB_PATH        = Path("./tars_history.db")
MAX_CONTEXT    = 10      # turnos máximos para el contexto del LLM
MAX_CHARS_CTX  = 3_000   # límite de caracteres del contexto (evita desbordamiento)

# Esquema
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    summary     TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(session_id),
    timestamp    TEXT NOT NULL,
    role         TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content      TEXT NOT NULL,
    drug_context TEXT DEFAULT NULL,
    msg_type     TEXT DEFAULT 'rag'
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_ts      ON messages(timestamp);
"""

# Conexión
@contextmanager
def _get_conn():
    """Abre y cierra la conexión SQLite de forma segura."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_schema() -> None:
    with _get_conn() as conn:
        conn.executescript(_SCHEMA)


# Crear tablas al importar el módulo
_ensure_schema()

# Helpers internos
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# Gestión de sesiones
def new_session(summary: str = "") -> str:
    """
    Crea una sesión nueva con UUID único.
    Retorna el session_id generado.
    """
    sid = str(uuid.uuid4())
    now = _now()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, created_at, updated_at, summary) "
            "VALUES (?, ?, ?, ?)",
            (sid, now, now, summary),
        )
    logger.info("Nueva sesión: %s", sid)
    return sid


def get_or_create_session(session_id: Optional[str]) -> str:
    """
    Si session_id existe en la BD lo retorna.
    Si no existe o es None, crea una sesión nueva.
    """
    if session_id:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row:
            return session_id
    return new_session()


def list_sessions(limit: int = 20) -> list[dict]:
    """
    Retorna las sesiones más recientes con número de mensajes.
    Útil para el sidebar de Streamlit.
    """
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.session_id,
                   s.created_at,
                   s.updated_at,
                   s.summary,
                   COUNT(m.id) AS n_messages
            FROM sessions s
            LEFT JOIN messages m ON m.session_id = s.session_id
            GROUP BY s.session_id
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_session(session_id: str) -> None:
    """Elimina una sesión y todos sus mensajes."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    logger.info("Sesión eliminada: %s", session_id)


def delete_all_history() -> None:
    """Borra toda la base de datos de historial."""
    with _get_conn() as conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM sessions")
    logger.warning("Historial completo eliminado.")


# Escritura de mensajes
def save_message(
    session_id: str,
    role: str,
    content: str,
    drug_context: Optional[dict] = None,
    msg_type: str = "rag",
) -> int:
    """
    Guarda un mensaje en la base de datos.

    Args:
        session_id   : ID de la sesión activa
        role         : 'user' | 'assistant' | 'system'
        content      : texto del mensaje
        drug_context : dict opcional con info del fármaco detectado
        msg_type     : 'rag' | 'pk_analysis'

    Returns:
        ID del mensaje insertado
    """
    now       = _now()
    drug_json = json.dumps(drug_context, ensure_ascii=False) if drug_context else None

    with _get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO messages
                (session_id, timestamp, role, content, drug_context, msg_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, now, role, content, drug_json, msg_type),
        )
        msg_id = cur.lastrowid
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
            (now, session_id),
        )
    return msg_id

# Recuperación de contexto para el LLM
def get_context(
    session_id: str,
    max_turns: int = MAX_CONTEXT,
    max_chars: int = MAX_CHARS_CTX,
) -> list[dict]:
    """
    Retorna los últimos N turnos como lista de dicts {role, content}.
    Formato compatible con ollama.chat(messages=[...]).

    El contexto se trunca por caracteres para no desbordar la ventana del LLM.
    Se conserva siempre lo más reciente.

    Returns:
        [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
    """
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, max_turns * 2),
        ).fetchall()

    # Revertir al orden cronológico
    messages = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    # Truncar desde el inicio (conservar los más recientes)
    total   = 0
    trimmed = []
    for msg in reversed(messages):
        total += len(msg["content"])
        if total > max_chars:
            break
        trimmed.insert(0, msg)

    return trimmed


def get_context_string(
    session_id: str,
    max_turns: int = MAX_CONTEXT,
) -> str:
    """
    Retorna el historial como texto plano para inyectar en el prompt RAG.

    Formato:
        Usuario: <pregunta>
        TARS: <respuesta>
        Usuario: <siguiente pregunta>
        ...

    Retorna cadena vacía si no hay historial.
    """
    msgs = get_context(session_id, max_turns)
    if not msgs:
        return ""

    lines = []
    for m in msgs:
        prefix = "Usuario" if m["role"] == "user" else "TARS"
        lines.append(f"{prefix}: {m['content']}")

    return "\n".join(lines)


# Historial completo de sesión
def get_session_history(session_id: str) -> list[dict]:
    """
    Retorna todos los mensajes de una sesión en orden cronológico.
    Usado en la pestaña "Mi Historial" de Streamlit.
    """
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, timestamp, role, content, drug_context, msg_type
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        if d["drug_context"]:
            try:
                d["drug_context"] = json.loads(d["drug_context"])
            except json.JSONDecodeError:
                pass
        result.append(d)

    return result

# Búsqueda
def search_history(keyword: str, limit: int = 20) -> list[dict]:
    """
    Busca mensajes que contengan `keyword` (sin distinción de mayúsculas).
    Retorna lista con metadatos de sesión, ordenada por fecha descendente.
    """
    pattern = f"%{keyword}%"
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.session_id, m.timestamp, m.role, m.content
            FROM messages m
            WHERE m.content LIKE ? COLLATE NOCASE
            ORDER BY m.timestamp DESC
            LIMIT ?
            """,
            (pattern, limit),
        ).fetchall()
    return [dict(r) for r in rows]


# Exportación
def export_session(session_id: str, fmt: str = "json") -> str:
    """
    Exporta el historial completo de una sesión.

    Args:
        session_id : ID de la sesión
        fmt        : 'json' → JSON indentado | 'text' → texto legible

    Returns:
        String con el contenido exportado listo para descargar.
    """
    history = get_session_history(session_id)

    if fmt == "json":
        return json.dumps(
            {"session_id": session_id, "messages": history},
            indent=2,
            ensure_ascii=False,
        )

    # Formato texto legible
    lines = [f"=== Sesión TARS — {session_id} ===\n"]
    for m in history:
        prefix = "Usuario" if m["role"] == "user" else "TARS"
        ts     = m["timestamp"][:16].replace("T", " ")
        lines.append(f"[{ts}] {prefix}: {m['content']}\n")

    return "\n".join(lines)