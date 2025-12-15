import streamlit as st
from utils import check_login

# -----------------------------------------------------------------------------
# 1. SETUP & SESSION STATE
# -----------------------------------------------------------------------------
st.set_page_config(page_title="KVK Platform", page_icon="🔴", layout="wide")

# Initialiseer sessie variabelen als ze er nog niet zijn
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_info" not in st.session_state:
    st.session_state.user_info = None

# -----------------------------------------------------------------------------
# 2. LOGIN SCHERM LOGICA (Wordt getoond als je niet ingelogd bent)
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
                    # Sla gegevens op in sessie
                    st.session_state.logged_in = True
                    st.session_state.user_info = user
                    st.rerun() # Herlaad de pagina om de navigatie te tonen
                else:
                    st.error("Ongeldige inloggegevens of account niet actief.")

# -----------------------------------------------------------------------------
# 3. UITLOGGEN
# -----------------------------------------------------------------------------
def logout():
    st.session_state.logged_in = False
    st.session_state.user_info = None
    st.rerun()

# -----------------------------------------------------------------------------
# 4. DE NAVIGATIE ROUTER
# -----------------------------------------------------------------------------
if not st.session_state.logged_in:
    login_screen()
else:
    # --- A. DEFINIEER ALLE PAGINA'S ---
    # We verwijzen hier naar de bestanden in je mapjes
    
    # Iedereen ziet deze (Welcome pagina - maak evt een intro.py of gebruik een functie)
    # Voor nu gebruiken we even een simpele functie als startpagina
    def welcome_page():
        st.title(f"Welkom, {st.session_state.user_info['naam']}")
        st.write(f"Rol: {st.session_state.user_info['rol']}")
        st.info("Selecteer een module in het menu links.")
        if st.button("Uitloggen"):
            logout()

    pg_welcome = st.Page(welcome_page, title="Home", icon="🏠")
    
    # De Modules (Verwijzend naar je bestanden in pages/)
    pg_spelers = st.Page("pages/1_⚽_Spelers_en_Teams.py", title="Spelers & Teams", icon="⚽")
    pg_coaches = st.Page("pages/2_👔_Coaches.py", title="Coaches", icon="👔")
    pg_wedstrijden = st.Page("pages/3_📊_Wedstrijden.py", title="Wedstrijden", icon="📊")
    pg_scouting = st.Page("pages/4_📝_Scouting.py", title="Scouting", icon="📝")
    pg_discover = st.Page("pages/5_🔎_Discover.py", title="Discover", icon="🔎")
    pg_aangeboden = st.Page("pages/6_📥_Aangeboden.py", title="Aangeboden", icon="📥")

# --- B. BEPAAL WIE WAT MAG ZIEN (MET SECTIES) ---
    user_level = st.session_state.user_info.get('toegangsniveau', 0)
    
    # Debugging: Zet dit tijdelijk aan als je twijfelt over je niveau
    # st.sidebar.write(f"Debug Niveau: {user_level}")

    # We bouwen een Dictionary (Woordenboek) voor secties in het menu
    pages_dict = {}

    # 1. De Algemene sectie (heeft iedereen)
    pages_dict["Algemeen"] = [pg_welcome]

    # 2. Modules verzamelen op basis van niveau
    modules = []
    
    # NIVEAU 1: BASIS (Scouts)
    if user_level >= 1:
        modules.extend([pg_scouting, pg_aangeboden, pg_discover])
    
    # NIVEAU 2: ANALIST
    if user_level >= 2:
        modules.extend([pg_wedstrijden, pg_coaches])

    # NIVEAU 3: DIRECTIE
    if user_level >= 3:
        modules.extend([pg_spelers])

    # Als er modules zijn, voegen we die toe als sectie 'Scouting Platform'
    if modules:
        pages_dict["Scouting Platform"] = modules

    # --- C. START DE NAVIGATIE ---
    # Streamlit snapt nu dat het groepen zijn en zal ze netjes tonen
    pg = st.navigation(pages_dict)
    pg.run()
    
    # Sidebar footer
    with st.sidebar:
        st.divider()
        st.write(f"👤 **{st.session_state.user_info['naam']}**")
        if st.button("Uitloggen", key="logout_btn"):
            logout()
