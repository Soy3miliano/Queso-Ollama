import streamlit as st
import os
import json
import re
import logging
from datetime import datetime, time
from typing import Optional

import ollama
from langchain_community.document_loaders import PyPDFDire  ctoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from drug_database import get_drug, get_all_modelable, DRUG_DB
from pharma_model import simulate_single_dose, find_optimal_interval, half_life
from notifier import schedule_reminders, cancel_all, list_active

# Configuración general
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("TARS")
 
MODEL_NAME = "llama3"
CANDIDATE_INTERVALS = [2, 4, 6, 8, 12, 24]
DEFAULT_TREATMENT_HOURS = {
    "amoxicilina": 168, "paracetamol": 72, "ibuprofeno": 72,
    "naproxeno": 72, "aspirina": 24, "loratadina": 336,
    "cetirizina": 336, "omeprazol": 336, "loperamida": 48,
    "dextrometorfano": 48, "guaifenesina": 48,
    "subsalicilato_bismuto": 48, "oximetazolina": 72,
}
_DOSE_DEFAULTS = {k: v.typical_dose_mg for k, v in DRUG_DB.items()}
_DURATION_KEYWORDS = [
    (["infección", "antibiótico", "amoxicilina"],        168.0),
    (["alergia", "rinitis", "loratadina", "cetirizina"], 168.0),
    (["omeprazol", "reflujo", "gastritis", "úlcera"],    336.0),
    (["gripe", "resfriado", "covid", "tos", "fiebre"],    72.0),
    (["diarrea", "loperamida", "bismuto"],                 48.0),
    (["dolor", "paracetamol", "ibuprofeno", "aspirina"],   24.0),
    (["naproxeno"],                                         72.0),
]

# --- CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Asistente Médico Offline", page_icon="⚕️")
st.title("⚕️ Asistente Médico Local - GuadalaHacks")
st.caption("Consultas basadas estrictamente en la bibliografía local (100% Offline)")

# --- MOTOR DE PROCESAMIENTO RAG ---
@st.cache_resource
def inicializar_rag():
    directorio_db = "./chroma_db_medico"
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
 
    qa_chain = None

    vectorstore = None
 
    if os.path.exists(directorio_db):
        try:
            vectorstore = Chroma(persist_directory=directorio_db, embedding_function=embeddings)
            st.info("📚 Cargando base de datos existente...")
        except:
            st.warning("⚠️ Base de datos corrupta, reindexando...")
            vectorstore = None
 
    if vectorstore is None:
        st.info("📚 Indexando libros médicos...")
 
        if not os.path.exists("./documentos_medicos"):
            os.makedirs("./documentos_medicos")
            st.warning("⚠️ Creé la carpeta 'documentos_medicos'. Por favor, añade PDFs allí y recarga.")
            st.stop()
 
        loader = PyPDFDirectoryLoader("./documentos_medicos")
        documentos = loader.load()
 
        if not documentos:
            st.warning("⚠️ No hay PDFs en la carpeta 'documentos_medicos'. Añade al menos uno y recarga.")
            st.stop()
 
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=0)
        textos = text_splitter.split_documents(documentos)
 
        st.info(f"📄 Procesando {len(textos)} fragmentos de {len(documentos)} documento(s)...")
 
        vectorstore = Chroma.from_documents(
            documents=textos,
            embedding=embeddings,
            persist_directory=directorio_db
        )
        vectorstore.persist()
        st.success(f"✅ ¡{len(documentos)} libro(s) indexado(s) correctamente!")
 
    llm = ChatOllama(
        model="llama3",
        temperature=0.0,
        stop=["<|eot_id|>", "<|start_header_id|>", "Pregunta:", "\nPregunta"]
    )
 
    prompt_template = """You are a highly precise medical data extractor. Your ONLY job is to find the answer in the provided Spanish text and extract it.
 
CRITICAL RULES:
1. Read the following Context (which is in Spanish).
2. Answer the Question in Spanish using ONLY the words from the text.
3. DO NOT invent medical terms. DO NOT translate. 
4. If the exact answer is not in the Context, you MUST output exactly: "No tengo información en la bibliografía proporcionada."
 
Context:
{context}
 
Question: {question}
Answer in Spanish:"""
 
    PROMPT = PromptTemplate(template=prompt_template, input_variables=["context", "question"])
 
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)
 
    retriever = vectorstore.as_retriever(
        search_type="mmr",
        search_kwargs={"k": 5, "fetch_k": 20}
    )
 
    qa_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | PROMPT
        | llm
        | StrOutputParser()
    )
 
    return qa_chain

