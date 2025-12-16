import streamlit as st
import pandas as pd
# Importeer de functie en de dictionaries uit utils
from utils import run_query, show_sidebar_filters, POSITION_METRICS, get_config_for_position

# -----------------------------------------------------------------------------
# 1. SETUP & DYNAMISCHE FILTERS
# -----------------------------------------------------------------------------
season, iteration_id, squad_id = show_sidebar_filters()

if not iteration_id or not squad_id:
    st.warning("Selecteer a.u.b. een seizoen, competitie en club in de zijbalk.")
    st.stop()

st.title(f"🔴 Squad Analyse: {season}")

# -----------------------------------------------------------------------------
# 2. DEFINIEER DE VOLGORDE VAN DE POSITIES
# -----------------------------------------------------------------------------
# We maken een simpele lijst van de posities die we willen tonen
display_positions = [
    ("CENTRAL_DEFENDER", "🛡️ Centrale Verdedigers"),
    ("RIGHT_WINGBACK_DEFENDER", "🏃 Vleugelverdedigers"),
    ("DEFENSIVE_MIDFIELD", "⚓ Defensieve Middenvelders"),
    ("CENTRAL_MIDFIELD", "🧠 Centrale Middenvelders"),
    ("ATTACKING_MIDFIELD", "🪄 Aanvallende Middenvelders"),
    ("RIGHT_WINGER", "⚡ Buitenspelers"),
    ("CENTER_FORWARD", "🎯 Spitsen")
]

# -----------------------------------------------------------------------------
# 3. DE LOOP: ANALYSE PER POSITIE
# -----------------------------------------------------------------------------
for db_pos, display_label in display_positions:
    # Gebruik je bestaande functie uit utils om de juiste metrics te pakken 
    metrics_config = get_config_for_position(db_pos, POSITION_METRICS)
    
    if not metrics_config:
        continue

    st.header(display_label)
    
    # Haal alle relevante IDs op (zoals gedefinieerd in POSITION_METRICS) 
    rel_ids = metrics_config.get('aan_bal', []) + metrics_config.get('zonder_bal', [])
    ids_str = ",".join([f"'{x}'" for x in rel_ids])

    # SQL Query (Let op de casting naar text voor de IDs) 
    query = f"""
        SELECT 
            p.commonname as "Speler", 
            pfs.metric_id, 
            pfs.final_score_1_to_100 as score, 
            def.name as metric_name
        FROM analysis.player_final_scores pfs
        JOIN analysis.players p ON pfs."playerId" = p.id
        JOIN analysis.playerscores_definitions def ON pfs.metric_id::text = def.id
        WHERE pfs."squadId"::text = %s 
          AND pfs."iterationId"::text = %s 
          AND pfs.position = %s
          AND pfs.metric_id IN ({ids_str})
    """
    df_pos = run_query(query, (squad_id, iteration_id, db_pos))

    if not df_pos.empty:
        # --- TABEL 1: SPELERS ---
        df_pivot = df_pos.pivot(index='Speler', columns='metric_name', values='score')
        st.write("### 👤 Individuele Scores")
        st.dataframe(
            df_pivot.style.background_gradient(cmap='RdYlGn', axis=0, vmin=40, vmax=80).format("{:.1f}"), 
            use_container_width=True
        )

        # --- TABEL 2: GEMIDDELDEN (Gestyleerd als de spelerstabel) ---
        st.write("### 📊 Positie Gemiddelde")
        averages = df_pivot.mean().to_frame().T
        averages.index = ["GROEP GEMIDDELDE"]
        st.dataframe(
            averages.style.background_gradient(cmap='RdYlGn', axis=1, vmin=40, vmax=80).format("{:.1f}"),
            use_container_width=True
        )

        # --- TARGET FINDER ---
        weak_metrics = averages.iloc[0][averages.iloc[0] < 60]
        if not weak_metrics.empty:
            weak_names = weak_metrics.index.tolist()
            # Haal IDs op voor de zwakke punten
            weak_ids = df_pos[df_pos['metric_name'].isin(weak_names)]['metric_id'].unique().tolist()
            weak_ids_str = ",".join([f"'{x}'" for x in weak_ids])

            with st.expander(f"🎯 Versterkingen voor: {', '.join(weak_names)}"):
                # Query voor targets die > 60 scoren op onze zwakke punten 
                target_query = f"""
                    SELECT 
                        p.commonname as "Naam", 
                        s.name as "Club", 
                        def.name as metric_name,
                        pfs.final_score_1_to_100 as score
                    FROM analysis.player_final_scores pfs
                    JOIN analysis.players p ON pfs."playerId" = p.id
                    JOIN analysis.squads s ON pfs."squadId" = s.id
                    JOIN public.iterations i ON pfs."iterationId" = i.id
                    JOIN analysis.playerscores_definitions def ON pfs.metric_id::text = def.id
                    WHERE (i.season = '25/26' OR i.season = '2025')
                      AND pfs.position = %s
                      AND pfs.metric_id IN ({weak_ids_str}) 
                      AND pfs.final_score_1_to_100 > 60
                      AND pfs."squadId"::text != %s
                """
                df_targets_raw = run_query(target_query, (db_pos, squad_id))
                
                if not df_targets_raw.empty:
                    df_target_pivot = df_targets_raw.pivot(index=['Naam', 'Club'], columns='metric_name', values='score')
                    df_target_pivot['Gaten Gedicht'] = df_target_pivot.notnull().sum(axis=1)
                    df_target_pivot = df_target_pivot.sort_values('Gaten Gedicht', ascending=False)
                    
                    st.dataframe(
                        df_target_pivot.style.background_gradient(cmap='RdYlGn', axis=None, vmin=40, vmax=80)
                        .format("{:.1f}", na_rep="-"),
                        use_container_width=True
                    )
        else:
            st.success("Deze positie scoort gemiddeld boven de norm.")
    
    st.divider()
