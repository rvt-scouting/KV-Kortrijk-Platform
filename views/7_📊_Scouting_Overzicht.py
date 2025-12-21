import streamlit as st
import pandas as pd
import plotly.express as px
from utils import run_query, commit_query  # Zorg dat commit_query in utils.py staat

st.set_page_config(page_title="Scouting Dashboard", page_icon="📊", layout="wide")

# -----------------------------------------------------------------------------
# 0. AUTHENTICATIE & LEVEL CHECK
# -----------------------------------------------------------------------------
if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB."); st.stop()

current_user_id = st.session_state.user_info.get('id')
try:
    lvl = int(st.session_state.user_info.get('toegangsniveau', 0))
except:
    lvl = 0

st.title("📊 Scouting Dashboard")

# -----------------------------------------------------------------------------
# 1. FILTERS (SIDEBAR)
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Filters Rapporten")

# Filter: Datum
date_range = st.sidebar.date_input("Datum Periode", [])

# Filter: Scouts (ALLEEN VOOR LEVEL 2+)
selected_scouts = []
if lvl > 1:
    try:
        df_scouts = run_query("SELECT id, naam FROM scouting.gebruikers WHERE rol != 'Admin' ORDER BY naam")
        if not df_scouts.empty:
            scout_opts = df_scouts['naam'].tolist()
            selected_scouts = st.sidebar.multiselect("Selecteer Scout(s)", scout_opts, default=scout_opts)
    except: pass
else:
    st.sidebar.info(f"👤 Je ziet alleen je eigen rapporten.")

# Filter: Advies Opties (ook nodig voor het bewerk-formulier)
advies_opts = ["Sign", "Future Sign", "Interesting", "Follow", "No", "A", "A+", "B", "C"]
try:
    df_advies_db = run_query("SELECT DISTINCT advies FROM scouting.rapporten WHERE advies IS NOT NULL ORDER BY advies")
    if not df_advies_db.empty:
        # Combineer hardcoded opties met wat in DB staat om niks te missen
        db_list = df_advies_db['advies'].tolist()
        advies_opts = list(set(advies_opts + db_list))
except:
    pass

selected_advies = st.sidebar.multiselect("Filter op Advies", advies_opts)

# Filter: Rating & Gouden Buzzer
min_rating = st.sidebar.slider("Minimale Beoordeling", 1, 10, 1)
show_only_gold = st.sidebar.checkbox("🏆 Toon enkel Gouden Buzzers")

# -----------------------------------------------------------------------------
# 2. TABS OPBOUWEN
# -----------------------------------------------------------------------------
tab_titles = ["📝 Alle Match Rapporten", "⭐ Shortlists"]
if lvl > 1:
    tab_titles.extend(["📥 Aangeboden Spelers (Markt)", "📈 Scout Statistieken"])

all_tabs = st.tabs(tab_titles)
tab_reports = all_tabs[0]
tab_shortlists = all_tabs[1]
tab_market = all_tabs[2] if len(all_tabs) > 2 else None
tab_stats = all_tabs[3] if len(all_tabs) > 3 else None

