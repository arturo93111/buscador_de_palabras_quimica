import os
import re
import unicodedata
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Química — Verificador de tema", page_icon="🧪", layout="wide")

# ------------------- utilidades -------------------
def strip_accents(s: str) -> str:
    """Elimina acentos y diacríticos de una cadena."""
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def tokenize(text: str):
    """Convierte texto en tokens alfanuméricos sin acentos."""
    clean = strip_accents(text.lower())
    return re.findall(r"[a-z0-9]+", clean)

@st.cache_data(show_spinner=False)
def load_from_pg(host, db, user, pwd):
    """Carga las palabras y sinónimos desde PostgreSQL."""
    import sqlalchemy as sa
    url = sa.engine.URL.create(
        drivername="postgresql+psycopg2",
        username=user, password=pwd, host=host, port=5432, database=db
    )
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        # Carga sin usar unaccent(), se normaliza en Python
        df = pd.read_sql("""
            SELECT
              id,
              palabra::text AS palabra_raw,
              CASE
                WHEN pg_typeof(sinonimos)::text LIKE 'text[]'
                  THEN array_to_string(sinonimos, ',')
                ELSE COALESCE(sinonimos::text, '')
              END AS sinonimos_raw,
              porcentaje_identidad
            FROM quimica.palabras_quimica
            ORDER BY palabra;
        """, conn)

    # Normalización en Python
    def norm_one(s: str) -> str:
        s = '' if s is None else s
        s = s.strip().lower()
        s = strip_accents(s)
        s = re.sub(r"\s+", "_", s)
        return s

    df["palabra_norm"] = df["palabra_raw"].fillna("").apply(lambda x: norm_one(str(x)))
    df["sinonimo_norm"] = (
        df["sinonimos_raw"].fillna("")
        .apply(lambda s: s.split(",")[0])
        .apply(norm_one)
    )
    return df

@st.cache_data(show_spinner=False)
def build_keyword_set(df: pd.DataFrame) -> set:
    """Construye el conjunto de palabras clave normalizadas."""
    kws = set()
    for _, r in df.iterrows():
        if r["palabra_norm"]:
            kws.add(r["palabra_norm"])
        if r["sinonimo_norm"]:
            kws.add(r["sinonimo_norm"])
    # añade variantes simples (singular/plural)
    kws |= {k.rstrip("s") for k in list(kws) if k.endswith("s")}
    kws |= {k + "s" for k in list(kws) if not k.endswith("s")}
    return kws

# ------------------- sidebar / conexión -------------------
st.sidebar.header("Conexión a PostgreSQL")
pg_host = st.sidebar.text_input("PGHOST", os.getenv("PGHOST", "127.0.0.1"))
pg_db   = st.sidebar.text_input("PGDATABASE", os.getenv("PGDATABASE", "chemistry_db"))
pg_user = st.sidebar.text_input("PGUSER", os.getenv("PGUSER", "chem_user"))
pg_pass = st.sidebar.text_input("PGPASSWORD", os.getenv("PGPASSWORD", ""), type="password")

TEMA_DEFAULT = "Química — Base de datos de palabras clave"
tema = st.sidebar.text_input("Tema (aparece en el título)", TEMA_DEFAULT).strip() or TEMA_DEFAULT
umbral = st.sidebar.slider("Umbral para decir: 'ES de Química' (%)", 5, 60, 20, step=1)

st.title(tema)
st.caption("Pega un texto y el sistema calculará el % de coincidencia con el vocabulario de Química (BD PostgreSQL).")

# ------------------- carga de datos -------------------
df = pd.DataFrame()
error = None
try:
    df = load_from_pg(pg_host, pg_db, pg_user, pg_pass)
except Exception as e:
    error = str(e)
    st.error(f"Error de conexión: {error}")
    st.stop()

if df.empty:
    st.error("No se pudieron cargar los datos desde la base de datos.")
    st.stop()

kw_set = build_keyword_set(df)

# ------------------- verificador de tema -------------------
st.subheader("🧪 Verificador de tema (Química)")
texto = st.text_area("Pega aquí el texto a evaluar", height=220, placeholder="Escribe o pega el párrafo aquí...")

col_a, col_b, col_c = st.columns(3)
with col_a:
    modo_den = st.radio("¿Cómo calcular el %?", ["vs. palabras del texto", "vs. vocabulario Química (BD)"], index=0)

if st.button("Evaluar"):
    tokens = tokenize(texto)
    tokens_set = set(tokens)

    # intersección: palabras del texto que están en el vocabulario
    matches = sorted(tokens_set & kw_set)
    n_match = len(matches)

    # Denominador según modo
    if modo_den == "vs. palabras del texto":
        denom = max(1, len(tokens_set))
        nota = "Proporción de palabras del **texto** que pertenecen al vocabulario de Química."
    else:
        denom = max(1, len(kw_set))
        nota = "Cobertura del **vocabulario de Química** presente en el texto (suele dar % pequeño)."

    porcentaje = round(100 * n_match / denom, 2)

    # Veredicto
    if porcentaje >= umbral:
        st.success(f"✅ **ES de Química** — Coincidencia: **{porcentaje}%** (umbral: {umbral}%)")
    else:
        st.warning(f"⚠️ **NO es de Química** — Coincidencia: **{porcentaje}%** (umbral: {umbral}%)")

    st.caption(nota)

    # Detalle
    c1, c2 = st.columns([2, 1])
    with c1:
        st.markdown("**Palabras de Química encontradas en el texto:**")
        if matches:
            st.write(", ".join(matches))
        else:
            st.write("_Ninguna_")
    with c2:
        st.metric("Tokens (únicos) del texto", f"{len(tokens_set):,}")
        st.metric("Coincidencias", f"{n_match:,}")

    # Tabla del vocabulario
    with st.expander("Ver vocabulario de Química (BD)"):
        show = df[["palabra_norm", "sinonimo_norm", "porcentaje_identidad"]].rename(
            columns={"palabra_norm": "palabra", "sinonimo_norm": "sinonimo"}
        ).sort_values(["porcentaje_identidad", "palabra"], ascending=[False, True])
        st.dataframe(show, use_container_width=True, hide_index=True)

