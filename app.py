import streamlit as st
import subprocess
import os
import pandas as pd
import re
from datetime import datetime, timedelta

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
@st.cache_data(show_spinner="Navazuji spojení se systémem...", ttl=600)
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    dnes = datetime.now().strftime("%d.%m.%Y")
    budoucno = (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        # Spustíme prohlížeč s parametry pro vyšší stabilitu
        browser = p.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox"])
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        # ZRYCHLENÍ: Blokujeme stahování obrázků a stylů
        page.route("**/*.{png,jpg,jpeg,svg,css,woff,woff2}", lambda route: route.abort())

        try:
            # 1. LOGIN - Jdeme přímo na login
            page.goto("https://nobe.moje-autoskola.cz/index.php", timeout=60000)
            page.fill('input[name="log_email"]', username)
            page.fill('input[name="log_heslo"]', password)
            
            # Klikneme a počkáme na změnu URL (přihlášení)
            page.click('input[type="submit"]')
            page.wait_for_url("**/index.php*", timeout=15000) 

            # 2. FILTR - Jdeme přímo na URL s filtrem
            url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_datum_do={budoucno}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
            
            # Nečekáme na 'load', ale jen na 'domcontentloaded' (stačí nám texty)
            page.goto(url_seznam, wait_until="domcontentloaded", timeout=45000)
            
            # Krátká pauza na JS tabulky
            page.wait_for_timeout(3000)

            # 3. SBĚR ODKAZŮ
            links = page.query_selector_all("a[href*='admin_prednaska.php?edit_id=']")
            urls = list(set([l.get_attribute("href") for l in links]))
            
            if not urls:
                # Pokud nic nenajde, vypíšeme co robot vidí (pro nás k ladění)
                obsah = page.inner_text("body")[:200].replace("\n", " ")
                st.warning(f"Na pobočce {pobocka_nazev} nejsou termíny. Robot vidí: {obsah}")
                return pd.DataFrame()

            # Limitujeme na prvních 15 termínů, aby to Streamlit neusekl kvůli času
            for detail_url in urls[:15]:
                full_url = f"https://nobe.moje-autoskola.cz/{detail_url}" if "http" not in detail_url else detail_url
                page.goto(full_url, wait_until="domcontentloaded")
                
                try:
                    termin_name = page.inner_text("h1", timeout=5000).replace("Přednáška - ", "").strip()
                    rows = page.query_selector_all("#table_seznam_zaku tr")
                    
                    prihlaseno = 0
                    uhrazeno = 0
                    
                    for row in rows:
                        cells = row.query_selector_all("td")
                        if len(cells) >= 6:
                            prihlaseno += 1
                            txt = cells[5].inner_text().split('z')[0]
                            if any(char.isdigit() for char in txt):
                                num = int(re.sub(r'\D', '', txt))
                                if num > 0: uhrazeno += 1
                    
                    if prihlaseno > 0:
                        data_list.append({"Termín": termin_name, "Přihlášeno": prihlaseno, "Uhrazeno": uhrazeno})
                except:
                    continue

        except Exception as e:
            st.error(f"Technický problém: {str(e)}")
        finally:
            browser.close()

    df = pd.DataFrame(data_list)
    if not df.empty:
        df['datum_obj'] = pd.to_datetime(df['Termín'].str.split(' ').str[0], dayfirst=True, errors='coerce')
        df = df.sort_values('datum_obj').drop(columns=['datum_obj'])
    return df
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
