import streamlit as st
import pandas as pd
import plotly.express as px
from utils import run_query, show_sidebar_filters

st.set_page_config(page_title="Discover", page_icon="🔎", layout="wide")

st.title("🔎 Discover & Data Visualisatie")

# 1. Filters ophalen (Seizoen & Competitie)
selected_season, selected_iteration_id = show_sidebar_filters()

if not selected_iteration_id:
    st.warning("Selecteer eerst een competitie in de zijbalk.")
    st.stop()

st.markdown("### 📊 Vergelijk spelers met Scatter Plots")
st.info("Kies hieronder twee statistieken om spelers tegen elkaar uit te zetten.")

# 2. Data ophalen (Alle scores van dit seizoen/competitie)
# We halen even alles op om mee te spelen
@st.cache_data
def get_discovery_data(iteration_id):
    query = """
        SELECT 
            p.commonname as "Naam", 
            sq.name as "Team", 
            a.position as "Positie",
            -- We pakken een paar generieke scores om te testen
            a.cb_kvk_score as "CV Score",
            a.fw_kvk_score as "Spits Score",
            a.playmaker_dm_kvk_score as "Spelmaker Score",
            a.ball_winning_dm_kvk_score as "Ballenafpakker Score"
        FROM analysis.final_impect_scores a
        JOIN public.players p ON a."playerId" = p.id
        LEFT JOIN public.squads sq ON a."squadId" = sq.id
        WHERE a."iterationId" = %s
    """
    return run_query(query, params=(iteration_id,))

df = get_discovery_data(selected_iteration_id)

if not df.empty:
    # 3. Instellingen voor de grafiek
    col1, col2, col3 = st.columns(3)
    with col1:
        # Filter op positie
        posities = ["Alle"] + df['Positie'].unique().tolist()
        filter_pos = st.selectbox("Filter op Positie:", posities)
    
    # Filter data op positie indien nodig
    if filter_pos != "Alle":
        plot_df = df[df['Positie'] == filter_pos]
    else:
        plot_df = df

    # Kies assen (alle kolommen behalve Naam/Team/Positie)
    numeric_cols = ["CV Score", "Spits Score", "Spelmaker Score", "Ballenafpakker Score"]
    
    with col2:
        x_axis = st.selectbox("X-As (Horizontaal):", numeric_cols, index=0)
    with col3:
        y_axis = st.selectbox("Y-As (Verticaal):", numeric_cols, index=1)

    # 4. Grafiek Tekenen
    fig = px.scatter(
        plot_df, 
        x=x_axis, 
        y=y_axis, 
        hover_data=['Naam', 'Team', 'Positie'],
        color='Team', # Kleur op basis van team
        title=f"{x_axis} vs {y_axis}",
        height=600
    )
    # Zorg dat de namen erbij staan als je eroverheen muist
    fig.update_traces(marker=dict(size=12, line=dict(width=1, color='DarkSlateGrey')))
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 5. Tabel tonen
    with st.expander("Bekijk ruwe data"):
        st.dataframe(plot_df)

else:
    st.error("Geen data gevonden voor deze selectie.")
