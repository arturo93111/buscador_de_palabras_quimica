import os
import re
import unicodedata
import pandas as pd
import streamlit as st

from sqlalchemy import create_engine, text

st.set_page_config(page_title="Química — Verificador de tema", page_icon="🧪", layout="wide")

# --------------------------------------------------------------
# 🔧 Funciones de utilidad
# --------------------------------------------------------------
def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def tokenize(text: str):
    clean = strip_accents(text.lower())
    return re.findall(r"[a-z0-9]+", clean)

# --------------------------------------------------------------
# 🔌 Conectar a PostgreSQL (Render o local)
# --------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_from_pg(pg_host, pg_db, pg_user, pg_pass):
    # 1) Si Render provee DATABASE_URL, úsala
    db_url = os.getenv("DATABASE_URL")

    if db_url:
        st.info("Conectando mediante DATABASE_URL (Render Cloud)...")
        engine = create_engine(db_url, connect_args={"sslmode": "require"})
    else:
        st.info("Conectando al PostgreSQL LOCAL...")
        engine = create_engine(
            f"postgresql+psycopg2://{pg_user}:{pg_pass}@{pg_host}:5432/{pg_db}"
        )

    query = """
        SELECT 
            id,
            lower(unaccent(palabra)) AS palabra_norm,
            lower(unaccent(
                CASE 
                    WHEN pg_typeof(sinonimos)::text LIKE 'text[]' THEN array_to_string(sinonimos, ',')
                    ELSE sinonimos::text
                END
            )) AS sinonimos_txt,
            porcentaje_identidad
        FROM quimica.palabras_quimica
        ORDER BY palabra;
    """

    with engine.begin() as conn:
        df = pd.read_sql(text(query), conn)

    # Normalizar
    df["palabra_norm"] = df["palabra_norm"].apply(strip_accents)
    df["sinonimo_norm"] = df["sinonimos_txt"].fillna("").apply(
        lambda s: strip_accents(s.split(",")[0]).strip().replace(" ", "_")
    )

    return df

# --------------------------------------------------------------
# Generar conjunto de palabras clave
# --------------------------------------------------------------
@st.cache_data(show_spinner=False)
def build_keyword_set(df: pd.DataFrame) -> set:
    kws = set()

    for _, row in df.iterrows():
        if row["palabra_norm"]:
            kws.add(row["palabra_norm"])
        if row["sinonimo_norm"]:
            kws.add(row["sinonimo_norm"])

    # Variantes singular/plural básicas
    kws |= {k.rstrip("s") for k in list(kws) if k.endswith("s")}
    kws |= {k + "s" for k in list(kws) if not k.endswith("s")}

    return kws

# --------------------------------------------------------------
# 🔧 Sidebar
# --------------------------------------------------------------
st.sidebar.header("Conexión PostgreSQL")

# Si Render tiene DATABASE_URL, ocultamos los campos locales
RENDER = os.getenv("DATABASE_URL") is not None

if not RENDER:
    pg_host = st.sidebar.text_input("PGHOST", "127.0.0.1")
    pg_db   = st.sidebar.text_input("PGDATABASE", "chemistry_db")
    pg_user = st.sidebar.text_input("PGUSER", "chem_user")
    pg_pass = st.sidebar.text_input("PGPASSWORD", "", type="password")
else:
    st.sidebar.success("Render detectado: usando DATABASE_URL automáticamente.")
    pg_host = pg_db = pg_user = pg_pass = None

TEMA_DEFAULT = "Química — Base de datos de palabras clave"
tema = st.sidebar.text_input("Tema (aparece en el título)", TEMA_DEFAULT).strip() or TEMA_DEFAULT

umbral = st.sidebar.slider("Umbral para decir: 'ES de Química' (%)", 5, 60, 20)

# --------------------------------------------------------------
# 🔍 Título
# --------------------------------------------------------------
st.title(tema)
st.caption("Pega un texto y el sistema calculará el % de coincidencia con el vocabulario de Química.")

# --------------------------------------------------------------
# 📥 Cargar datos
# --------------------------------------------------------------
try:
    df = load_from_pg(pg_host, pg_db, pg_user, pg_pass)
except Exception as e:
    st.error("❌ No se pudo conectar a la base de datos.")
    st.code(str(e))
    st.stop()

kw_set = build_keyword_set(df)

# --------------------------------------------------------------
# 🧪 Verificador
# --------------------------------------------------------------
st.subheader("🧪 Verificador de tema (Química)")

texto = st.text_area("Pega aquí el texto a evaluar:", height=220)

modo = st.radio("¿Cómo calcular el %?", ["vs. palabras del texto", "vs. vocabulario Química"])

if st.button("Evaluar"):
    tokens = tokenize(texto)
    tokens_set = set(tokens)

    matches = sorted(tokens_set & kw_set)
    n_match = len(matches)

    if modo == "vs. palabras del texto":
        denom = max(1, len(tokens_set))
    else:
        denom = max(1, len(kw_set))

    porcentaje = round(100 * n_match / denom, 2)

    if porcentaje >= umbral:
        st.success(f"✅ **ES de Química** — {porcentaje}% de coincidencia")
    else:
        st.warning(f"⚠️ **NO es de Química** — {porcentaje}% de coincidencia")

    # Mostrar coincidencias
    st.markdown("### Palabras encontradas:")
    st.write(", ".join(matches) if matches else "_Ninguna_")

    # Mostrar tabla completa
    with st.expander("Ver vocabulario completo"):
        show = df[["palabra_norm", "sinonimo_norm", "porcentaje_identidad"]].rename(
            columns={"palabra_norm": "palabra", "sinonimo_norm": "sinonimo"}
        )
        st.dataframe(show, use_container_width=True, hide_index=True)