# MOTOR FARMACOCINÉTICO Y NOTIFICACIONES
_EXTRACTION_PROMPT = """You are a clinical assistant. Your only task is to read
the user message and extract TWO numeric values.
 
RESPOND ONLY with a JSON object, no additional text, no explanations:
{"dose_mg": NUMBER_OR_NULL, "hours": NUMBER_OR_NULL}
 
Rules:
- "dose_mg" : the dose in mg that the user mentions explicitly. If NOT mentioned, put null.
- "hours"   : duration of the treatment in hours. Convert days ("3 days" → 72, "a week" → 168).
  If NOT mentioned, put null.
- Respond ONLY the JSON.
 
User message to be analyzed:
"""
 
def _extract_dose_and_duration(mensaje: str, drug_key: str) -> tuple[float, float]:
    """Pipeline de 3 capas: LLM extractor → regex → defaults de BD."""
    dose_llm = hours_llm = None
 
    # Capa 1 — LLM extractor
    try:
        resp = ollama.chat(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": _EXTRACTION_PROMPT + mensaje}],
        )
        raw = resp["message"]["content"].strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        raw = re.sub(r",\s*}", "}", raw)
        raw = raw.replace("'", '"')
        extracted = json.loads(raw)
        dose_llm  = extracted.get("dose_mg")
        hours_llm = extracted.get("hours")
    except Exception:
        pass
 
    # Capa 2 — Regex
    if dose_llm is None:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*mg", mensaje, re.IGNORECASE)
        if m:
            dose_llm = float(m.group(1).replace(",", "."))
 
    if hours_llm is None:
        for pattern, multiplier in [
            (r"(\d+)\s*d[íi]as?", 24),
            (r"(\d+)\s*semanas?", 168),
            (r"(\d+)\s*horas?", 1),
        ]:
            m = re.search(pattern, mensaje, re.IGNORECASE)
            if m:
                hours_llm = float(m.group(1)) * multiplier
                break
        if hours_llm is None:
            msg_low = mensaje.lower()
            for keywords, default_h in _DURATION_KEYWORDS:
                if any(kw in msg_low for kw in keywords):
                    hours_llm = default_h
                    break
 
    # Capa 3 — Defaults
    final_dose  = float(dose_llm)  if dose_llm  is not None else _DOSE_DEFAULTS.get(drug_key, 500.0)
    final_hours = float(hours_llm) if hours_llm is not None else DEFAULT_TREATMENT_HOURS.get(drug_key, 48.0)
    return final_dose, final_hours
 
 
def _run_pk_analysis(drug_key: str, dose_mg: float, total_hours: float) -> dict:
    """Ejecuta simulación PK y devuelve resultados listos para mostrar en Streamlit."""
    drug = get_drug(drug_key)
    if drug is None:
        return {"error": f"Fármaco '{drug_key}' no encontrado."}
    if drug.local_action:
        return {"local_action": True, "name": drug.name, "notes": drug.notes}
 
    single = simulate_single_dose(
        k=drug.ke, V_mL=drug.V_mL, A0_mg=dose_mg, CMB=drug.CMB,
        drug_name=drug.name, gamma=drug.gamma, t_end=min(total_hours, 48.0),
    )
    opt = find_optimal_interval(
        k=drug.ke, V_mL=drug.V_mL, A0_mg=dose_mg, CMB=drug.CMB,
        drug_name=drug.name, candidates=CANDIDATE_INTERVALS,
        gamma=drug.gamma, t_final=min(total_hours, 72.0),
    )
    return {
        "drug": drug.name,
        "dose_mg": dose_mg,
        "ke": drug.ke,
        "half_life_h": round(half_life(drug.ke), 2),
        "V_mL": drug.V_mL,
        "CMB": drug.CMB,
        "C_max": round(single.C_max, 4),
        "t_max": round(single.t_max, 2),
        "t_below_cmb": round(single.t_below_cmb, 2) if single.t_below_cmb else None,
        "optimal_interval_h": opt["optimal_interval_h"],
        "summary": opt["summary"],
        "is_valid": opt["is_valid"],
        "notes": drug.notes,
    }
 
 
