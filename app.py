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
@st.cache_data(show_spinner="Analyzuji termíny (následující 3 měsíce)...", ttl=3600)
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    dnes_obj = datetime.now()
    budoucno_obj = dnes_obj + timedelta(days=90)
    dnes = dnes_obj.strftime("%d.%m.%Y")
    budoucno = budoucno_obj.strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # 1. KROK: Přihlášení
        page.goto("https://nobe.moje-autoskola.cz/index.php")
        page.fill('input[name="log_email"]', username)
        page.fill('input[name="log_heslo"]', password)
        page.click('input[type="submit"]')
        page.wait_for_load_state("networkidle")
        
        # DEBUG: Co vidí robot po přihlášení?
        # st.write(f"Aktuální URL po loginu: {page.url}")

        # 2. KROK: Seznam přednášek
        url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_datum_do={budoucno}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
        page.goto(url_seznam)
        page.wait_for_timeout(2000) # Počkáme 2 vteřiny na vykreslení tabulky
        
        # Najdeme odkazy. Zkusíme být víc obecní, kdyby se URL mírně lišila
        links = page.query_selector_all("a")
        urls = []
        for l in links:
            href = l.get_attribute("href")
            if href and "admin_prednaska.php?edit_id=" in href:
                # Očistíme URL od případných nesmyslů
                clean_url = href.split('&')[0] if 'edit_id' in href else href
                urls.append(clean_url)
        
        urls = list(set(urls)) # Unikátní termíny
        
        # DEBUG: Kolik termínů robot našel?
        # st.write(f"Nalezeno termínů: {len(urls)}")

        if not urls:
             # Pokud nic nenajde, zkusíme vypsat kousek textu ze stránky, abychom věděli, kde jsme
             obsah = page.inner_text("body")[:500]
             st.error(f"Na stránce se seznamem nebyl nalezen žádný odkaz na detail přednášky. Robot vidí: {obsah}")
             return pd.DataFrame()

        for detail_url in urls:
            full_url = f"https://nobe.moje-autoskola.cz/{detail_url}" if "http" not in detail_url else detail_url
            page.goto(full_url)
            page.wait_for_timeout(1000)
            
            try:
                termin_name = page.inner_text("h1").replace("Přednáška - ", "").strip()
                rows = page.query_selector_all("#table_seznam_zaku tr")
                
                prihlaseno = 0
                uhrazeno = 0
                
                for row in rows:
                    cells = row.query_selector_all("td")
                    if len(cells) >= 6:
                        prihlaseno += 1
                        text_uhrazeno = cells[5].inner_text().strip()
                        
                        # Odstraníme vše kromě čísel a písmene 'z'
                        clean_text = re.sub(r'[^0-9z]', '', text_uhrazeno.lower())
                        
                        if 'z' in clean_text:
                            zaplaceno_raw = clean_text.split('z')[0]
                            if zaplaceno_raw and int(zaplaceno_raw) > 0:
                                uhrazeno += 1
                        else:
                            if clean_text and int(clean_text) > 0:
                                uhrazeno += 1
                
                if prihlaseno > 0:
                    data_list.append({
                        "Termín": termin_name,
                        "Přihlášeno": prihlaseno,
                        "Uhrazeno": uhrazeno
                    })
            except:
                continue
                
        browser.close()

    new_df = pd.DataFrame(data_list)
    if not new_df.empty:
        new_df['datum_obj'] = pd.to_datetime(new_df['Termín'].str.split(' ').str[0], dayfirst=True, errors='coerce')
        new_df = new_df.sort_values('datum_obj').drop(columns=['datum_obj'])
        
    return new_df
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
