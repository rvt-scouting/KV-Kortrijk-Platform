import streamlit as st
import pandas as pd
# We importeren de benodigde functies en configuraties uit jouw utils.py
from utils import run_query, show_sidebar_filters, POSITION_METRICS, get_config_for_position

# -----------------------------------------------------------------------------
# 1. SETUP & FILTERS (GELINKT AAN JOUW UTILS.PY)
# -----------------------------------------------------------------------------
# Jouw utils.py geeft exact deze 2 waarden terug
season, iteration_id = show_sidebar_filters()

# Omdat jouw utils.py geen club-filter heeft, halen we de clublijst hier op
# zodat we niets aan utils.py hoeven te veranderen.
selected_squad_id = None
if iteration_id:
    st.sidebar.divider()
    st.sidebar.subheader("2. Specifieke Club")
    
    # Query om alle clubs in de geselecteerde competitie op te halen
    squad_query = """
        SELECT DISTINCT s.id, s.name 
        FROM analysis.squads s
        JOIN analysis.player_final_scores pfs ON s.id = pfs."squadId"::text
        WHERE pfs."iterationId"::text = %s
        ORDER BY s.name
    """
    df_squads = run_query(squad_query, (iteration_id,))
    
    if not df_squads.empty:
        squad_map = dict(zip(df_squads['name'], df_squads['id']))
        squad_names = list(squad_map.keys())
        
        # We zetten KV Kortrijk als standaard als deze in de lijst staat
        default_idx = squad_names.index('KV Kortrijk') if 'KV Kortrijk' in squad_names else 0
        sel_squad_name = st.sidebar.selectbox("Kies Club:", squad_names, index=default_idx)
        selected_squad_id = squad_map[sel_sq_name]

if not iteration_id or not selected_squad_id:
    st.warning("Selecteer a.u.b. een seizoen, competitie en club in de zijbalk.")
    st.stop()

st.title(f"🔴 Squad Analyse: {sel_squad_name} ({season})")

# -----------------------------------------------------------------------------
# 2. POSITIE DEFINITIES (VOLGORDE OP DE PAGINA)
# -----------------------------------------------------------------------------
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
    metrics_config = get_config_for_position(db_pos, POSITION_METRICS)
    if not metrics_config:
        continue

    st.header(display_label)
    
    # IDs voorbereiden (text cast voor de database)
    rel_ids = metrics_config.get('aan_bal', []) + metrics_config.get('zonder_bal', [])
    ids_str = ",".join([f"'{x}'" for x in rel_ids])

    # Query voor de clubspelers
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
    df_pos = run_query(query, (selected_squad_id, iteration_id, db_pos))

    if not df_pos.empty:
        # GEBRUIK pivot_table met mean om de 'Duplicate entries' error te voorkomen
        df_pivot = df_pos.pivot_table(index='Speler', columns='metric_name', values='score', aggfunc='mean')
        
        st.write("### 👤 Individuele Scores")
        st.dataframe(
            df_pivot.style.background_gradient(cmap='RdYlGn', axis=0, vmin=40, vmax=80).format("{:.1f}"), 
            use_container_width=True
        )

        # Positie Gemiddelde
        st.write("### 📊 Positie Gemiddelde")
        averages = df_pivot.mean().to_frame().T
        averages.index = ["GROEP GEMIDDELDE"]
        st.dataframe(
            averages.style.background_gradient(cmap='RdYlGn', axis=1, vmin=40, vmax=80).format("{:.1f}"),
            use_container_width=True
        )

        # --- TARGET FINDER (EXPANDER) ---
        weak_metrics = averages.iloc[0][averages.iloc[0] < 60]
        if not weak_metrics.empty:
            weak_names = weak_metrics.index.tolist()
            weak_ids = df_pos[df_pos['metric_name'].isin(weak_names)]['metric_id'].unique().tolist()
            weak_ids_str = ",".join([f"'{x}'" for x in weak_ids])

            with st.expander(f"🎯 Versterkingen voor: {', '.join(weak_names)}"):
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
                df_targets_raw = run_query(target_query, (db_pos, selected_squad_id))
                
                if not df_targets_raw.empty:
                    # Ook hier pivot_table om duplicaten te middelen
                    df_target_pivot = df_targets_raw.pivot_table(
                        index=['Naam', 'Club'], 
                        columns='metric_name', 
                        values='score', 
                        aggfunc='mean'
                    )
                    df_target_pivot['Gaten Gedicht'] = df_target_pivot.notnull().sum(axis=1)
                    df_target_pivot = df_target_pivot.sort_values('Gaten Gedicht', ascending=False)
                    
                    st.dataframe(
                        df_target_pivot.style.background_gradient(cmap='RdYlGn', axis=None, vmin=40, vmax=80)
                        .format("{:.1f}", na_rep="-"),
                        use_container_width=True
                    )
        else:
            st.success("Deze positie is optimaal bezet (gemiddeld > 60).")
    else:
        st.caption(f"Geen data gevonden voor {display_label}.")
    
    st.divider()
