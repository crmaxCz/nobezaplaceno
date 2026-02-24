import streamlit as st
import subprocess
import os
import pandas as pd
import re

# Funkce pro instalaci prohlížeče, pokud chybí
def install_playwright_browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        # Pokud by náhodou knihovna chyběla v prostředí
        subprocess.run(["pip", "install", "playwright"])
        from playwright.sync_api import sync_playwright
    
    # Instalace samotného prohlížeče Chromium
    # Provádíme pouze jednou za restart aplikace
    if "browser_installed" not in st.session_state:
        subprocess.run(["playwright", "install", "chromium"])
        st.session_state["browser_installed"] = True

# Spustíme instalaci hned na začátku
install_playwright_browser()
from playwright.sync_api import sync_playwright

# --- KONFIGURACE ---
POBOCKY = {
    "136": "Praha", "137": "Brno", "268": "Plzeň", "354": "Ostrava",
    "133": "Olomouc", "277": "Hradec Králové", "326": "Liberec",
    "387": "Pardubice", "151": "Nový Jičín", "321": "Frýdek - Místek",
    "237": "Havířov", "203": "Opava", "215": "Trutnov", "400": "Zlín"
}

st.set_page_config(page_title="AŠ NOBE Statistiky", layout="wide")

# Načtení tajných údajů z Trezoru (Secrets)
USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

# --- FUNKCE S CACHE ---
@st.cache_data(show_spinner="Stahuji čerstvá data z autoškoly...", ttl=3600) # cache platí 1 hodinu
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Přihlášení
        page.goto("https://nobe.moje-autoskola.cz/index.php")
        page.fill('input[name="log_email"]', username)  # Opraveno z prihlasovaci_jmeno
        page.fill('input[name="log_heslo"]', password)  # Opraveno z heslo
        page.click('input[type="submit"]')
        page.wait_for_load_state("networkidle")
        
        # Načtení seznamu termínů
        url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od=01.01.2024&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
        page.goto(url_seznam)
        
        links = page.query_selector_all("a[href*='admin_prednaska.php?edit_id=']")
        urls = list(set([l.get_attribute("href") for l in links]))[:10] # Omezíme na prvních 10 pro test rychlosti
        
        for detail_url in urls:
            page.goto(f"https://nobe.moje-autoskola.cz/{detail_url}")
            try:
                # Získání názvu/data (předpokládáme h1)
                termin_name = page.inner_text("h1").replace("Přednáška - ", "")
                rows = page.query_selector_all("#table_seznam_zaku tr")
                
                prihlaseno = 0
                uhrazeno = 0
                for row in rows:
                    cells = row.query_selector_all("td")
                    if len(cells) > 5:
                        prihlaseno += 1
                        if re.search(r'\d.*z', cells[5].inner_text()):
                            uhrazeno += 1
                
                data_list.append({
                    "Termín": termin_name,
                    "Přihlášeno": prihlaseno,
                    "Uhrazeno": uhrazeno
                })
            except:
                continue
                
        browser.close()
    return pd.DataFrame(data_list)

# --- BOČNÍ PANEL (Vzhledová úprava) ---
with st.sidebar:
    st.header("📍 Pobočky")
    # Radio button vytvoří seznam pod sebou
    vybrana_pobocka_nazev = st.radio(
        "Vyberte pobočku k zobrazení:",
        options=list(POBOCKY.values()),
        index=0 # Defaultně Praha
    )
    
    # Najdeme ID k vybranému názvu
    vybrana_pobocka_id = [k for k, v in POBOCKY.items() if v == vybrana_pobocka_nazev][0]
    
    st.divider()
    if st.button("🔄 Vynutit totální refresh"):
        st.cache_data.clear()
        st.rerun()

# --- HLAVNÍ OBSAH ---
st.subheader(f"Statistiky pro: {vybrana_pobocka_nazev}")

# Automatické spuštění díky cache
df = get_pobocka_data(vybrana_pobocka_id, vybrana_pobocka_nazev, USER, PW)

if not df.empty:
    # Pomocné sloupce
    df['Neuhrazeno'] = df['Přihlášeno'] - df['Uhrazeno']
    
    # Karty s rychlým přehledem
    c1, c2 = st.columns(2)
    c1.metric("Celkem přihlášeno", df['Přihlášeno'].sum())
    c2.metric("Celkem uhrazeno", df['Uhrazeno'].sum())

    # Graf
    st.bar_chart(df.set_index("Termín")[["Uhrazeno", "Neuhrazeno"]])
    
    # Tabulka
    st.dataframe(df, use_container_width=True)
else:
    st.info("Pro tuto pobočku nebyla nalezena žádná data nebo probíhá načítání.")
