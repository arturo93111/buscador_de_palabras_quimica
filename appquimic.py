import streamlit as st
import sqlalchemy
from sqlalchemy import text
import pandas as pd
import os

st.set_page_config(page_title="Química — Base de datos de palabras clave")

st.title("🔬 Química — Base de datos de palabras clave")

# ==========================
# CONEXIÓN A POSTGRES
# ==========================
st.sidebar.header("Conexión PostgreSQL")

# Render ya coloca DATABASE_URL automáticamente
DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    st.sidebar.success("Render detectado: usando DATABASE_URL automáticamente.")
else:
    st.sidebar.error("DATABASE_URL no detectada.")
    st.stop()

# Crear engine SQLAlchemy
engine = sqlalchemy.create_engine(DATABASE_URL)

# ==========================
# CONSULTA SQL
# ==========================

QUERY = text("""
    SELECT
        id,
        lower(palabra) AS palabra_norm,
        lower(sinonimos) AS sinonimo_norm,
        porcentaje_identidad
    FROM quimica.palabras_quimica
    ORDER BY palabra;
""")

try:
    df = pd.read_sql(QUERY, engine)
    st.info("Conexión establecida con la base de datos.")
except Exception as e:
    st.error("❌ No se pudo conectar a la base de datos.")
    st.exception(e)
    st.stop()

# ==========================
# PROCESAR TEXTO
# ==========================

st.subheader("Verificador de palabras")

texto_usuario = st.text_area("Pega tu texto para analizar:", height=200)

umbral = st.sidebar.slider("Umbral para decir: 'ES de Química' (%)", 1, 100, 20)

if st.button("Analizar texto"):
    if not texto_usuario.strip():
        st.warning("Debes pegar un texto.")
        st.stop()

    # Normalizar texto del usuario
    palabras_usuario = texto_usuario.lower().split()

    coincidencias = []

    for _, fila in df.iterrows():
        palabra = fila["palabra_norm"]
        sinonimo = fila["sinonimo_norm"]

        if palabra in palabras_usuario or sinonimo in palabras_usuario:
            coincidencias.append((palabra, sinonimo, fila["porcentaje_identidad"]))

    if coincidencias:
        total = len(df)
        porcentaje = (len(coincidencias) / total) * 100

        st.write(f"### Resultado: {porcentaje:.2f}% de coincidencia")

        st.table(
            pd.DataFrame(coincidencias, columns=["Palabra", "Sinónimo", "Identidad %"])
        )

        if porcentaje >= umbral:
            st.success("El texto **SÍ ES** de Química.")
        else:
            st.warning("El texto **NO parece** ser de Química.")

    else:
        st.error("No se encontraron coincidencias en el texto.")
