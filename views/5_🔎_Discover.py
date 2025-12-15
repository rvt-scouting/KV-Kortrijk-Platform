import streamlit as st
import plotly.express as px
import pandas as pd
from utils import run_query

# -----------------------------------------------------------------------------
# 1. SETUP & CONFIGURATIE
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Discover", page_icon="🔎", layout="wide")
st.title("🔎 Discover & Data Visualisatie")

# -----------------------------------------------------------------------------
# 2. CUSTOM SIDEBAR (Specifiek voor Discover)
# -----------------------------------------------------------------------------
st.sidebar.header("1. Selecteer Data")

# A. Seizoen (Verplicht)
season_query = "SELECT DISTINCT season FROM public.iterations ORDER BY season DESC;"
try:
    df_seasons = run_query(season_query)
    seasons_list = df_seasons['season'].tolist()
    
    # Sessie status behouden als die er is
    idx = 0
    if "sb_season" in st.session_state and st.session_state.sb_season in seasons_list:
        idx = seasons_list.index(st.session_state.sb_season)
    
    selected_season = st.sidebar.selectbox("Seizoen:", seasons_list, index=idx, key="sb_season")
except Exception as e:
    st.error("Kon seizoenen niet laden.")
    st.stop()

# B. Competitie (Optioneel)
iter_query = """
    SELECT id, "competitionName" 
    FROM public.iterations 
    WHERE season = %s 
    ORDER BY "competitionName"
"""
df_iters = run_query(iter_query, params=(selected_season,))

if df_iters.empty:
    st.warning("Geen competities gevonden voor dit seizoen.")
    st.stop()

# Opties: "Alle Competities" + specifieke competities
comp_options = ["Alle Competities"] + df_iters['competitionName'].tolist()
selected_comp_name = st.sidebar.selectbox("Competitie:", comp_options)

# C. Bepaal welke IDs we ophalen
if selected_comp_name == "Alle Competities":
    target_ids = df_iters['id'].tolist() # Alles van dit seizoen
    st.sidebar.caption(f"Data van {len(target_ids)} competities.")
else:
    target_ids = df_iters[df_iters['competitionName'] == selected_comp_name]['id'].tolist()

target_ids_tuple = tuple(str(x) for x in target_ids)
st.sidebar.divider()

# -----------------------------------------------------------------------------
# 3. DATA OPHALEN
# -----------------------------------------------------------------------------
@st.cache_data
def get_analysis_data(ids_tuple):
    # We joinen iterations om de competitienaam te hebben
    query = """
        SELECT 
            p.commonname as "Naam", 
            sq.name as "Team", 
            i."competitionName" as "Competitie",
            a.* FROM analysis.final_impect_scores a
        JOIN public.players p ON a."playerId" = p.id
        LEFT JOIN public.squads sq ON a."squadId" = sq.id
        JOIN public.iterations i ON a."iterationId" = i.id
        WHERE a."iterationId" IN %s
    """
    return run_query(query, params=(ids_tuple,))

df = get_analysis_data(target_ids_tuple)

if df.empty:
    st.warning("Geen data gevonden.")
    st.stop()

# -----------------------------------------------------------------------------
# 4. GRAFIEK INSTELLINGEN
# -----------------------------------------------------------------------------
# Filter kolommen (geen IDs of tekst)
exclude_cols = ['playerId', 'squadId', 'iterationId', 'Naam', 'Team', 'Competitie', 'position', 'birthdate']
numeric_cols = [c for c in df.columns if c not in exclude_cols and pd.api.types.is_numeric_dtype(df[c])]
numeric_cols.sort()

# We verdelen de ruimte nu in 3 kolommen i.p.v. 4
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("##### 📍 Assen")
    x_axis = st.selectbox("X-As", numeric_cols, index=0 if len(numeric_cols) > 0 else 0)
    # Slimme selectie voor Y (probeer een andere dan X te kiezen)
    def_y = 1 if len(numeric_cols) > 1 else 0
    y_axis = st.selectbox("Y-As", numeric_cols, index=def_y)

with c2:
    st.markdown("##### 🕵️ Filter Positie")
    if 'position' in df.columns:
        positions = ["Alle"] + sorted(df['position'].dropna().unique().tolist())
        sel_pos = st.selectbox("Kies positie:", positions)
        if sel_pos != "Alle":
            df = df[df['position'] == sel_pos]

with c3:
    st.markdown("##### 🛡️ Filter Teams")
    all_teams = sorted(df['Team'].dropna().unique().tolist())
    sel_teams = st.multiselect("Specifieke teams (leeg = alles):", all_teams)
    if sel_teams:
        df = df[df['Team'].isin(sel_teams)]

# -----------------------------------------------------------------------------
# 5. VISUALISATIE
# -----------------------------------------------------------------------------
st.divider()

if not df.empty:
    # Titel dynamisch maken
    chart_title = f"{x_axis} vs {y_axis} | {selected_season}"
    if selected_comp_name != "Alle Competities":
        chart_title += f" ({selected_comp_name})"

    fig = px.scatter(
        df, 
        x=x_axis, 
        y=y_axis, 
        color='Team',  # Standaard altijd kleuren op Team
        hover_data=['Naam', 'Team', 'Competitie', 'position'], 
        title=chart_title,
        height=700,
        template="plotly_white",
        text='Naam' if len(df) < 50 else None # Namen tonen bij kleine selecties
    )
    
    # Styling
    fig.update_traces(
        marker=dict(size=12, line=dict(width=1, color='DarkSlateGrey')),
        textposition='top center'
    )
    
    st.plotly_chart(fig, use_container_width=True)

    # -------------------------------------------------------------------------
    # 6. DETAIL TABEL
    # -------------------------------------------------------------------------
    with st.expander("📄 Bekijk bron data van selectie"):
        show_cols = ['Naam', 'Team', 'position', 'Competitie', x_axis, y_axis]
        st.dataframe(
            df[show_cols].sort_values(by=x_axis, ascending=False),
            use_container_width=True
        )

else:
    st.error("Geen spelers overgebleven na filters.")
