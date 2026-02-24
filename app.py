import streamlit as st
import subprocess
import os
import pandas as pd
import re
from datetime import datetime

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
@st.cache_data(show_spinner="Analyzuji termíny...", ttl=3600)
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    dnes = datetime.now().strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Přihlášení (používáme tvoje zjištěné názvy polí)
        page.goto("https://nobe.moje-autoskola.cz/index.php")
        page.fill('input[name="log_email"]', username)
        page.fill('input[name="log_heslo"]', password)
        page.click('input[type="submit"]')
        page.wait_for_load_state("networkidle")
        
        url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
        page.goto(url_seznam)
        
        links = page.query_selector_all("a[href*='admin_prednaska.php?edit_id=']")
        urls = list(set([l.get_attribute("href") for l in links]))
        
        for detail_url in urls:
            page.goto(f"https://nobe.moje-autoskola.cz/{detail_url}")
            try:
                termin_name = page.inner_text("h1").replace("Přednáška - ", "").strip()
                rows = page.query_selector_all("#table_seznam_zaku tr")
                
                prihlaseno = 0
                uhrazeno = 0
                raw_values = []
                
                for row in rows:
                    cells = row.query_selector_all("td")
                    if len(cells) > 5:
                        prihlaseno += 1
                        text_uhrazeno = cells[5].inner_text().strip()
                        raw_values.append(text_uhrazeno)
                        
                        casti = text_uhrazeno.split('z')
                        if len(casti) > 1:
                            prvni_cast = casti[0]
                            jen_cisla = re.sub(r'\D', '', prvni_cast)
                            if jen_cisla and int(jen_cisla) > 0:
                                uhrazeno += 1
                
                if prihlaseno > 0:
                    data_list.append({
                        "Termín": termin_name,
                        "Přihlášeno": prihlaseno,
                        "Uhrazeno": uhrazeno,
                        "DEBUG_TEXT": ", ".join(raw_values[:3])
                    })
            except:
                continue
                
        browser.close()

    # --- TADY BYLA CHYBA (Původně jsi zde měl return pd.DataFrame(data_list), což ukončilo funkci předčasně) ---
    new_df = pd.DataFrame(data_list)
    
    if not new_df.empty:
        try:
            # Vytvoříme pomocný sloupec pro řazení podle data
            # Bere první část textu (např. 5.3.2025) a převede na datum
            new_df['datum_obj'] = pd.to_datetime(new_df['Termín'].str.split(' ').str[0], dayfirst=True, errors='coerce')
            new_df = new_df.sort_values('datum_obj')
            new_df = new_df.drop(columns=['datum_obj'])
        except Exception as e:
            st.error(f"Chyba při řazení: {e}")
            
    return new_df # Teď už vrací správně seřazenou tabulku

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
