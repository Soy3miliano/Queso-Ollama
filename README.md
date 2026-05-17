# Queso-Ollama
<p align="center">
  <img src="assets/logo.png" width="200"/>
</p>

<h1 align="center">Nombre del Proyecto</h1>

<p align="center">
  Breve descripción poderosa y profesional del proyecto.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue">
  <img src="https://img.shields.io/badge/Status-Development-green">
  <img src="https://img.shields.io/badge/License-MIT-yellow">
</p>

---

# 📌 Descripción

Tars es un asistente de salud inteligente sieñado para operar de forma totalmente local y privada, garantizando la confidencialidad absoluta del usuario. Su función principal es actuar como un sistema de apoyo en la identificación de s+intomas y la orientación sobre el uso responsable de medicamentos de venta libre(OTC por sus siglas en inglés de Over-the-count).

A diferencia de los modelos de IA comerciales, TARS basa sus respuestas exclusivamente en una base de conocimientos curada: libros de texto de farmacología y medicina de universidades de renombre, eliminando alucinaciones y proporcionando dosis, frecuencias y duraciones de tratamiento fundamentadas en literatura académica.

---

# 🎯 Objetivos

## Objetivo General
Proporcionar una herramienta de consulta médica local y offline que asista a los usuarios en el manejo de síntomas leves mediante el uso correcto de fármacos OTC.

## Objetivos Específicos

- Privacidad Total: Ejecutar modelos de lenguaje de gran tamaño localmente para que los datos de salud nunca salgan del dispositivo.
- Rigor académico: Implementar un sistema RAG (Retrieval.Augmented Generation) para que las dosis y frecuencias se extraigan de PDFs médicos válidos
- Seguridad en Dosificación: Calculas dosis personalizadas basadas en el perfil del usuario (edad, peso) siguiendo estrictamente los protocolos de venta libre.
---

# 🧠 Contexto e Investigación

El proyecto nace de la necesidad de democratizar el acceso a información médica precisa en lugares con conexión a internet limitada o para usuarios que priorizan su privacidad.

Inspircación y Metodología: 
- Ollama: El motor de ejecución local que permite correr modelos como Llama 3 o Minstral sin servidores extrenos.
- Farmacología de Goodman & Gilman / Harrison: Inspirado en las estructuras de datos de estos pilares de la medicina universitaria para la jerarquización de fármacos.

---

# ⚙️ Tecnologías Utilizadas

| Tecnología | Uso |
|------------|-----|
| Python 3.11| Lenguaje núcleo del sistema |
| Ollama | Orquestación de LLm local |

---

# 🏗️ Arquitectura del Sistema

<p align="center">
  <img src="assets/architecture.png" width="800"/>
</p>

1. Ingesta: Los libros de texto en PDF se fragmentan y se convierten en vectores numéricos.
2. Consulta: El usuario ingresa sus síntomas y datos.
3. Recuperación: El sistema busca en la base vectorial la sección exacta del libro que habla del síntoma o medicamento.
Generación: El LLM (vía Ollama) redacta una respuesta coherente usando solo la información recuperada.

---

# 🔄 Funcionamiento

## Paso 1
Captura de datos.

## Paso 2
Procesamiento de señales.

## Paso 3
Clasificación mediante IA.

## Paso 4
Respuesta del sistema.

---

# 🔒 Seguridad

Ejecución Local: No hay APIs externas. La información sobre enfermedades o síntomas permanece en la memoria RAM del equipo local.

Filtro OTC: El sistema está programado para detectar si el usuario solicita medicamentos controlados (receta obligatoria) y declinar la respuesta, sugiriendo siempre la visita a un profesional.
Advertencias Automáticas: Cada respuesta de TARS incluye un disclaimer sobre el riesgo de reacciones alérgicas y la importancia de no automedicarse.

---

# 📚 Referencias

- Amoxilina
- Evidencia 2. Modelado de concentración de amoxicilina en plasma sanguíneo.
- Modern Control Enginnering (5th Edition)
- Mathematical models for drug diffusion through the compartments of blood and tissue medium.
- Pharmacokinetic and Pharmacodynamic Data Analysis: Concepts and Applications, Third Edition.
- Clinical Pharmacokinetics and Pharmacodynamics (5th edition).
- Circuits Signals and Systems for Bioengineers A MATLAB-Based Introduction (3th edition).
- Signals and Systems Analysis In Biomedical Enginnering.

---

# 📂 Estructura del Proyecto

```bash
src/
assets/
docs/
tests/
```

---

# 🛠️ Futuras Mejoras

- Análisis de Interacciones: Capacidad para advertir si un medicamento OTC choca con otro que el usuario ya esté tomando.
- Interfaz de Voz: Integración con Whisper para permitir consultas por voz (estilo Interstellar).
- OCR de Etiquetas: Poder tomar una foto a la caja del medicamento y que TARS explique la dosis basada en el libro de texto.

---

# 👥 Autores

- Emiliano Montalvo, Andrés Guzmán, Algo Galván, Diego Huitron
- Queso-Ollama
- ITESM

---

# 📜 Licencia

MIT License