import streamlit as st
from utils import check_login

# -----------------------------------------------------------------------------
# 1. SETUP
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="KVK Platform", 
    page_icon="🔴", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# -----------------------------------------------------------------------------
# 2. LOGIN LOGICA
# -----------------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_info" not in st.session_state:
    st.session_state.user_info = None

def login_screen():
    st.title("🔴⚪ KVK Login")
    with st.form("login"):
        email = st.text_input("Email")
        pwd = st.text_input("Wachtwoord", type="password")
        if st.form_submit_button("Inloggen"):
            user = check_login(email, pwd)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_info = user
                st.rerun()
            else:
                st.error("Fout")

def logout():
    st.session_state.logged_in = False
    st.session_state.user_info = None
    st.rerun()

# -----------------------------------------------------------------------------
# 3. PAGINA DEFINITIES
# -----------------------------------------------------------------------------
def welcome():
    st.title(f"Welkom {st.session_state.user_info.get('naam')}")
    st.write("Gebruik het menu links.")

def test_page_func():
    st.title("🛠️ Test Pagina")
    st.write("Als je dit ziet, werkt het menu!")
    st.write(f"Jouw ruwe data: {st.session_state.user_info}")

# Paginabeheer
pg_home = st.Page(welcome, title="Home", icon="🏠")
pg_test = st.Page(test_page_func, title="Systeem Test", icon="🛠️")

# Zorg dat deze bestanden echt bestaan in 'views/'!
pg_scout = st.Page("views/scouting.py", title="Scouting", icon="📝") 
pg_disc = st.Page("views/5_🔎_Discover.py", title="Discover", icon="🔎")
pg_offer = st.Page("views/6_📥_Aangeboden.py", title="Aangeboden", icon="📥")
pg_match = st.Page("views/3_📊_Wedstrijden.py", title="Wedstrijden", icon="📊")
pg_coach = st.Page("views/2_👔_Coaches.py", title="Coaches", icon="👔")
pg_player = st.Page("views/1_⚽_Spelers_en_Teams.py", title="Spelers", icon="⚽")

# -----------------------------------------------------------------------------
# 4. NAVIGATIE BOUWER
# -----------------------------------------------------------------------------
if not st.session_state.logged_in:
    login_screen()
else:
    # Haal niveau op (veilig)
    try:
        lvl = int(st.session_state.user_info.get('toegangsniveau', 0))
    except:
        lvl = 0

    # Bouw de dictionary
    pages = {}
    
    # GROEP 1: ALGEMEEN (Altijd minimaal 2 pagina's om menu te forceren!)
    pages["Algemeen"] = [pg_home, pg_test]

    # GROEP 2: MODULES
    modules = []
    if lvl >= 1: modules.extend([pg_scout, pg_offer, pg_disc])
    if lvl >= 2: modules.extend([pg_match, pg_coach])
    if lvl >= 3: modules.extend([pg_player])

    if modules:
        pages["Scouting App"] = modules

    # START DE NAVIGATIE
    with st.sidebar:
        st.title("KV Kortrijk") # Dit MOET zichtbaar zijn
        
    pg = st.navigation(pages)
    pg.run()

    with st.sidebar:
        st.divider()
        if st.button("Uitloggen"):
            logout()