def _mostrar_reporte_pk(r: dict) -> None:
    """Renderiza el reporte PK dentro de Streamlit."""
    if "error" in r:
        st.error(r["error"])
        return
    if r.get("local_action"):
        st.info(f"ℹ️ **{r['name']}** actúa localmente en el tracto GI y no requiere modelado sistémico.\n\n{r['notes']}")
        return
 
    st.success(f"✅ Intervalo óptimo recomendado: **cada {r['optimal_interval_h']} horas**")
 
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Cmax", f"{r['C_max']:.3f} µg/mL")
    col2.metric("Tiempo al pico", f"{r['t_max']:.2f} h")
    col3.metric("Vida media (t½)", f"{r['half_life_h']} h")
    col4.metric("CMB efectiva", f"{r['CMB']} µg/mL")
 
    if r["t_below_cmb"]:
        st.warning(f"⚠️ Con dosis única, la concentración cae bajo el umbral efectivo a las **{r['t_below_cmb']} h**. No usar dosis única aislada.")
 
    st.subheader("Evaluación de regímenes (72 h de simulación)")
    for s in r["summary"]:
        valido = s["trough_ss"] >= r["CMB"]
        emoji  = "✅" if valido else "❌"
        st.markdown(f"{emoji} Cada **{s['interval_h']}h** — valle: `{s['trough_ss']:.4f}` µg/mL · pico SS: `{s['peak_ss']:.4f}` µg/mL")
 
    with st.expander("📝 Notas clínicas"):
        st.write(r["notes"])
        st.caption(f"ke = {r['ke']} h⁻¹ · V = {r['V_mL']:,} mL")

# --- INTERFAZ DE CHAT ---
with st.sidebar:
    st.header("⚙️ Configuración")
    st.info("💡 **Para añadir nuevos PDFs:** Coloca los archivos en `documentos_medicos` y presiona F5.")
    st.divider()
    st.subheader("📚 Documentos cargados:")
    if os.path.exists("./documentos_medicos"):
        pdfs = [f for f in os.listdir("./documentos_medicos") if f.endswith(".pdf")]
        if pdfs:
            st.success(f"✅ {len(pdfs)} PDF(s) encontrado(s):")
            for i, pdf in enumerate(pdfs, 1):
                st.write(f"{i}. {pdf}")
        else:
            st.warning("⚠️ No hay PDFs en `documentos_medicos`")
    else:
        st.error("❌ Carpeta `documentos_medicos` no existe")
 
    st.divider()
    st.subheader("💊 Recordatorios activos:")
    activos = list_active()
    if activos:
        for a in activos:
            next_at = a.get('next_dose_at') or 'sin próximo'
            remaining = a.get('remaining_doses', 0)
            st.write(
                f"• {a['drug']} — {a['dose_mg']} mg c/{a['interval_h']} h · "
                f"próxima: {next_at} · restantes: {remaining}"
            )
        if st.button("🛑 Cancelar todos"):
            cancel_all()
            st.rerun()
    else:
        st.caption("Ninguno activo")

# Inicializar RAG (fallback a modelo local si falla)
try:
    qa_chain = inicializar_rag()
except Exception as e:
    qa_chain = None
    st.warning("⚠️ No se pudo inicializar el indexado RAG. El chat usará el modelo local si está disponible.")

if "mensajes" not in st.session_state:
    st.session_state.mensajes = []

for mensaje in st.session_state.mensajes:
    with st.chat_message(mensaje["role"]):
        st.markdown(mensaje["content"])

