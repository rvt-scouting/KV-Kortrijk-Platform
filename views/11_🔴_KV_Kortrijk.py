import streamlit as st
import pandas as pd
import plotly.express as px
from utils import run_query, show_sidebar_filters, POSITION_METRICS, get_config_for_position

# -----------------------------------------------------------------------------
# 1. CONSTANTEN EN SETUP
# -----------------------------------------------------------------------------
KVK_SQUAD_ID = '362'  # Jouw specifieke Squad ID 

st.set_page_config(page_title="KV Kortrijk Analyse", layout="wide")
st.title("🔴 KV Kortrijk: Club Dashboard")

# Gebruik de sidebar filters voor de context (Seizoen/Competitie) 
season, iteration_id = show_sidebar_filters()

if not iteration_id:
    st.warning("Selecteer a.u.b. een seizoen en competitie in de zijbalk om de analyse te starten.")
    st.stop()

# -----------------------------------------------------------------------------
# 2. SPEELSTIJL ANALYSE
# -----------------------------------------------------------------------------
st.header("📊 Team Profiel & Speelstijl")

# Query op basis van de analyse schema tabellen 
style_query = """
    SELECT profile_name, score 
    FROM analysis.squad_profile_scores 
    WHERE "squadId" = %s AND "iterationId" = %s
"""
df_style = run_query(style_query, (KVK_SQUAD_ID, iteration_id))

if not df_style.empty:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.subheader("Speelstijl Scores")
        st.dataframe(df_style.sort_values('score', ascending=False), hide_index=True)
    with col2:
        fig = px.bar(df_style, x='score', y='profile_name', orientation='h', 
                     color='score', color_continuous_scale='Reds',
                     title="Tactische Identiteit")
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Geen speelstijl data beschikbaar voor deze selectie.")

# -----------------------------------------------------------------------------
# 3. POSITIE-SPECIFIEKE GAP ANALYSE
# -----------------------------------------------------------------------------
st.divider()
st.header("⚽ Positie Analyse & Verbeterpunten")

# Mapping van database posities naar leesbare tekst 
pos_options = {
    "CENTRAL_DEFENDER": "Centrale Verdediger",
    "RIGHT_WINGBACK_DEFENDER": "Vleugelverdediger (R)",
    "DEFENSIVE_MIDFIELD": "Defensieve Middenvelder",
    "CENTRAL_MIDFIELD": "Centrale Middenvelder",
    "ATTACKING_MIDFIELD": "Aanvallende Middenvelder",
    "RIGHT_WINGER": "Buitenspeler (R)",
    "CENTER_FORWARD": "Spits"
}

selected_pos_key = st.selectbox("Kies een positie om te evalueren:", list(pos_options.keys()), format_func=lambda x: pos_options[x])

# Haal de specifieke metrics op uit de configuratie in utils.py 
metrics_config = get_config_for_position(selected_pos_key, POSITION_METRICS)

if metrics_config:
    # Combineer alle relevante metric IDs voor deze positie 
    relevant_ids = metrics_config.get('aan_bal', []) + metrics_config.get('zonder_bal', [])
    
    # Query om de prestaties van onze eigen spelers op te halen 
    kvk_players_query = f"""
        SELECT 
            p.commonname as "Speler",
            pfs.metric_id,
            pfs.final_score_1_to_100 as score,
            def.name as metric_name
        FROM analysis.player_final_scores pfs
        JOIN analysis.players p ON pfs."playerId" = p.id
        JOIN analysis.playerscores_definitions def ON pfs.metric_id::text = def.id
        WHERE pfs."squadId" = %s 
          AND pfs."iterationId" = %s 
          AND pfs.position = %s
          AND pfs.metric_id IN ({','.join(map(str, relevant_ids))})
    """
    df_kvk = run_query(kvk_players_query, (KVK_SQUAD_ID, iteration_id, selected_pos_key))

    if not df_kvk.empty:
        # Pivoteren voor een overzichtelijke tabel 
        df_kvk_pivot = df_kvk.pivot(index='Speler', columns='metric_name', values='score')
        
        st.subheader(f"Huidige Bezetting: {pos_options[selected_pos_key]}")
        st.write("Hieronder zie je de scores van onze huidige spelers op de belangrijkste metrics:")
        st.dataframe(df_kvk_pivot.style.background_gradient(cmap='RdYlGn', axis=None, vmin=40, vmax=80))

        # Bereken gemiddeldes en identificeer zwakke punten (< 60) 
        averages = df_kvk_pivot.mean().round(1)
        weak_metrics = averages[averages < 60]
        
        if not weak_metrics.empty:
            st.warning(f"⚠️ **Gedetecteerde zwaktes (Gemiddelde < 60):** {', '.join(weak_metrics.index.tolist())}")
            
            # IDs ophalen van de zwakke metrics voor de target search 
            weak_ids = df_kvk[df_kvk['metric_name'].isin(weak_metrics.index)]['metric_id'].unique().tolist()

            # -----------------------------------------------------------------------------
            # 4. TRANSFER TARGET FINDER
            # -----------------------------------------------------------------------------
            st.divider()
            st.header(f"🔎 Marktverkenning: Oplossingen voor {pos_options[selected_pos_key]}")
            st.info(f"Gezocht naar spelers (Seizoen 25/26 of 2025) die hoger dan 60 scoren op onze zwakke punten.")

            target_query = f"""
                SELECT 
                    p.commonname as "Naam",
                    s.name as "Club",
                    pfs.metric_id,
                    pfs.final_score_1_to_100 as score
                FROM analysis.player_final_scores pfs
                JOIN analysis.players p ON pfs."playerId" = p.id
                JOIN analysis.squads s ON pfs."squadId" = s.id
                JOIN public.iterations i ON pfs."iterationId" = i.id
                WHERE (i.season = '25/26' OR i.season = '2025')
                  AND pfs.position = %s
                  AND pfs.metric_id IN ({','.join(map(str, weak_ids))})
                  AND pfs.final_score_1_to_100 > 60
                  AND pfs."squadId" != %s
            """
            df_targets_raw = run_query(target_query, (selected_pos_key, KVK_SQUAD_ID))

            if not df_targets_raw.empty:
                # Analyseer welke speler de meeste 'gaten' dicht 
                target_summary = df_targets_raw.groupby(['Naam', 'Club']).agg(
                    Dicht_Aantal_Gaten=('metric_id', 'count'),
                    Gemiddelde_Score=('score', 'mean')
                ).reset_index()

                # Sorteer: meeste opgeloste zwaktes eerst 
                target_summary = target_summary.sort_values(by=['Dicht_Aantal_Gaten', 'Gemiddelde_Score'], ascending=False)
                
                st.table(target_summary.head(15))
            else:
                st.write("Geen directe versterkingen gevonden op de markt die op alle zwakke punten boven de 60 scoren.")
        else:
            st.success("✅ Geen kritieke zwakke punten gevonden voor deze positie. De groep scoort gemiddeld boven de 60.")
    else:
        st.info("Er is momenteel geen spelersdata voor deze positie bij KV Kortrijk.")