# =============================================================================
# TAB 1: ALLE MATCH RAPPORTEN
# =============================================================================
with tab_reports:
    col_head, col_btn = st.columns([6, 1])
    with col_head:
        st.header("Alle Scouting Rapporten")
    with col_btn:
        if st.button("🔄 Ververs Data", type="primary"):
            st.cache_data.clear()
            st.rerun()
    
    # Query om alle data op te halen (inclusief IDs voor bewerken)
    query = """
        SELECT 
            r.id,
            r.scout_id, 
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
        LEFT JOIN scouting.gebruikers s ON r.scout_id = s.id
        LEFT JOIN public.players p ON r.speler_id = p.id
        LEFT JOIN public.matches m ON r.wedstrijd_id = m.id
        LEFT JOIN public.squads sq_h ON m."homeSquadId" = sq_h.id
        LEFT JOIN public.squads sq_a ON m."awaySquadId" = sq_a.id
        ORDER BY r.aangemaakt_op DESC
    """
    
    try:
        df_reports = run_query(query)
        
        if not df_reports.empty:
            # --- PYTHON SIDE FILTERING ---
            if lvl == 1:
                df_reports = df_reports[df_reports['scout_id'] == current_user_id]
            elif selected_scouts:
                df_reports = df_reports[df_reports['Scout'].isin(selected_scouts)]

            if selected_advies:
                df_reports = df_reports[df_reports['Advies'].isin(selected_advies)]
            
            df_reports = df_reports[df_reports['Rating'] >= min_rating]
            if show_only_gold:
                df_reports = df_reports[df_reports['Gold'] == True]
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                df_reports['Datum'] = pd.to_datetime(df_reports['Datum'])
                df_reports = df_reports[(df_reports['Datum'].dt.date >= start_date) & (df_reports['Datum'].dt.date <= end_date)]

            # --- TABEL WEERGAVE ---
            st.info("💡 Klik op een rij om details te zien of het rapport aan te passen.")
            
            event = st.dataframe(
                df_reports,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",          
                selection_mode="single-row", 
                column_config={
                    "id": None, "scout_id": None,
                    "Datum": st.column_config.DatetimeColumn(format="DD-MM-YYYY"),
                    "Rating": st.column_config.NumberColumn(format="%d/10"),
                    "Gold": st.column_config.CheckboxColumn("🏆"),
                    "Rapport": st.column_config.TextColumn("Tekst", width="medium"), 
                }
            )
            
            # --- DETAIL & EDIT SECTIE ---
            if len(event.selection.rows) > 0:
                selected_idx = event.selection.rows[0]
                row = df_reports.iloc[selected_idx]
                
                # Check eigenaarschap
                is_owner = (int(row['scout_id']) == int(current_user_id))
                can_edit = is_owner or lvl >= 3

                st.divider()
                
                # Header met Toggle voor Edit-modus
                h_col1, h_col2 = st.columns([5, 1])
                with h_col1:
                    st.subheader(f"📄 Rapport: {row['Speler']}")
                
                edit_mode = False
                if can_edit:
                    with h_col2:
                        edit_mode = st.toggle("📝 Bewerken", help="Pas dit rapport aan")

                if edit_mode:
                    # FORMULIER OM DATA AAN TE PASSEN
                    with st.form("edit_form"):
                        st.warning("Let op: Je overschrijft de bestaande gegevens.")
                        c1, c2, c3 = st.columns(3)
                        new_pos = c1.text_input("Positie", value=row['Positie'])
                        new_rating = c2.slider("Rating", 1, 10, int(row['Rating']))
                        new_advies = c3.selectbox("Advies", advies_opts, index=advies_opts.index(row['Advies']) if row['Advies'] in advies_opts else 0)
                        
                        new_text = st.text_area("Rapport Tekst", value=row['Rapport'], height=200)
                        new_gold = st.checkbox("🏆 Gouden Buzzer", value=bool(row['Gold']))
                        
                        if st.form_submit_button("Wijzigingen Opslaan", type="primary"):
                            update_sql = """
                                UPDATE scouting.rapporten 
                                SET positie_gespeeld = %s, beoordeling = %s, advies = %s, rapport_tekst = %s, gouden_buzzer = %s
                                WHERE id = %s
                            """
                            if commit_query(update_sql, (new_pos, new_rating, new_advies, new_text, new_gold, int(row['id']))):
                                st.success("Rapport bijgewerkt!")
                                st.cache_data.clear()
                                st.rerun()
                else:
                    # NORMALE WEERGAVE (Lees-modus)
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.markdown(f"**Scout:** {row['Scout']}")
                        c2.markdown(f"**Wedstrijd:** {row['Wedstrijd']}")
                        c3.markdown(f"**Beoordeling:** {row['Rating']}/10 {'🏆' if row['Gold'] else ''}")
                        c4.markdown(f"**Advies:** {row['Advies']}")
                        st.divider()
                        st.markdown(row['Rapport'] if row['Rapport'] else "*Geen tekst.*")
                        st.caption(f"Gemaakt op: {row['Datum']}")

        else:
            st.info("Geen rapporten gevonden.")
    except Exception as e:
        st.error(f"Fout bij laden: {e}")