tab_rag, tab_pk = st.tabs(["📖 Consulta Bibliográfica", "💊 Dosificación Óptima"])

with tab_rag:
    st.subheader("Chat bibliográfico")
    st.caption("Pregunta usando la bibliografía local o consulta al modelo local si no hay indexado.")

    prompt = st.chat_input("Consulta un síntoma, protocolo o historial...")

    if prompt:
        st.session_state.mensajes.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            if qa_chain is not None:
                with st.spinner("Buscando en la bibliografía médica..."):
                    try:
                        texto_final = qa_chain.invoke(prompt)
                        st.markdown(texto_final)
                        st.session_state.mensajes.append({"role": "assistant", "content": texto_final})
                    except Exception as e:
                        st.error(f"❌ Error de procesamiento: {e}")
            else:
                with st.spinner("Consultando modelo local..."):
                    try:
                        from ia_local import consultar_modelo

                        texto_final = consultar_modelo(prompt)
                        st.markdown(texto_final)
                        st.session_state.mensajes.append({"role": "assistant", "content": texto_final})
                    except Exception as e:
                        st.error(f"❌ Error consultando modelo local: {e}")

# DOSIFICACION FARMACOCINETICA
with tab_pk:
    st.subheader("Calculadora de Intervalo de Dosificación")
    st.caption("Modelo LTI monocompartimental")
 
    modelables = get_all_modelable()
    opciones   = {v.name: k for k, v in modelables.items()}
    nombre_sel = st.selectbox("Selecciona el medicamento", list(opciones.keys()))
    drug_key   = opciones[nombre_sel]
    drug       = get_drug(drug_key)
 
    col_a, col_b = st.columns(2)
    with col_a:
        dose_input = st.number_input(
            "Dosis por toma (mg)",
            min_value=1.0,
            max_value=float(drug.max_dose_per_day_mg),
            value=float(drug.typical_dose_mg),
            step=50.0,
        )
    with col_b:
        dias_input = st.number_input(
            "Duración del tratamiento (días)",
            min_value=1,
            max_value=30,
            value=int(DEFAULT_TREATMENT_HOURS.get(drug_key, 48) // 24),
        )

    use_last_taken = st.checkbox("Ya tomé una dosis antes y quiero ajustar el horario")
    first_dose_time = None
    if use_last_taken:
        last_taken_time = st.time_input(
            "Hora de la última toma",
            value=datetime.now().time(),
        )
        first_dose_time = datetime.combine(datetime.now().date(), last_taken_time)
        st.caption("El recordatorio se ajustará en base a la última toma registrada.")

    remind_check = st.checkbox("Programar recordatorios en este equipo")
 
    texto_libre = st.text_input(
        "O describe tu situación (opcional — extrae dosis y duración automáticamente)",
        placeholder="Ej: necesito amoxicilina 875mg por 7 días para una infección",
    )
 
    if st.button("▶ Calcular intervalo óptimo", type="primary"):
        if texto_libre.strip():
            with st.spinner("Extrayendo dosis y duración del texto..."):
                dose_final, hours_final = _extract_dose_and_duration(texto_libre, drug_key)
            st.info(f"Extraído del texto → **{dose_final:.0f} mg** durante **{hours_final:.0f} h**")
        else:
            dose_final  = float(dose_input)
            hours_final = float(dias_input * 24)
 
        with st.spinner("Simulando modelo farmacocinético..."):
            resultado = _run_pk_analysis(drug_key, dose_final, hours_final)
 
        _mostrar_reporte_pk(resultado)
 
        if remind_check and resultado.get("optimal_interval_h"):
            schedule_reminders(
                drug_name=resultado["drug"],
                dose_mg=dose_final,
                interval_h=resultado["optimal_interval_h"],
                total_hours=hours_final,
                first_dose_time=first_dose_time,
            )
            st.success(f"🔔 Recordatorios programados cada {resultado['optimal_interval_h']} h")
            if first_dose_time is not None:
                st.info(f"Horario base tomado: {first_dose_time.strftime('%H:%M')}")
            st.rerun()