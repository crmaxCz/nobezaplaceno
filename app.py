import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta

# Konfigurace stránky
st.set_page_config(page_title="Dashboard Přednášek NOBE", layout="wide")

# Definice poboček (ID: Název)
BRANCHES = {
    "136": "Praha", "137": "Brno", "268": "Plzeň", "354": "Ostrava",
    "133": "Olomouc", "277": "Hradec Králové", "326": "Liberec",
    "387": "Pardubice", "151": "Nový Jičín", "321": "Frýdek - Místek",
    "237": "Havířov", "203": "Opava", "215": "Trutnov", "400": "Zlín"
}

# Načtení přihlašovacích údajů ze Streamlit Secrets
EMAIL = st.secrets["EMAIL"]
PASSWORD = st.secrets["PASSWORD"]

def get_session():
    """Vytvoří přihlášenou session."""
    session = requests.Session()
    login_url = "https://nobe.moje-autoskola.cz/index.php"
    # Typické názvy polí pro tento systém, pokud by nefungovaly, je třeba je ověřit v HTML login formuláři
    payload = {
        "prihlasit_email": EMAIL,
        "prihlasit_heslo": PASSWORD,
        "akce": "prihlasit"
    }
    session.post(login_url, data=payload)
    return session

@st.cache_data(ttl=3600) # Cache na 1 hodinu
def fetch_lectures(branch_id):
    """Scrapuje data pro konkrétní pobočku."""
    date_from = datetime.now().strftime("%d.%m.%Y")
    date_to = (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y")
    
    url = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={date_from}&vytez_datum_do={date_to}&vytez_typ=545&vytez_lokalita={branch_id}&akce=prednasky_filtr"
    
    session = get_session()
    response = session.get(url)
    
    if response.status_code != 200:
        return None

    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table", {"id": "tab-terminy"})
    
    lectures = []
    
    if table:
        rows = table.find_all("tr")[1:]  # Přeskočit hlavičku
        for row in rows:
            cols = row.find_all("td")
            if len(cols) > 0:
                # Datum a čas jsou obvykle v prvním sloupci v tagu <a>
                date_time_text = cols[0].get_text(strip=True)
                lectures.append({"Datum a čas": date_time_text})
    
    return pd.DataFrame(lectures)

# UI - Sidebar
st.sidebar.header("Nastavení")
selected_city = st.sidebar.selectbox("Vyberte pobočku", options=list(BRANCHES.values()))
# Získání ID podle vybraného města
selected_id = [id for id, name in BRANCHES.items() if name == selected_city][0]

load_button = st.sidebar.button("Načíst / Obnovit data")

# Hlavní panel
st.title(f"Přednášky - {selected_city}")

if load_button:
    with st.spinner('Stahuji data...'):
        df = fetch_lectures(selected_id)
        
        if df is not None and not df.empty:
            st.success(f"Nalezeno {len(df)} termínů na příští 3 měsíce.")
            st.table(df) # Zobrazení statické tabulky (jednodušší) nebo st.dataframe(df)
        else:
            st.info("Pro tuto pobočku nebyly v daném období nalezeny žádné přednášky.")
else:
    st.write("Vyberte pobočku v levém panelu a klikněte na tlačítko pro načtení dat.")
