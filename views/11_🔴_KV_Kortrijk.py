import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from utils import run_query, show_sidebar_filters, POSITION_METRICS, get_config_for_position

# -----------------------------------------------------------------------------
# 1. SETUP & FILTERS
# -----------------------------------------------------------------------------
season, iteration_id = show_sidebar_filters()

selected_squad_id = None
sel_squad_name = None

if iteration_id:
    st.sidebar.divider()
    st.sidebar.subheader("2. Specifieke Club")
    squad_query = """
        SELECT DISTINCT s.id, s.name FROM analysis.squads s
        JOIN analysis.player_final_scores pfs ON s.id = pfs."squadId"::text
        WHERE pfs."iterationId"::text = %s ORDER BY s.name
    """
    df_squads = run_query(squad_query, (iteration_id,))
    if not df_squads.empty:
        squad_map = dict(zip(df_squads['name'], df_squads['id']))
        squad_names = list(squad_map.keys())
        default_idx = squad_names.index('KV Kortrijk') if 'KV Kortrijk' in squad_names else 0
        sel_squad_name = st.sidebar.selectbox("Kies Club:", squad_names, index=default_idx)
        selected_squad_id = squad_map[sel_squad_name]

if not iteration_id or not selected_squad_id:
    st.warning("Selecteer a.u.b. een seizoen, competitie en club in de zijbalk.")
    st.stop()

st.title(f"🔴 Squad Planner: {sel_squad_name}")

display_positions = [
    ("CENTRAL_DEFENDER", "🛡️ Centrale Verdedigers"),
    ("RIGHT_WINGBACK_DEFENDER", "🏃 Vleugelverdedigers (R)"),
    ("LEFT_WINGBACK_DEFENDER", "🏃 Vleugelverdedigers (L)"),
    ("DEFENSE_MIDFIELD", "⚓ Defensieve Middenvelders"),
    ("CENTRAL_MIDFIELD", "🧠 Centrale Middenvelders"),
    ("ATTACKING_MIDFIELD", "🪄 Aanvallende Middenvelders"),
    ("RIGHT_WINGER", "⚡ Buitenspelers (R)"),
    ("LEFT_WINGER", "⚡ Buitenspelers (L)"),
    ("CENTER_FORWARD", "🎯 Spitsen")
]

# -----------------------------------------------------------------------------
# 3. DE LOOP: ANALYSE PER POSITIE
# -----------------------------------------------------------------------------
for db_pos, display_label in display_positions:
    metrics_config = get_config_for_position(db_pos, POSITION_METRICS)
    if not metrics_config: continue

    st.header(display_label)
    rel_ids = metrics_config.get('aan_bal', []) + metrics_config.get('zonder_bal', [])
    ids_str = ",".join([f"'{x}'" for x in rel_ids])

    # Data ophalen
    query = f"""
        SELECT p.commonname as "Speler", pfs.metric_id, pfs.final_score_1_to_100 as score, def.name as metric_name,
        EXTRACT(YEAR FROM AGE(p.birthdate)) as "Leeftijd"
        FROM analysis.player_final_scores pfs
        JOIN analysis.players p ON pfs."playerId"::text = p.id
        JOIN analysis.playerscores_definitions def ON pfs.metric_id::text = def.id
        WHERE pfs."squadId"::text = %s AND pfs."iterationId"::text = %s 
        AND pfs.position = %s AND pfs.metric_id IN ({ids_str})
    """
    df_pos = run_query(query, (selected_squad_id, iteration_id, db_pos))

    if not df_pos.empty:
        # TABS INITIALISEREN
        tab1, tab2 = st.tabs(["📋 Data Matrix", "🕸️ Spider Charts"])

        # --- TAB 1: DATA MATRIX ---
        with tab1:
            df_pivot = df_pos.pivot_table(index='Speler', columns='metric_name', values='score', aggfunc='mean')
            st.write("### 👤 Individuele Scores")
            st.dataframe(df_pivot.style.background_gradient(cmap='RdYlGn', axis=0, vmin=40, vmax=80).format("{:.1f}"), use_container_width=True)
            
            averages = df_pivot.mean().to_frame().T
            averages.index = ["GROEP GEMIDDELDE"]
            st.write("### 📊 Positie Gemiddelde")
            st.dataframe(averages.style.background_gradient(cmap='RdYlGn', axis=1, vmin=40, vmax=80).format("{:.1f}"), use_container_width=True)

        # --- TAB 2: SPIDER CHARTS ---
        with tab2:
            st.write("### 🕸️ Profiel Vergelijking")
            
            # Selectie voor vergelijking
            col_a, col_b = st.columns(2)
            with col_a:
                eigen_speler = st.selectbox(f"Selecteer eigen speler ({display_label}):", ["Geen"] + list(df_pivot.index))
            
            # Radar Chart opbouw
            categories = df_pivot.columns.tolist()
            fig = go.Figure()

            # 1. Gemiddelde (Basis)
            fig.add_trace(go.Scatterpolar(
                r=averages.iloc[0].values,
                theta=categories,
                fill='toself',
                name='Groep Gemiddelde',
                line_color='gray',
                opacity=0.5
            ))

            # 2. Eigen Speler (Overlay)
            if eigen_speler != "Geen":
                fig.add_trace(go.Scatterpolar(
                    r=df_pivot.loc[eigen_speler].values,
                    theta=categories,
                    fill='toself',
                    name=eigen_speler,
                    line_color='red'
                ))

            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=True,
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)

        # --- TARGET FINDER (Zelfde als voorheen) ---
        weak_metrics = averages.iloc[0][averages.iloc[0] < 60]
        if not weak_metrics.empty:
            weak_ids_str = ",".join([f"'{x}'" for x in df_pos[df_pos['metric_name'].isin(weak_metrics.index)]['metric_id'].unique()])
            with st.expander(f"🎯 Versterkingen voor: {', '.join(weak_metrics.index.tolist())}"):
                target_query = f"""
                    SELECT p.commonname as "Naam", s.name as "Club", def.name as metric_name, pfs.final_score_1_to_100 as score,
                    EXTRACT(YEAR FROM AGE(p.birthdate)) as "Leeftijd"
                    FROM analysis.player_final_scores pfs
                    JOIN analysis.players p ON pfs."playerId"::text = p.id
                    JOIN analysis.squads s ON pfs."squadId"::text = s.id
                    JOIN public.iterations i ON pfs."iterationId"::text = i.id
                    JOIN analysis.playerscores_definitions def ON pfs.metric_id::text = def.id
                    WHERE (i.season = '25/26' OR i.season = '2025' OR i.season = '24/25')
                    AND pfs.position = %s AND pfs.metric_id IN ({weak_ids_str}) 
                    AND pfs.final_score_1_to_100 > 60 AND pfs."squadId"::text != %s
                    AND EXTRACT(YEAR FROM AGE(p.birthdate)) <= 25
                """
                df_targets = run_query(target_query, (db_pos, selected_squad_id))
                if not df_targets.empty:
                    df_target_pivot = df_targets.pivot_table(index=['Naam', 'Leeftijd', 'Club'], columns='metric_name', values='score', aggfunc='mean')
                    df_target_pivot['Gaten Gedicht'] = df_target_pivot.notnull().sum(axis=1)
                    st.dataframe(df_target_pivot.sort_values('Gaten Gedicht', ascending=False).head(15).style.background_gradient(cmap='RdYlGn', axis=None, vmin=40, vmax=80).format("{:.1f}", na_rep="-"), use_container_width=True)
        st.divider()
