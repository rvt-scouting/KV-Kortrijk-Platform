import streamlit as st
import pandas as pd
from utils import run_query, init_connection

st.set_page_config(page_title="Admin Panel", page_icon="⚙️", layout="wide")

# -----------------------------------------------------------------------------
# 1. BEVEILIGING CHECK
# -----------------------------------------------------------------------------
if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB.")
    st.stop()

# Haal niveau en ID op
try:
    lvl = int(st.session_state.user_info.get('toegangsniveau', 0))
    current_user_id = st.session_state.user_info.get('id')
except:
    lvl = 0
    current_user_id = None

# Alleen niveau 3 (Admin) mag hier komen
if lvl < 3:
    st.error("⛔ Geen toegang. Dit gedeelte is alleen voor beheerders.")
    st.stop()

st.title("⚙️ Admin & Configuratie")

# -----------------------------------------------------------------------------
# 2. HULPFUNCTIE VOOR DATABASE OPSLAAN
# -----------------------------------------------------------------------------
def execute_command(query, params=None):
    """ Voert een SQL commando uit (INSERT/UPDATE) """
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        st.error(f"Database Fout: {e}")
        return False
    finally:
        if conn: conn.close()

# -----------------------------------------------------------------------------
# 3. TABS
# -----------------------------------------------------------------------------
tab1, tab2 = st.tabs(["👤 Gebruikers Beheer", "🎯 Shortlists Beheer"])

# =============================================================================
# TAB 1: GEBRUIKERS (TABEL: scouting.gebruikers)
# =============================================================================
with tab1:
    st.header("Nieuwe Gebruiker Toevoegen")
    
    with st.form("add_user_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            new_naam = st.text_input("Naam", placeholder="bv. Jean-Marie")
            new_email = st.text_input("Email", placeholder="bv. jm@kvk.be")
            new_pass = st.text_input("Wachtwoord", type="password")
        
        with c2:
            new_rol = st.selectbox("Rol", ["Scout", "Hoofd Scout", "Manager", "Coach", "Admin"])
            new_lvl = st.selectbox("Toegangsniveau", [1, 2, 3], 
                                   help="1=Scout (Input), 2=Coach/Manager (View), 3=Admin (Alles)")
            new_actief = st.checkbox("Account Actief?", value=True)
        
        submitted_user = st.form_submit_button("💾 Gebruiker Aanmaken")
        
        if submitted_user:
            if new_naam and new_email and new_pass:
                # 1. Check dubbele email
                check = run_query("SELECT id FROM scouting.gebruikers WHERE email = %s", params=(new_email,))
                
                if not check.empty:
                    st.error("Deze email bestaat al in de database!")
                else:
                    # 2. Insert
                    q_user = """
                        INSERT INTO scouting.gebruikers 
                        (email, wachtwoord, naam, rol, toegangsniveau, actief)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    if execute_command(q_user, params=(new_email, new_pass, new_naam, new_rol, new_lvl, new_actief)):
                        st.success(f"Gebruiker **{new_naam}** succesvol aangemaakt!")
                        st.cache_data.clear()
            else:
                st.warning("Vul minimaal Naam, Email en Wachtwoord in.")

    st.divider()
    st.subheader("Overzicht Gebruikers")
    
    df_users = run_query("""
        SELECT id, naam, email, rol, toegangsniveau, actief 
        FROM scouting.gebruikers 
        ORDER BY id
    """)
    
    if not df_users.empty:
        st.dataframe(
            df_users, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "actief": st.column_config.CheckboxColumn("Actief"),
            }
        )
    else:
        st.info("Nog geen gebruikers gevonden.")

# =============================================================================
# TAB 2: SHORTLISTS (TABEL: scouting.shortlists)
# =============================================================================
with tab2:
    st.header("Nieuwe Shortlist Aanmaken")
    st.info("Shortlists worden gebruikt om spelers te groeperen (bv. 'Zomer 2025', 'Keepers').")
    
    with st.form("add_shortlist_form", clear_on_submit=True):
        new_naam = st.text_input("Naam van Shortlist", placeholder="bv. Winter 2026")
        
        submitted_sl = st.form_submit_button("💾 Shortlist Toevoegen")
        
        if submitted_sl:
            if new_naam:
                # AANGEPAST: Gebruik kolom 'naam' en voeg 'eigenaar_id' toe
                q_sl = """
                    INSERT INTO scouting.shortlists (naam, eigenaar_id, aangemaakt_op) 
                    VALUES (%s, %s, NOW())
                """
                
                if execute_command(q_sl, params=(new_naam, current_user_id)):
                    st.success(f"Shortlist '{new_naam}' toegevoegd!")
                    st.cache_data.clear()
            else:
                st.warning("Vul een naam in.")

    st.divider()
    st.subheader("Actieve Shortlists")
    
    # AANGEPAST: Selecteer id en naam
    try:
        df_sl = run_query("SELECT id, naam FROM scouting.shortlists ORDER BY id")
        if not df_sl.empty:
            st.dataframe(
                df_sl, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "id": "ID",
                    "naam": "Naam Lijst"
                }
            )
        else:
            st.info("Geen shortlists gevonden.")
    except Exception as e:
        st.error(f"Fout bij laden shortlists: {e}")
