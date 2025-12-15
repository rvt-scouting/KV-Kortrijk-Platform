import streamlit as st
import pandas as pd
import plotly.express as px
from utils import run_query

st.set_page_config(page_title="Scouting Dashboard", page_icon="📊", layout="wide")

st.title("📊 Scouting Dashboard")

# -----------------------------------------------------------------------------
# 1. FILTERS (SIDEBAR)
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Filters Rapporten")

# Filter: Datum
date_range = st.sidebar.date_input("Datum Periode", [])

# Filter: Scouts
try:
    df_scouts = run_query("SELECT id, naam FROM scouting.scouts ORDER BY naam")
    scout_opts = df_scouts['naam'].tolist()
    selected_scouts = st.sidebar.multiselect("Selecteer Scout(s)", scout_opts, default=scout_opts)
except:
    selected_scouts = []

# Filter: Rating & Gouden Buzzer
min_rating = st.sidebar.slider("Minimale Beoordeling", 1, 10, 1)
show_only_gold = st.sidebar.checkbox("🏆 Toon enkel Gouden Buzzers")

# -----------------------------------------------------------------------------
# 2. TABS
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📝 Alle Match Rapporten", 
    "⭐ Shortlists", 
    "📥 Aangeboden Spelers (Markt)",
    "📈 Scout Statistieken"
])

# =============================================================================
# TAB 1: ALLE MATCH RAPPORTEN
# =============================================================================
with tab1:
    st.header("Alle Scouting Rapporten")
    
    # Query: We moeten slim omgaan met de Database-IDs vs Manuele Namen (COALESCE)
    query = """
        SELECT 
            r.id,
            r.aangemaakt_op as "Datum",
            s.naam as "Scout",
            COALESCE(p.commonname, r.custom_speler_naam, 'Onbekend') as "Speler",
            COALESCE(CONCAT(sq_h.name, ' vs ', sq_a.name), r.custom_wedstrijd_naam, 'Onbekend') as "Wedstrijd",
            r.positie_gespeeld as "Positie",
            r.beoordeling as "Rating",
            r.advies as "Advies",
            r.gouden_buzzer as "Gold",
            r.rapport_tekst as "Rapport"
        FROM scouting.rapporten r
        LEFT JOIN scouting.scouts s ON r.scout_id = s.id
        LEFT JOIN public.players p ON r.speler_id = p.id
        LEFT JOIN public.matches m ON r.wedstrijd_id = m.id
        LEFT JOIN public.squads sq_h ON m."homeSquadId" = sq_h.id
        LEFT JOIN public.squads sq_a ON m."awaySquadId" = sq_a.id
        ORDER BY r.aangemaakt_op DESC
    """
    
    try:
        df_reports = run_query(query)
        
        if not df_reports.empty:
            # --- FILTERS TOEPASSEN ---
            # 1. Scout Filter
            if selected_scouts:
                df_reports = df_reports[df_reports['Scout'].isin(selected_scouts)]
            
            # 2. Rating Filter
            df_reports = df_reports[df_reports['Rating'] >= min_rating]
            
            # 3. Gold Filter
            if show_only_gold:
                df_reports = df_reports[df_reports['Gold'] == True]

            # 4. Datum Filter (Als er data gekozen zijn)
            if len(date_range) == 2:
                start_date, end_date = date_range
                df_reports['Datum'] = pd.to_datetime(df_reports['Datum'])
                df_reports = df_reports[
                    (df_reports['Datum'].dt.date >= start_date) & 
                    (df_reports['Datum'].dt.date <= end_date)
                ]

            # --- WEERGAVE ---
            st.markdown(f"**{len(df_reports)}** rapporten gevonden.")
            
            # Mooiere tabel met st.dataframe config
            st.dataframe(
                df_reports,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": None, # Verberg ID
                    "Datum": st.column_config.DatetimeColumn(format="DD-MM-YYYY HH:mm"),
                    "Rating": st.column_config.NumberColumn(format="%d/10"),
                    "Gold": st.column_config.CheckboxColumn("🏆"),
                    "Rapport": st.column_config.TextColumn("Tekst", width="large"),
                }
            )
        else:
            st.info("Nog geen rapporten in de database.")
            
    except Exception as e:
        st.error(f"Fout bij laden rapporten: {e}")

