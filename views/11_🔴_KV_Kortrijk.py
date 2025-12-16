import streamlit as st
import pandas as pd
import plotly.express as px
from utils import run_query, show_sidebar_filters, POSITION_METRICS, get_config_for_position

# -----------------------------------------------------------------------------
# 1. CONSTANTEN EN SETUP
# -----------------------------------------------------------------------------
KVK_SQUAD_ID = '362' 

st.title("🔴 KV Kortrijk: Club Dashboard")

# Gebruik de sidebar filters voor de context
season, iteration_id = show_sidebar_filters()

if not iteration_id:
    st.warning("Selecteer a.u.b. een seizoen en competitie in de zijbalk.")
    st.stop()

# -----------------------------------------------------------------------------
# 2. TEAM PROFIEL
# -----------------------------------------------------------------------------
st.header("📊 Team Profiel & Speelstijl")

style_query = """
    SELECT profile_name, score 
    FROM analysis.squad_profile_scores 
    WHERE "squadId" = %s AND "iterationId" = %s
"""
df_style = run_query(style_query, (KVK_SQUAD_ID, iteration_id))

if not df_style.empty:
    col1, col2 = st.columns([1, 2])
    with col1:
        st.dataframe(df_style.sort_values('score', ascending=False), hide_index=True)
    with col2:
        fig = px.bar(df_style, x='score', y='profile_name', orientation='h', 
                     color='score', color_continuous_scale='Reds')
        st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# 3. POSITIE ANALYSE (MET FIX VOOR DATATYPES)
# -----------------------------------------------------------------------------
st.divider()
st.header("⚽ Positie Analyse & Verbeterpunten")

pos_options = {
    "CENTRAL_DEFENDER": "Centrale Verdediger",
    "RIGHT_WINGBACK_DEFENDER": "Vleugelverdediger (R)",
    "DEFENSIVE_MIDFIELD": "Defensieve Middenvelder",
    "CENTRAL_MIDFIELD": "Centrale Middenvelder",
    "ATTACKING_MIDFIELD": "Aanvallende Middenvelder",
    "RIGHT_WINGER": "Buitenspeler (R)",
    "CENTER_FORWARD": "Spits"
}

selected_pos_key = st.selectbox("Kies een positie:", list(pos_options.keys()), format_func=lambda x: pos_options[x])
metrics_config = get_config_for_position(selected_pos_key, POSITION_METRICS)

if metrics_config:
    relevant_ids = metrics_config.get('aan_bal', []) + metrics_config.get('zonder_bal', [])
    
    # FIX: Zet de IDs om naar een string van gequoteerde waarden: '66','58','64',...
    ids_string = ",".join([f"'{x}'" for x in relevant_ids])
    
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
          AND pfs.metric_id IN ({ids_string})
    """
    df_kvk = run_query(kvk_players_query, (KVK_SQUAD_ID, iteration_id, selected_pos_key))

    if not df_kvk.empty:
        df_kvk_pivot = df_kvk.pivot(index='Speler', columns='metric_name', values='score')
        st.subheader(f"Huidige Bezetting: {pos_options[selected_pos_key]}")
        st.dataframe(df_kvk_pivot.style.background_gradient(cmap='RdYlGn', axis=None, vmin=40, vmax=80))

        averages = df_kvk_pivot.mean().round(1)
        weak_metrics = averages[averages < 60]
        
        if not weak_metrics.empty:
            st.warning(f"⚠️ **Zwakke punten:** {', '.join(weak_metrics.index.tolist())}")
            
            # Verkrijg de IDs van de zwakke metrics voor de volgende query
            weak_ids = df_kvk[df_kvk['metric_name'].isin(weak_metrics.index)]['metric_id'].unique().tolist()
            # FIX: Ook hier quoten voor de IN clausule
            weak_ids_string = ",".join([f"'{x}'" for x in weak_ids])

            # -----------------------------------------------------------------------------
            # 4. TRANSFER TARGET FINDER (MET FIX)
            # -----------------------------------------------------------------------------
            st.divider()
            st.header("🔎 Marktverkenning")
            
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
                  AND pfs.metric_id IN ({weak_ids_string})
                  AND pfs.final_score_1_to_100 > 60
                  AND pfs."squadId" != %s
            """
            df_targets_raw = run_query(target_query, (selected_pos_key, KVK_SQUAD_ID))

            if not df_targets_raw.empty:
                target_summary = df_targets_raw.groupby(['Naam', 'Club']).agg(
                    Dicht_Aantal_Gaten=('metric_id', 'count'),
                    Gemiddelde_Score=('score', 'mean')
                ).reset_index().sort_values(by=['Dicht_Aantal_Gaten', 'Gemiddelde_Score'], ascending=False)
                
                st.table(target_summary.head(15))
            else:
                st.write("Geen versterkingen gevonden op de markt voor deze criteria.")
        else:
            st.success("✅ Geen kritieke zwakke punten gevonden.")
