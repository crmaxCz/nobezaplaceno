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
@st.cache_data(show_spinner="Přihlašuji se a stahuji data...", ttl=600)
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    dnes = datetime.now().strftime("%d.%m.%Y")
    budoucno = (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        # Spuštění prohlížeče s parametry pro stabilitu
        browser = p.chromium.launch(headless=True, args=["--disable-gpu", "--no-sandbox"])
        # Vytvoříme kontext (v něm žijí cookies o přihlášení)
        context = browser.new_context()
        page = context.new_page()

        try:
            # KROK 1: Přihlášení (uděláme jen jednou)
            page.goto("https://nobe.moje-autoskola.cz/index.php", timeout=60000)
            page.fill('input[name="log_email"]', username)
            page.fill('input[name="log_heslo"]', password)
            page.click('input[type="submit"]')
            
            # Počkáme, až se objevíme na hlavní ploše (potvrzení loginu)
            page.wait_for_url("**/index.php*", timeout=20000)

            # KROK 2: Skok na filtrovaný seznam (už jako přihlášený uživatel)
            url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_datum_do={budoucno}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
            page.goto(url_seznam, wait_until="domcontentloaded", timeout=45000)
            
            # Najdeme odkazy na detaily (edit_id)
            links = page.query_selector_all("a[href*='admin_prednaska.php?edit_id=']")
            urls = list(set([l.get_attribute("href") for l in links]))

            if not urls:
                # Malý trik: Pokud robot nic nevidí, vypíšeme mu text stránky pro kontrolu
                debug_text = page.inner_text("body")[:150].replace("\n", " ")
                st.warning(f"Pobočka {pobocka_nazev}: Žádné termíny. (Robot vidí: {debug_text})")
                return pd.DataFrame()

            # KROK 3: Procházení detailů (velmi rychlé díky existující session)
            for detail_url in urls[:15]: # Omezení na 15 pro rychlost
                full_url = f"https://nobe.moje-autoskola.cz/{detail_url}" if "http" not in detail_url else detail_url
                page.goto(full_url, wait_until="domcontentloaded", timeout=20000)
                
                try:
                    # Název z H1
                    termin_name = page.inner_text("h1", timeout=5000).replace("Přednáška - ", "").strip()
                    
                    # Analýza tabulky žáků
                    rows = page.query_selector_all("#table_seznam_zaku tr")
                    prihlaseno = 0
                    uhrazeno = 0
                    
                    for row in rows:
                        cells = row.query_selector_all("td")
                        if len(cells) >= 6:
                            prihlaseno += 1
                            txt = cells[5].inner_text().split('z')[0]
                            # Vyfiltrujeme jen číslice
                            num_str = "".join(filter(str.isdigit, txt))
                            if num_str and int(num_str) > 0:
                                uhrazeno += 1
                    
                    if prihlaseno > 0:
                        data_list.append({"Termín": termin_name, "Přihlášeno": prihlaseno, "Uhrazeno": uhrazeno})
                except:
                    continue

        except Exception as e:
            st.error(f"Chyba při komunikaci: {str(e)}")
        finally:
            browser.close()

    # Zpracování dat do tabulky
    df = pd.DataFrame(data_list)
    if not df.empty:
        # Převedeme na datum pro řazení
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
