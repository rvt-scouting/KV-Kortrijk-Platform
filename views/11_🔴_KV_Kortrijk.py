import streamlit as st
import pandas as pd
import plotly.graph_objects as go
# We importeren de benodigde functies en configuraties uit jouw utils.py
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

    rel_ids = metrics_config.get('aan_bal', []) + metrics_config.get('zonder_bal', [])
    ids_str = ",".join([f"'{x}'" for x in rel_ids])

    # 1. Haal eigen spelers op
    query_eigen = f"""
        SELECT p.commonname as "Speler", pfs.metric_id, pfs.final_score_1_to_100 as score, def.name as metric_name
        FROM analysis.player_final_scores pfs
        JOIN analysis.players p ON pfs."playerId"::text = p.id
        JOIN analysis.playerscores_definitions def ON pfs.metric_id::text = def.id
        WHERE pfs."squadId"::text = %s AND pfs."iterationId"::text = %s 
        AND pfs.position = %s AND pfs.metric_id IN ({ids_str})
    """
    df_eigen = run_query(query_eigen, (selected_squad_id, iteration_id, db_pos))

    if not df_eigen.empty:
        st.header(display_label)
        df_pivot_eigen = df_eigen.pivot_table(index='Speler', columns='metric_name', values='score', aggfunc='mean')
        averages = df_pivot_eigen.mean().to_frame().T
        
        # 2. Haal potentiële targets op (voor de selectbox in de spider en de tabel)
        weak_metrics = averages.iloc[0][averages.iloc[0] < 60]
        df_target_pivot = pd.DataFrame()
        
        if not weak_metrics.empty:
            weak_ids_str = ",".join([f"'{x}'" for x in df_eigen[df_eigen['metric_name'].isin(weak_metrics.index)]['metric_id'].unique()])
            target_query = f"""
                SELECT p.commonname as "Naam", s.name as "Club", def.name as metric_name, pfs.final_score_1_to_100 as score,
                EXTRACT(YEAR FROM AGE(p.birthdate)) as "Leeftijd"
                FROM analysis.player_final_scores pfs
                JOIN analysis.players p ON pfs."playerId"::text = p.id
                JOIN analysis.squads s ON pfs."squadId"::text = s.id
                JOIN public.iterations i ON pfs."iterationId"::text = i.id
                JOIN analysis.playerscores_definitions def ON pfs.metric_id::text = def.id
                WHERE (i.season = '25/26' OR i.season = '2025' OR i.season = '24/25')
                AND pfs.position = %s AND pfs.metric_id IN ({ids_str}) 
                AND pfs."squadId"::text != %s
                AND EXTRACT(YEAR FROM AGE(p.birthdate)) <= 25
            """
            df_targets_raw = run_query(target_query, (db_pos, selected_squad_id))
            if not df_targets_raw.empty:
                df_target_pivot = df_targets_raw.pivot_table(index=['Naam', 'Leeftijd', 'Club'], columns='metric_name', values='score', aggfunc='mean')
                df_target_pivot['Gaten Gedicht'] = df_target_pivot[weak_metrics.index].gt(60).sum(axis=1)
                df_target_pivot = df_target_pivot.sort_values('Gaten Gedicht', ascending=False).head(15)

        # TABS INITIALISEREN
        tab1, tab2 = st.tabs(["📋 Data Matrix", "🕸️ Spider Charts"])

        # --- TAB 1: DATA MATRIX ---
        with tab1:
            st.write("### 👤 Eigen Selectie Scores")
            st.dataframe(df_pivot_eigen.style.background_gradient(cmap='RdYlGn', axis=0, vmin=40, vmax=80).format("{:.1f}"), use_container_width=True)
            
            st.write("### 📊 Positie Gemiddelde")
            averages.index = ["GROEP GEMIDDELDE"]
            st.dataframe(averages.style.background_gradient(cmap='RdYlGn', axis=1, vmin=40, vmax=80).format("{:.1f}"), use_container_width=True)

            if not df_target_pivot.empty:
                with st.expander("🎯 Aanbevolen Versterkingen (Top 15, <25j)"):
                    st.dataframe(df_target_pivot.style.background_gradient(cmap='RdYlGn', axis=None, vmin=40, vmax=80).format("{:.1f}", na_rep="-"), use_container_width=True)

        # --- TAB 2: SPIDER CHARTS ---
        with tab2:
            st.write("### 🕸️ Profiel Vergelijking")
            col_a, col_b = st.columns(2)
            with col_a:
                eigen_speler = st.selectbox(f"Vergelijk eigen speler:", ["Geen"] + list(df_pivot_eigen.index), key=f"own_{db_pos}")
            with col_b:
                target_namen = [idx[0] for idx in df_target_pivot.index] if not df_target_pivot.empty else []
                target_speler = st.selectbox(f"Leg target over profiel:", ["Geen"] + target_namen, key=f"trg_{db_pos}")
            
            categories = df_pivot_eigen.columns.tolist()
            fig = go.Figure()

            # 1. Gemiddelde
            fig.add_trace(go.Scatterpolar(r=averages.iloc[0].values, theta=categories, fill='toself', name='Groep Gemiddelde', line_color='gray', opacity=0.4))

            # 2. Eigen Speler
            if eigen_speler != "Geen":
                fig.add_trace(go.Scatterpolar(r=df_pivot_eigen.loc[eigen_speler].values, theta=categories, fill='toself', name=f"EIGEN: {eigen_speler}", line_color='red'))

            # 3. Target Speler
            if target_speler != "Geen":
                # Haal de rij op uit de multi-index df_target_pivot op basis van de naam
                target_data = df_target_pivot.xs(target_speler, level='Naam').iloc[0]
                # We vullen NaN waarden met 0 voor de spider chart visualisatie
                fig.add_trace(go.Scatterpolar(r=target_data[categories].fillna(0).values, theta=categories, fill='toself', name=f"TARGET: {target_speler}", line_color='cyan'))

            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), showlegend=True, height=500, margin=dict(l=80, r=80, t=20, b=20))
            st.plotly_chart(fig, use_container_width=True)
            
    st.divider()
