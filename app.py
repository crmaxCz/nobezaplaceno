import streamlit as st
import subprocess
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. INSTALACE PROHLÍŽEČE ---
def install_playwright_browser():
    if "browser_installed" not in st.session_state:
        with st.spinner("Příprava systému (instalace Chromia)..."):
            subprocess.run(["playwright", "install", "chromium"])
            st.session_state["browser_installed"] = True

install_playwright_browser()
from playwright.sync_api import sync_playwright

# --- 2. KONFIGURACE ---
POBOCKY = {
    "136": "Praha", "137": "Brno", "268": "Plzeň", "354": "Ostrava",
    "133": "Olomouc", "277": "Hradec Králové", "326": "Liberec",
    "387": "Pardubice", "151": "Nový Jičín", "321": "Frýdek - Místek",
    "237": "Havířov", "203": "Opava", "215": "Trutnov", "400": "Zlín"
}

st.set_page_config(page_title="NOBE Dashboard", layout="wide")

USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

# --- 3. SCRAPER FUNKCE ---
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    dnes = datetime.now().strftime("%d.%m.%Y")
    budoucno = (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = context.new_page()

        try:
            # KROK 1: Login
            page.goto("https://nobe.moje-autoskola.cz/index.php", timeout=60000)
            page.fill('input[name="log_email"]', username)
            page.fill('input[name="log_heslo"]', password)
            page.click('input[type="submit"]')
            page.wait_for_url("**/index.php*", timeout=30000)

            # KROK 2: Seznam termínů (Filtrovaná URL)
            url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_datum_do={budoucno}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
            page.goto(url_seznam, wait_until="domcontentloaded", timeout=60000)
            
            # Najdeme všechny odkazy na přednášky (agresivní selektor)
            all_links = page.query_selector_all("a[href*='admin_prednaska.php?edit_id=']")
            
            urls = []
            for link in all_links:
                href = link.get_attribute("href")
                if href:
                    # Pokud je URL relativní, přidáme doménu
                    if href.startswith("/"):
                        full_url = f"https://nobe.moje-autoskola.cz{href}"
                    elif href.startswith("admin_"):
                        full_url = f"https://nobe.moje-autoskola.cz/{href}"
                    else:
                        full_url = href
                    
                    if full_url not in urls:
                        urls.append(full_url)

            if not urls:
                st.warning(f"V systému nebyly pro pobočku {pobocka_nazev} nalezeny žádné budoucí termíny.")
                return pd.DataFrame()

            # KROK 3: Procházení detailů
            status_txt = st.empty()
            p_bar = st.progress(0)

            for i, detail_url in enumerate(urls[:15]): # Limit 15 pro stabilitu
                page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(1000) # Krátká pauza na vykreslení tabulky
                
                try:
                    title = page.inner_text("h1").replace("Přednáška - ", "").strip()
                    status_txt.text(f"Zpracovávám: {title}")
                    
                    # Hledáme tabulku se seznamem žáků
                    table = page.query_selector("table.table-striped")
                    if table:
                        rows = table.query_selector_all("tbody tr")
                        prihlaseno = 0
                        uhrazeno = 0
                        
                        for row in rows:
                            cells = row.query_selector_all("td")
                            # Podle tvého HTML: Sloupec 5 (index 4) je Uhrazeno
                            if len(cells) >= 5:
                                row_content = row.inner_text()
                                if "∑" in row_content: # Ignorujeme patičku
                                    continue
                                
                                prihlaseno += 1
                                payment_cell = cells[4].inner_text()
                                
                                # Extrakce částky před "z"
                                # Odstraní &nbsp;, mezery, Kč a vezme jen to před "z"
                                pre_z = payment_cell.split('z')[0]
                                only_digits = re.sub(r'\D', '', pre_z)
                                
                                if only_digits and int(only_digits) > 0:
                                    uhrazeno += 1
                        
                        if prihlaseno > 0:
                            data_list.append({"Termín": title, "Přihlášeno": prihlaseno, "Uhrazeno": uhrazeno})
                except:
                    continue
                p_bar.progress((i + 1) / len(urls[:15]))
            
            status_txt.empty()
            p_bar.empty()

        except Exception as e:
            st.error(f"Chyba při stahování dat: {str(e)}")
        finally:
            browser.close()

    return pd.DataFrame(data_list)

# --- 4. DASHBOARD ---
st.sidebar.header("Nastavení")
selected_pobocka = st.sidebar.radio("Vyberte pobočku:", list(POBOCKY.values()))
pobocka_id = [k for k, v in POBOCKY.items() if v == selected_pobocka][0]

if st.sidebar.button("🔄 Načíst čerstvá data"):
    st.cache_data.clear()
    st.rerun()

st.title(f"📊 Obsazenost a platby: {selected_pobocka}")

@st.cache_data(ttl=600)
def load_and_cache(pid, pname, u, p):
    return get_pobocka_data(pid, pname, u, p)

df = load_and_cache(pobocka_id, selected_pobocka, USER, PW)

if not df.empty:
    df['Neuhrazeno'] = df['Přihlášeno'] - df['Uhrazeno']
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Termínů", len(df))
    col2.metric("Žáků celkem", df['Přihlášeno'].sum())
    col3.metric("Zaplaceno", df['Uhrazeno'].sum())

    st.subheader("Graf obsazenosti")
    st.bar_chart(df.set_index("Termín")[["Uhrazeno", "Neuhrazeno"]])
    
    st.subheader("Detailní tabulka")
    st.dataframe(df, use_container_width=True)
else:
    st.info("Žádná data k zobrazení. Zkuste jinou pobočku nebo vynutit obnovení dat.")
