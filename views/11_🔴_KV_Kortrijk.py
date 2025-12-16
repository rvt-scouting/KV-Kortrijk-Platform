import streamlit as st
import pandas as pd
from utils import run_query, show_sidebar_filters, POSITION_METRICS

# -----------------------------------------------------------------------------
# 1. SETUP & DYNAMISCHE FILTERS
# -----------------------------------------------------------------------------
st.set_page_config(page_title="KVK Squad Planner", layout="wide")
season, iteration_id, squad_id = show_sidebar_filters()

if not iteration_id or not squad_id:
    st.warning("Selecteer a.u.b. een seizoen, competitie en club in de zijbalk.")
    st.stop()

st.title(f"🔴 Squad Analyse: {season}")

# -----------------------------------------------------------------------------
# 2. POSITIE MAPPING
# -----------------------------------------------------------------------------
pos_options = {
    "CENTRAL_DEFENDER": "🛡️ Centrale Verdedigers",
    "RIGHT_WINGBACK_DEFENDER": "🏃 Vleugelverdedigers",
    "DEFENSIVE_MIDFIELD": "⚓ Defensieve Middenvelders",
    "CENTRAL_MIDFIELD": "🧠 Centrale Middenvelders",
    "ATTACKING_MIDFIELD": "🪄 Aanvallende Middenvelders",
    "RIGHT_WINGER": "⚡ Buitenspelers",
    "CENTER_FORWARD": "🎯 Spitsen"
}

# -----------------------------------------------------------------------------
# 3. LOOP DOOR ALLE POSITIES (SCROLLABLE)
# -----------------------------------------------------------------------------
for pos_key, pos_label in pos_options.items():
    st.header(pos_label)
    
    metrics_config = POSITION_METRICS.get(pos_key.lower())
    if not metrics_config:
        st.info(f"Geen configuratie voor {pos_label}")
        continue

    # IDs klaarmaken
    relevant_ids = metrics_config.get('aan_bal', []) + metrics_config.get('zonder_bal', [])
    ids_str = ",".join([f"'{x}'" for x in relevant_ids])

    # Data ophalen
    query = f"""
        SELECT p.commonname as "Speler", pfs.metric_id, pfs.final_score_1_to_100 as score, def.name as metric_name
        FROM analysis.player_final_scores pfs
        JOIN analysis.players p ON pfs."playerId" = p.id
        JOIN analysis.playerscores_definitions def ON pfs.metric_id::text = def.id
        WHERE pfs."squadId" = %s AND pfs."iterationId" = %s AND pfs.position = %s
        AND pfs.metric_id IN ({ids_str})
    """
    df_pos = run_query(query, (squad_id, iteration_id, pos_key))

    if not df_pos.empty:
        df_pivot = df_pos.pivot(index='Speler', columns='metric_name', values='score')
        
        # TABEL 1: Individuele Spelers
        st.write("**Individuele Scores:**")
        st.dataframe(df_pivot.style.background_gradient(cmap='RdYlGn', axis=0, vmin=40, vmax=80).format("{:.1f}"), use_container_width=True)

        # TABEL 2: Gemiddeldes (Apart en Opvallend)
        averages = df_pivot.mean().to_frame().T
        averages.index = ["GROEP GEMIDDELDE"]
        
        st.write("**Positie Gemiddelde:**")
        st.table(averages.style.applymap(lambda x: 'background-color: #ffcccc' if x < 60 else 'background-color: #ccffcc').format("{:.1f}"))

        # Werkpunten identificeren
        weak_metrics = averages.iloc[0][averages.iloc[0] < 60]
        
        if not weak_metrics.empty:
            weak_names = weak_metrics.index.tolist()
            weak_ids = df_pos[df_pos['metric_name'].isin(weak_names)]['metric_id'].unique().tolist()
            weak_ids_str = ",".join([f"'{x}'" for x in weak_ids])

            # DROPDOWN: Targets
            with st.expander(f"🔍 Bekijk Versterkingen voor {pos_label} (Zwaktes: {', '.join(weak_names)})"):
                target_query = f"""
                    SELECT p.commonname as "Naam", s.name as "Club", pfs.metric_id, pfs.final_score_1_to_100 as score
                    FROM analysis.player_final_scores pfs
                    JOIN analysis.players p ON pfs."playerId" = p.id
                    JOIN analysis.squads s ON pfs."squadId" = s.id
                    JOIN public.iterations i ON pfs."iterationId" = i.id
                    WHERE i.season IN ('25/26', '2025') AND pfs.position = %s
                    AND pfs.metric_id IN ({weak_ids_str}) AND pfs.final_score_1_to_100 > 60
                    AND pfs."squadId" != %s
                """
                df_targets = run_query(target_query, (pos_key, squad_id))
                
                if not df_targets.empty:
                    summary = df_targets.groupby(['Naam', 'Club']).agg(
                        Matches=('metric_id', 'count'),
                        Avg_Score=('score', 'mean')
                    ).reset_index().sort_values(['Matches', 'Avg_Score'], ascending=False)
                    st.dataframe(summary.head(10), use_container_width=True)
                else:
                    st.write("Geen targets gevonden die alle zwaktes verbeteren.")
        else:
            st.success(f"Positie {pos_label} is optimaal bezet.")
    else:
        st.caption(f"Geen data voor {pos_label}")
    
    st.divider()
