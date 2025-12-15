import streamlit as st
from utils import check_login

# -----------------------------------------------------------------------------
# 1. SETUP & SESSION STATE
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="KVK Platform", 
    page_icon="🔴", 
    layout="wide",
    initial_sidebar_state="expanded" # Forceer menu open
)

# Initialiseer sessie variabelen
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_info" not in st.session_state:
    st.session_state.user_info = None

# -----------------------------------------------------------------------------
# 2. LOGIN SCHERM (Alleen zichtbaar als niet ingelogd)
# -----------------------------------------------------------------------------
def login_screen():
    st.title("🔴⚪ KVK Data Platform - Login")
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form"):
            email = st.text_input("E-mailadres")
            password = st.text_input("Wachtwoord", type="password")
            submit = st.form_submit_button("Inloggen")
            
            if submit:
                user = check_login(email, password)
                if user:
                    st.success(f"Welkom terug, {user['naam']}!")
                    st.session_state.logged_in = True
                    st.session_state.user_info = user
                    st.rerun()
                else:
                    st.error("Ongeldige inloggegevens of account niet actief.")

# -----------------------------------------------------------------------------
# 3. UITLOGGEN & WELKOM
# -----------------------------------------------------------------------------
def logout():
    st.session_state.logged_in = False
    st.session_state.user_info = None
    st.rerun()

def welcome_page():
    st.title(f"Welkom, {st.session_state.user_info['naam']}")
    # Let op: we gebruiken hier 'rol', zoals het in je nieuwe tabel heet
    rol = st.session_state.user_info.get('rol', 'Onbekend')
    st.write(f"**Functie:** {rol}")
    
    st.info("👈 Selecteer een module in het menu links om te beginnen.")
    
    st.markdown("---")
    st.caption("© 2025 KV Kortrijk Scouting Dept.")

# -----------------------------------------------------------------------------
# 4. DE NAVIGATIE ROUTER
# -----------------------------------------------------------------------------
if not st.session_state.logged_in:
    login_screen()
else:
    # --- A. DEFINIEER PAGINA'S (Check of deze bestandsnamen EXACT kloppen in GitHub!) ---
    pg_welcome = st.Page(welcome_page, title="Home", icon="🏠")
    
    pg_spelers = st.Page("pages/1_⚽_Spelers_en_Teams.py", title="Spelers & Teams", icon="⚽")
    pg_coaches = st.Page("pages/2_👔_Coaches.py", title="Coaches", icon="👔")
    pg_wedstrijden = st.Page("pages/3_📊_Wedstrijden.py", title="Wedstrijden", icon="📊")
    pg_scouting = st.Page("pages/4_📝_Scouting.py", title="Scouting", icon="📝")
    pg_discover = st.Page("pages/5_🔎_Discover.py", title="Discover", icon="🔎")
    pg_aangeboden = st.Page("pages/6_📥_Aangeboden.py", title="Aangeboden", icon="📥")

    # --- B. BEPAAL RECHTEN ---
    raw_level = st.session_state.user_info.get('toegangsniveau', 0)
    
    # Veiligheidsconversie: Zorg dat het zeker een getal is (int)
    try:
        user_level = int(raw_level)
    except:
        user_level = 0

    # --- C. BOUW HET MENU (SECTIES) ---
    pages_dict = {}

    # 1. Altijd zichtbaar
    pages_dict["Algemeen"] = [pg_welcome]

    # 2. Modules verzamelen
    modules = []

    # Niveau 1: Basis (Scouting, Aangeboden, Discover)
    if user_level >= 1:
        modules.extend([pg_scouting, pg_aangeboden, pg_discover])
    
    # Niveau 2: Analist (+ Wedstrijden, Coaches)
    if user_level >= 2:
        modules.extend([pg_wedstrijden, pg_coaches])

    # Niveau 3: Directie (+ Spelers Data)
    if user_level >= 3:
        modules.extend([pg_spelers])

    # Voeg toe aan menu als er modules zijn
    if modules:
        pages_dict["Scouting Platform"] = modules

    # --- D. START NAVIGATIE ---
    pg = st.navigation(pages_dict)
    pg.run()
    
# --- E. SIDEBAR FOOTER (DEBUG VERSIE) ---
    with st.sidebar:
        st.divider()
        st.write(f"👤 **{st.session_state.user_info['naam']}**")
        
        # --- DEBUG INFO START ---
        raw = st.session_state.user_info.get('toegangsniveau', 'Niet gevonden')
        st.code(f"DB Niveau: {raw}\nType: {type(raw)}")
        st.code(f"Modules: {len(modules)}")
        if st.button("🗑️ Cache Legen"):
            st.cache_data.clear()
            st.rerun()
        # --- DEBUG INFO EINDE ---

        if st.button("Uitloggen", key="logout_btn"):
            logout()
