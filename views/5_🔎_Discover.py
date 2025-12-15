import streamlit as st
import plotly.express as px
from utils import run_query, show_sidebar_filters

# Pagina configuratie
st.set_page_config(page_title="Discover", page_icon="🔎", layout="wide")
st.title("🔎 Discover & Data Visualisatie")

# 1. Filters uit de sidebar halen (via utils)
selected_season, selected_iteration_id = show_sidebar_filters()

if not selected_iteration_id:
    st.info("👈 Selecteer links een seizoen en competitie om te beginnen.")
    st.stop()

# 2. Data ophalen
# We gebruiken nu directe joins omdat de IDs allemaal tekst zijn.
@st.cache_data
def get_analysis_data(iter_id):
    query = """
        SELECT 
            p.commonname as "Naam", 
            sq.name as "Team", 
            a.* FROM analysis.final_impect_scores a
        JOIN public.players p ON a."playerId" = p.id
        LEFT JOIN public.squads sq ON a."squadId" = sq.id
        WHERE a."iterationId" = %s
    """
    # We sturen iter_id als parameter mee (string)
    return run_query(query, params=(str(iter_id),))

df = get_analysis_data(selected_iteration_id)

if not df.empty:
    # 3. Automatisch numerieke kolommen vinden voor de assen
    # We filteren kolommen die 'score' bevatten en negeren IDs
    score_cols = [c for c in df.columns if 'score' in c.lower() and c not in ['playerId', 'squadId', 'iterationId']]
    
    if not score_cols:
        st.error("Geen score-kolommen gevonden in de tabel.")
        st.stop()
        
    st.divider()
    
    # 4. Instellingen voor de grafiek
    col_filters, col_x, col_y = st.columns([1, 1, 1])
    
    with col_filters:
        st.markdown("##### 1. Filter Data")
        # Optioneel: filter op positie als die kolom bestaat
        if 'position' in df.columns:
            posities = ["Alle"] + sorted(df['position'].dropna().unique().tolist())
            filter_pos = st.selectbox("Positie", posities)
            if filter_pos != "Alle":
                df = df[df['position'] == filter_pos]
    
    with col_x:
        st.markdown("##### 2. X-As")
        x_axis = st.selectbox("Kies statistiek X", score_cols, index=0)
        
    with col_y:
        st.markdown("##### 3. Y-As")
        # Probeer slim de tweede kolom als default te pakken
        default_y_index = 1 if len(score_cols) > 1 else 0
        y_axis = st.selectbox("Kies statistiek Y", score_cols, index=default_y_index)

    # 5. Scatter Plot Genereren
    if not df.empty:
        fig = px.scatter(
            df, 
            x=x_axis, 
            y=y_axis, 
            hover_data=['Naam', 'Team'], # Wat zie je als je muist?
            color='Team',                # Kleur bolletjes per team
            title=f"{x_axis} vs {y_axis} ({selected_season})",
            height=600,
            template="plotly_white"      # Schone witte achtergrond
        )
        
        # Maak de bolletjes iets groter en duidelijker
        fig.update_traces(marker=dict(size=10, line=dict(width=1, color='DarkSlateGrey')))
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Geen spelers overgebleven na filteren.")

    # 6. Ruwe data tabel (in een uitklapmenu om het netjes te houden)
    with st.expander("Bekijk de tabel"):
        display_cols = ['Naam', 'Team'] + ([x_axis, y_axis] if x_axis != y_axis else [x_axis])
        st.dataframe(df[display_cols].sort_values(by=x_axis, ascending=False))

else:
    st.error("Geen data gevonden voor deze competitie. Check of de iterationId's in de tabellen overeenkomen.")
