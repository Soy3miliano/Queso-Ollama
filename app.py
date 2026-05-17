import streamlit as st
import os
from langchain_community.document_loaders import PyPDFDirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Asistente Médico Offline", page_icon="⚕️")
st.title("⚕️ Asistente Médico Local - GuadalaHacks")
st.caption("Consultas basadas estrictamente en la bibliografía local (100% Offline)")

# --- 2. MOTOR DE PROCESAMIENTO RAG ---
@st.cache_resource
def inicializar_rag():
    directorio_db = "./chroma_db_medico"
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    
    # Siempre reprocessa para detectar nuevos PDFs
    vectorstore = None
    
    # Intenta cargar si existe
    if os.path.exists(directorio_db):
        try:
            vectorstore = Chroma(persist_directory=directorio_db, embedding_function=embeddings)
            st.info("📚 Cargando base de datos existente...")
        except:
            st.warning("⚠️ Base de datos corrupta, reindexando...")
            vectorstore = None
    
    # Si no existe o está corrupta, procesa los PDFs
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
        
        # Pica los libros en párrafos de 1000 letras
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        textos = text_splitter.split_documents(documentos)
        
        st.info(f"📄 Procesando {len(textos)} fragmentos de {len(documentos)} documento(s)...")
        
        # Crea la base de datos local
        vectorstore = Chroma.from_documents(
            documents=textos, 
            embedding=embeddings, 
            persist_directory=directorio_db
        )
        vectorstore.persist()
        st.success(f"✅ ¡{len(documentos)} libro(s) indexado(s) correctamente!")

    # Configuramos el modelo Phi-3
    llm = ChatOllama(model="phi3", temperature=0.0, stop=["Pregunta:", "\nPregunta", "Question:"])
    
 # Prompt Híbrido: Reglas en inglés, ejecución en español
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

    # Función para formatear documentos
    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    # Recuperador
    retriever = vectorstore.as_retriever(
        search_type="mmr", 
        search_kwargs={"k": 5, "fetch_k": 20}
    )

    # Cadena RAG moderna (LCEL)
    qa_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | PROMPT
        | llm
        | StrOutputParser()
    )
    
    return qa_chain

# --- 3. INTERFAZ DE CHAT ---
with st.sidebar:
    st.header("⚙️ Configuración")
    st.info("💡 **Para añadir nuevos PDFs:** Coloca los archivos en la carpeta `documentos_medicos` y presiona F5 para recargar.")
    
    st.divider()
    
    # Mostrar PDFs disponibles
    st.subheader("📚 Documentos cargados:")
    if os.path.exists("./documentos_medicos"):
        pdfs = [f for f in os.listdir("./documentos_medicos") if f.endswith(".pdf")]
        if pdfs:
            st.success(f"✅ {len(pdfs)} PDF(s) encontrado(s):")
            for i, pdf in enumerate(pdfs, 1):
                st.write(f"{i}. {pdf}")
        else:
            st.warning("⚠️ No hay PDFs en la carpeta `documentos_medicos`")
    else:
        st.error("❌ Carpeta `documentos_medicos` no existe")

try:
    qa_chain = inicializar_rag()
except Exception as e:
    st.error(f"❌ Error: {e}")
    st.info("💡 Asegúrate de que:\n1. Ollama está corriendo\n2. Tienes los modelos 'nomic-embed-text' y 'phi3' instalados\n3. Hay al menos un PDF en 'documentos_medicos'")
    st.stop()

if "mensajes" not in st.session_state:
    st.session_state.mensajes = []

for mensaje in st.session_state.mensajes:
    with st.chat_message(mensaje["role"]):
        st.markdown(mensaje["content"])

prompt = st.chat_input("Consulta un síntoma, protocolo o historial...")

if prompt:
    # Mostramos mensaje del usuario
    st.session_state.mensajes.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Procesamos con el RAG
    with st.chat_message("assistant"):
        with st.spinner("Buscando en la bibliografía médica..."):
            try:
                # Enviamos la pregunta a nuestra cadena RAG
                texto_final = qa_chain.invoke(prompt)
                
                st.markdown(texto_final)
                st.session_state.mensajes.append({"role": "assistant", "content": texto_final})
            except Exception as e:
                st.error(f"❌ Error de procesamiento: {e}")