# =============================================================================
# TAB 2: SHORTLISTS (ORIGINELE LOGICA)
# =============================================================================
with tab_shortlists:
    st.header("🎯 Shortlists")
    try:
        base_query = "SELECT id, naam FROM scouting.shortlists"
        if lvl == 1:
            sl_opts = run_query(base_query + " WHERE eigenaar_id = %s", params=(current_user_id,))
        else:
            sl_opts = run_query(base_query)

        if not sl_opts.empty:
            sl_tabs = st.tabs(sl_opts['naam'].tolist())
            for i, sl_row in sl_opts.iterrows():
                with sl_tabs[i]:
                    q_sl = "SELECT * FROM scouting.rapporten WHERE shortlist_id = %s" # Vereenvoudigd voor voorbeeld
                    df_sl = run_query(q_sl, params=(sl_row['id'],))
                    st.dataframe(df_sl, use_container_width=True)
    except: pass

# =============================================================================
# TAB 3: AANGEBODEN SPELERS (ALLEEN LEVEL 2+)
# =============================================================================
if tab_market:
    with tab_market:
        st.header("📥 Aangeboden Spelers")
        status_filter = st.multiselect("Filter op Status", ["Interessant", "Te bekijken", "Onderhandeling", "In de gaten houden", "Afgekeurd"], default=["Interessant", "Te bekijken", "Onderhandeling"])
        if status_filter:
            q_market = f"""
                SELECT p.commonname as "Naam", sq.name as "Huidig Team", EXTRACT(YEAR FROM AGE(p.birthdate)) as "Leeftijd",
                o.status as "Status", o.vraagprijs as "Prijs (€)", o.makelaar as "Makelaar", o.opmerkingen as "Scoutingsverslag",
                o.video_link as "Video", o.tmlink as "TM"
                FROM scouting.offered_players o JOIN public.players p ON o.player_id = p.id
                LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
                WHERE o.status IN ({','.join([f"'{s}'" for s in status_filter])}) ORDER BY o.aangeboden_datum DESC
            """
            try:
                df_market = run_query(q_market)
                if not df_market.empty:
                    def color_status(val):
                        color = 'black'
                        if val == 'Interessant': color = '#27ae60' 
                        elif val == 'Afgekeurd': color = '#c0392b' 
                        elif val == 'Onderhandeling': color = '#f39c12' 
                        return f'color: {color}; font-weight: bold'
                    st.dataframe(
                        df_market.style.applymap(color_status, subset=['Status']), use_container_width=True, hide_index=True,
                        column_config={"Prijs (€)": st.column_config.NumberColumn(format="€ %.2f"), "Video": st.column_config.LinkColumn("📺"), "TM": st.column_config.LinkColumn("TM"), "Scoutingsverslag": st.column_config.TextColumn(width="large")}
                    )
                else: st.info("Geen spelers gevonden.")
            except Exception as e: st.error(f"Fout markt: {e}")
        else: st.warning("Selecteer status.")

# =============================================================================
# TAB 4: SCOUT STATISTIEKEN (ALLEEN LEVEL 2+)
# =============================================================================
if tab_stats:
    with tab_stats:
        st.header("📈 Activiteit Scouts")
        
        c1, c2 = st.columns(2)
        with c1:
            df_stats = run_query("SELECT s.naam as \"Scout\", COUNT(r.id) as \"Aantal Rapporten\" FROM scouting.rapporten r JOIN scouting.gebruikers s ON r.scout_id = s.id GROUP BY s.naam ORDER BY \"Aantal Rapporten\" DESC")
            if not df_stats.empty: st.plotly_chart(px.bar(df_stats, x="Scout", y="Aantal Rapporten", title="Rapporten per Scout", color="Aantal Rapporten", color_continuous_scale="Reds"), use_container_width=True)
        with c2:
            df_adv = run_query("SELECT advies, COUNT(id) as \"Aantal\" FROM scouting.rapporten GROUP BY advies")
            if not df_adv.empty: st.plotly_chart(px.pie(df_adv, values="Aantal", names="advies", title="Verdeling Adviezen", hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu), use_container_width=True)

        st.markdown("---"); st.subheader("Laatste 10 Activiteiten")
        df_log = run_query("SELECT r.aangemaakt_op, s.naam, COALESCE(p.commonname, r.custom_speler_naam) as speler, r.beoordeling FROM scouting.rapporten r JOIN scouting.gebruikers s ON r.scout_id = s.id LEFT JOIN public.players p ON r.speler_id = p.id ORDER BY r.aangemaakt_op DESC LIMIT 10")
        if not df_log.empty:
            for _, row in df_log.iterrows(): st.text(f"{row['aangemaakt_op'].strftime('%d-%m %H:%M')} - {row['naam']} scoutte {row['speler']} (Rating: {row['beoordeling']})")
