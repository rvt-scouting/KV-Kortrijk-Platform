import streamlit as st
import pandas as pd
import plotly.express as px
from utils import run_query, show_sidebar_filters, POSITION_METRICS, get_config_for_position

# -----------------------------------------------------------------------------
# 1. SETUP & DATA LADEN
# -----------------------------------------------------------------------------
st.title("🔴 KV Kortrijk Club Analyse")

# Gebruik de sidebar filters uit utils.py
season, iteration_id = show_sidebar_filters()

# We fixeren KV Kortrijk (ID 265 is een voorbeeld, pas aan naar de juiste ID uit je DB)
# Tip: Je kunt dit opzoeken via: SELECT id FROM public.squads WHERE name ILIKE '%Kortrijk%'
KVK_SQUAD_ID = '265' 

if iteration_id:
    # -----------------------------------------------------------------------------
    # 2. SPEELSTIJLEN (SQUAD PROFILE SCORES)
    # -----------------------------------------------------------------------------
    st.header("🛡️ Speelstijl Profiel")
    
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
                         title="Speelstijl Scores", color='score', color_continuous_scale='Reds')
            st.plotly_chart(fig, use_container_width=True)

    # -----------------------------------------------------------------------------
    # 3. POSITIE ANALYSE & ZWAKKE PUNTEN
    # -----------------------------------------------------------------------------
    st.divider()
    st.header("⚽ Positie Analyse & Verbeterpunten")

    # Selecteer positie om te analyseren
    posities_vertaling = {
        "CENTRAL_DEFENDER": "Centrale Verdediger",
        "RIGHT_WINGBACK_DEFENDER": "Vleugelverdediger (R)",
        "DEFENSIVE_MIDFIELD": "Defensieve Middenvelder",
        "CENTRAL_MIDFIELD": "Centrale Middenvelder",
        "ATTACKING_MIDFIELD": "Aanvallende Middenvelder",
        "RIGHT_WINGER": "Buitenspeler (R)",
        "CENTER_FORWARD": "Spits"
    }
    
    sel_pos = st.selectbox("Selecteer positie voor diepte-analyse:", list(posities_vertaling.keys()), format_func=lambda x: posities_vertaling[x])
    
    # Haal de metrics op voor deze positie uit utils.py
    metrics_config = get_config_for_position(sel_pos, POSITION_METRICS)
    
    if metrics_config:
        # We combineren aan_bal en zonder_bal metrics
        all_metric_ids = metrics_config.get('aan_bal', []) + metrics_config.get('zonder_bal', [])
        
        # Query om de scores van KVK spelers op deze positie op te halen
        # We gebruiken de analysis.player_final_scores tabel voor gemak
        player_scores_query = f"""
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
              AND pfs.metric_id IN ({','.join(map(str, all_metric_ids))})
        """
        df_kvk_players = run_query(player_scores_query, (KVK_SQUAD_ID, iteration_id, sel_pos))
        
        if not df_kvk_players.empty:
            # Pivot de tabel voor een mooi overzicht per speler
            df_pivot = df_kvk_players.pivot(index='Speler', columns='metric_name', values='score')
            
            st.subheader(f"Huidige Bezetting: {posities_vertaling[sel_pos]}")
            st.dataframe(df_pivot.style.background_gradient(cmap='RdYlGn', axis=None, low=0.4, high=0.9))
            
            # Bereken gemiddeldes per kolom
            averages = df_pivot.mean().round(1)
            
            # Identificeer werkpunten (score < 60)
            weak_metrics = averages[averages < 60]
            weak_metric_names = weak_metrics.index.tolist()
            
            # Haal ook de IDs op van deze zwakke metrics voor de volgende query
            weak_metric_ids = df_kvk_players[df_kvk_players['metric_name'].isin(weak_metric_names)]['metric_id'].unique().tolist()

            st.warning(f"⚠️ **Zwakke punten op deze positie:** {', '.join(weak_metric_names) if weak_metric_names else 'Geen'}")
            
            # -----------------------------------------------------------------------------
            # 4. TARGET FINDER (DE SCOUTING LOGICA)
            # -----------------------------------------------------------------------------
            if weak_metric_ids:
                st.divider()
                st.header(f"🎯 Potentiële Targets (Seizoen 25/26 & 2025)")
                st.info(f"Gezocht naar spelers die excelleren (>60) in: {', '.join(weak_metric_names)}")
                
                # Query om spelers te vinden die hoog scoren op onze zwakke punten
                target_query = f"""
                    SELECT 
                        p.commonname as "Naam",
                        s.name as "Huidige Club",
                        pfs.metric_id,
                        pfs.final_score_1_to_100 as score
                    FROM analysis.player_final_scores pfs
                    JOIN analysis.players p ON pfs."playerId" = p.id
                    JOIN analysis.squads s ON pfs."squadId" = s.id
                    JOIN public.iterations i ON pfs."iterationId" = i.id
                    WHERE i.season IN ('25/26', '2025')
                      AND pfs.position = %s
                      AND pfs.metric_id IN ({','.join(map(str, weak_metric_ids))})
                      AND pfs.final_score_1_to_100 > 60
                      AND pfs."squadId" != %s  -- Niet onze eigen spelers
                """
                df_targets_raw = run_query(target_query, (sel_pos, KVK_SQUAD_ID))
                
                if not df_targets_raw.empty:
                    # Tel op hoeveel van de zwakke punten de speler 'overbrugt'
                    df_targets_summary = df_targets_raw.groupby(['Naam', 'Huidige Club']).agg(
                        Matches=('metric_id', 'count'),
                        Gem_Score=('score', 'mean')
                    ).reset_index()
                    
                    # Sorteren op meeste matches (3 op 3 is de ideale speler)
                    df_targets_summary = df_targets_summary.sort_values(by=['Matches', 'Gem_Score'], ascending=False)
                    
                    # Display resultaat
                    st.write(f"Gevonden kandidaten: {len(df_targets_summary)}")
                    st.table(df_targets_summary.head(10))
                else:
                    st.write("Geen spelers gevonden die op al deze punten beter scoren. Probeer de criteria te verruimen.")
            else:
                st.success("Deze positie scoort op alle datapunten gemiddeld boven de 60! Geen directe versterking nodig op basis van data.")
        else:
            st.info("Geen spelersdata gevonden voor deze positie bij KVK in dit seizoen.")
    else:
        st.error("Configuratie voor deze positie niet gevonden in utils.py")

else:
    st.warning("Selecteer eerst een seizoen en competitie in de sidebar.")
