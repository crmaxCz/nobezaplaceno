import streamlit as st
import subprocess
import pandas as pd
import re
from datetime import datetime, timedelta

# --- 1. INSTALACE ---
def install_playwright_browser():
    if "browser_installed" not in st.session_state:
        with st.spinner("Instalace prohlížeče..."):
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

st.set_page_config(page_title="NOBE Zaplaceno", layout="wide")

USER = st.secrets["moje_jmeno"]
PW = st.secrets["moje_heslo"]

# --- 3. SCRAPER ---
def get_pobocka_data(pobocka_id, pobocka_nazev, username, password):
    data_list = []
    # Filtr na 3 měsíce dopředu
    dnes = datetime.now().strftime("%d.%m.%Y")
    budoucno = (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        try:
            # A. LOGIN
            page.goto("https://nobe.moje-autoskola.cz/index.php")
            page.fill('input[name="log_email"]', username)
            page.fill('input[name="log_heslo"]', password)
            page.click('input[type="submit"]')
            page.wait_for_url("**/index.php*")

            # B. SEZNAM (podle tvého HTML)
            url_seznam = f"https://nobe.moje-autoskola.cz/admin_prednasky.php?vytez_datum_od={dnes}&vytez_datum_do={budoucno}&vytez_typ=545&vytez_lokalita={pobocka_id}&akce=prednasky_filtr"
            page.goto(url_seznam, wait_until="networkidle")
            
            # Hledáme odkazy přesně podle tvého HTML (tr.text-warning td a)
            links = page.query_selector_all("tr.text-warning td a[href*='admin_prednaska.php?edit_id=']")
            
            # Vyčištění URL (přidání domény) a unikátnost
            urls = []
            for l in links:
                href = l.get_attribute("href")
                if href:
                    full_url = "https://nobe.moje-autoskola.cz" + (href if href.startswith("/") else "/" + href)
                    if full_url not in urls:
                        urls.append(full_url)

            if not urls:
                st.warning(f"Na pobočce {pobocka_nazev} nebyly v seznamu nalezeny žádné budoucí přednášky.")
                return pd.DataFrame()

            # C. SBĚR DAT Z DETAILŮ
            status = st.empty()
            bar = st.progress(0)

            for i, detail_url in enumerate(urls[:20]): # Limit 20 termínů pro rychlost
                page.goto(detail_url, wait_until="domcontentloaded")
                
                try:
                    # Název z H1
                    title = page.inner_text("h1").replace("Přednáška - ", "").strip()
                    status.text(f"Analyzuji: {title}")

                    # Tabulka žáků (podle tvého elementu table.table-striped)
                    table = page.query_selector("table.table-striped")
                    if table:
                        rows = table.query_selector_all("tbody tr")
                        prihlaseno = 0
                        uhrazeno = 0
                        
                        for row in rows:
                            cells = row.query_selector_all("td")
                            # Musí to být řádek žáka (aspoň 5 buněk) a nesmí to být suma ∑
                            if len(cells) >= 5 and "∑" not in row.inner_text():
                                prihlaseno += 1
                                # 5. sloupec (index 4) je Uhrazeno
                                pay_txt = cells[4].inner_text().split('z')[0]
                                clean_val = "".join(filter(str.isdigit, pay_txt))
                                if clean_val and int(clean_val) > 0:
                                    uhrazeno += 1
                        
                        if prihlaseno > 0:
                            data_list.append({"Termín": title, "Přihlášeno": prihlaseno, "Uhrazeno": uhrazeno})
                except:
                    continue
                bar.progress((i + 1) / len(urls[:20]))

            status.empty()
            bar.empty()

        except Exception as e:
            st.error(f"Chyba: {e}")
        finally:
            browser.close()

    return pd.DataFrame(data_list)

# --- 4. UI DASHBOARD ---
st.sidebar.header("📍 Pobočka")
pobocka_name = st.sidebar.selectbox("Vyberte:", list(POBOCKY.values()))
pobocka_id = [k for k, v in POBOCKY.items() if v == pobocka_name][0]

if st.sidebar.button("🔄 Načíst nová data"):
    st.cache_data.clear()

st.title(f"Přehled plateb: {pobocka_name}")

# Cache na 15 minut
@st.cache_data(ttl=900)
def load_data(pid, pname, u, p):
    return get_pobocka_data(pid, pname, u, p)

df = load_data(pobocka_id, pobocka_name, USER, PW)

if not df.empty:
    df['Neuhrazeno'] = df['Přihlášeno'] - df['Uhrazeno']
    
    c1, c2 = st.columns(2)
    c1.metric("Celkem přihlášených", df['Přihlášeno'].sum())
    c2.metric("Celkem zaplaceno", df['Uhrazeno'].sum())
    
    st.bar_chart(df.set_index("Termín")[["Uhrazeno", "Neuhrazeno"]])
    st.dataframe(df, use_container_width=True)
else:
    st.info("Žádná data k zobrazení. Zkuste jinou pobočku nebo obnovit data.")