# =============================================================================
# TAB 2: SHORTLISTS
# =============================================================================
with tab2:
    st.header("🎯 Shortlists")
    
    # Haal eerst de shortlist namen op
    try:
        sl_opts = run_query("SELECT * FROM scouting.shortlists")
        if not sl_opts.empty:
            # Maak tabs voor elke shortlist
            sl_tabs = st.tabs(sl_opts['label'].tolist())
            
            for i, row in sl_opts.iterrows():
                sl_id = row['value'] # of 'id' afhankelijk van je tabelstructuur
                sl_name = row['label']
                
                with sl_tabs[i]:
                    # Haal spelers op die op deze shortlist staan
                    # We pakken het meest recente rapport per speler voor deze shortlist
                    q_sl = """
                        SELECT DISTINCT ON (r.speler_id, r.custom_speler_naam)
                            COALESCE(p.commonname, r.custom_speler_naam) as "Speler",
                            r.positie_gespeeld as "Positie",
                            r.beoordeling as "Rating",
                            r.advies as "Advies",
                            r.rapport_tekst as "Laatste Info",
                            s.naam as "Scout",
                            r.aangemaakt_op as "Datum"
                        FROM scouting.rapporten r
                        LEFT JOIN public.players p ON r.speler_id = p.id
                        LEFT JOIN scouting.scouts s ON r.scout_id = s.id
                        WHERE r.shortlist_id = %s
                        ORDER BY r.speler_id, r.custom_speler_naam, r.aangemaakt_op DESC
                    """
                    df_sl = run_query(q_sl, params=(sl_id,))
                    
                    if not df_sl.empty:
                        st.dataframe(
                            df_sl, 
                            use_container_width=True, 
                            hide_index=True,
                            column_config={
                                "Datum": st.column_config.DateColumn(format="DD-MM-YYYY"),
                                "Rating": st.column_config.NumberColumn(format="%d")
                            }
                        )
                    else:
                        st.info(f"Nog geen spelers op shortlist '{sl_name}'.")
        else:
            st.warning("Geen shortlists gedefinieerd in tabel scouting.shortlists")
            
    except Exception as e:
        st.error(f"Fout shortlists: {e}")

# =============================================================================
# TAB 3: AANGEBODEN SPELERS (MARKT)
# =============================================================================
with tab3:
    st.header("📥 Aangeboden Spelers")
    
    # Filter op status
    status_filter = st.multiselect(
        "Filter op Status", 
        ["Interessant", "Te bekijken", "Onderhandeling", "In de gaten houden", "Afgekeurd"],
        default=["Interessant", "Te bekijken", "Onderhandeling"]
    )
    
    if not status_filter:
        st.warning("Selecteer minstens één status.")
        st.stop()
        
    q_market = f"""
        SELECT 
            p.commonname as "Naam",
            sq.name as "Huidig Team",
            EXTRACT(YEAR FROM AGE(p.birthdate)) as "Leeftijd",
            o.status as "Status",
            o.vraagprijs as "Prijs (€)",
            o.makelaar as "Makelaar",
            o.opmerkingen as "Scoutingsverslag",
            o.video_link as "Video",
            o.tmlink as "TM"
        FROM scouting.offered_players o
        JOIN public.players p ON o.player_id = p.id
        LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
        WHERE o.status IN ({','.join([f"'{s}'" for s in status_filter])})
        ORDER BY o.aangeboden_datum DESC
    """
    
    try:
        df_market = run_query(q_market)
        if not df_market.empty:
            # Kleurmarkering voor status
            def color_status(val):
                color = 'black'
                if val == 'Interessant': color = '#27ae60' # Green
                elif val == 'Afgekeurd': color = '#c0392b' # Red
                elif val == 'Onderhandeling': color = '#f39c12' # Orange
                return f'color: {color}; font-weight: bold'

            st.dataframe(
                df_market.style.applymap(color_status, subset=['Status']),
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "Prijs (€)": st.column_config.NumberColumn(format="€ %.2f"),
                    "Video": st.column_config.LinkColumn("📺"),
                    "TM": st.column_config.LinkColumn("TM"),
                    "Scoutingsverslag": st.column_config.TextColumn(width="large")
                }
            )
        else:
            st.info("Geen spelers gevonden met deze status.")
    except Exception as e:
        st.error(f"Fout markt: {e}")

# =============================================================================
# TAB 4: SCOUT STATISTIEKEN
# =============================================================================
with tab4:
    st.header("📈 Activiteit Scouts")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # 1. Aantal rapporten per scout
        q_stats = """
            SELECT s.naam as "Scout", COUNT(r.id) as "Aantal Rapporten"
            FROM scouting.rapporten r
            JOIN scouting.scouts s ON r.scout_id = s.id
            GROUP BY s.naam
            ORDER BY "Aantal Rapporten" DESC
        """
        df_stats = run_query(q_stats)
        if not df_stats.empty:
            fig = px.bar(df_stats, x="Scout", y="Aantal Rapporten", title="Rapporten per Scout", color="Aantal Rapporten", color_continuous_scale="Reds")
            st.plotly_chart(fig, use_container_width=True)
            
    with col2:
        # 2. Verdeling per Advies
        q_adv = """
            SELECT advies, COUNT(id) as "Aantal"
            FROM scouting.rapporten
            GROUP BY advies
        """
        df_adv = run_query(q_adv)
        if not df_adv.empty:
            fig2 = px.pie(df_adv, values="Aantal", names="advies", title="Verdeling Adviezen", hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("---")
    st.subheader("Laatste 10 Activiteiten")
    # Tijdlijn
    q_log = """
        SELECT r.aangemaakt_op, s.naam, 
               COALESCE(p.commonname, r.custom_speler_naam) as speler, 
               r.beoordeling
        FROM scouting.rapporten r
        JOIN scouting.scouts s ON r.scout_id = s.id
        LEFT JOIN public.players p ON r.speler_id = p.id
        ORDER BY r.aangemaakt_op DESC LIMIT 10
    """
    df_log = run_query(q_log)
    if not df_log.empty:
        for _, row in df_log.iterrows():
            st.text(f"{row['aangemaakt_op'].strftime('%d-%m %H:%M')} - {row['naam']} scoutte {row['speler']} (Rating: {row['beoordeling']})")
