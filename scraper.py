import logging
import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.filedialog import asksaveasfilename, askopenfilename

import threading
import subprocess
import os
import re
from datetime import date, datetime
import queue
import sys
import argparse


# Globals for runtime state
stop_event = threading.Event()
scrape_start_time = None
inserted_signatures = set()  # in-memory signatures of already inserted records

# Configure logging
logging.basicConfig(
    filename="doctor_data_scraper.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Initialize the SQLite database
def initialize_database():
    logging.info("Initializing database.")
    conn = sqlite3.connect("doctor_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            riziv_nr TEXT UNIQUE,
            profession TEXT,
            convention_state TEXT,
            qualification TEXT,
            qualification_date TEXT,
            address TEXT,
            city TEXT
        )
    """)
    conn.commit()
    # Load existing signatures so we don't reinject duplicates across runs
    _load_existing_signatures(conn)
    return conn

# === Deduplication helpers ===
def _record_signature(record):
    """Return a tuple signature for a doctor record used for in-memory deduplication.

    Priority key is riziv_nr when defined; otherwise build a composite of other fields (case-insensitive).
    """
    (name, riziv_nr, profession, convention_state, qualification,
     qualification_date, address, city) = record
    if riziv_nr and riziv_nr.strip().lower() != "undefined":
        return ("R", riziv_nr.strip())
    norm = lambda v: (v or "").strip().lower()
    return (
        "F",
        norm(name),
        norm(profession),
        norm(convention_state),
        norm(qualification),
        norm(qualification_date),
        norm(address),
        norm(city),
    )

def _load_existing_signatures(conn):
    """Populate the in-memory signature set with rows already present in the DB."""
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT name, riziv_nr, profession, convention_state, qualification, qualification_date, address, city
            FROM doctors
        """)
        rows = cur.fetchall()
        for row in rows:
            inserted_signatures.add(_record_signature(row))
        logging.info(f"Loaded {len(rows)} existing rows into signature set.")
    except Exception as e:
        logging.warning(f"Failed loading existing signatures: {e}")

# Function to fetch a single page with retries
def fetch_page(page_number, location_value, retries=5):
    """Fetch a single result page for a given form location filter (0 or 1)."""
    url = (
        "http://localhost:8080/https://webappsa.riziv-inami.fgov.be/silverpages/Home/SearchHcw/" 
        f"?PageNumber={page_number}&Form.Name=&Form.FirstName=&Form.Profession=&Form.Specialisation="
        f"&Form.ConventionState=&Form.Location={location_value}&Form.NihdiNumber=&Form.Qualification="
        f"&Form.NorthEastLat=&Form.NorthEastLng=&Form.SouthWestLat=&Form.SouthWestLng=&Form.LocationLng=&Form.LocationLat="
    )
    for attempt in range(retries):
        try:
            logging.info(
                f"Fetching page {page_number} (Form.Location={location_value}), attempt {attempt + 1}/{retries}."
            )
            headers = {
                'Accept-Language': 'nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Cache-Control': 'max-age=0',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1'
            }
            cookies = {
                '.nihdi.language': 'c%3Dnl-BE%7Cuic%3Dnl-BE'
            }
            response = requests.get(url, headers=headers, cookies=cookies, timeout=60)
            response.raise_for_status()
            logging.info(
                f"Successfully fetched page {page_number} (Form.Location={location_value})."
            )
            return response.text
        except requests.exceptions.RequestException as e:
            logging.warning(
                f"Error fetching page {page_number} (Form.Location={location_value}), attempt {attempt + 1}: {e}"
            )
            time.sleep(3)  # Wait before retrying
    logging.error(f"Failed to fetch page {page_number} (Form.Location={location_value}) after {retries} attempts.")
    return None

# Extract data from a single page
def extract_data(html):
    """Parse a search result page and return list of doctor tuple records."""
    logging.info("Extracting data from HTML.")
    soup = BeautifulSoup(html, "html.parser")
    entries = soup.select(".card")
    data = []

    def normalize(text: str) -> str:
        # Collapse whitespace & strip
        return re.sub(r"\s+", " ", text).strip()

    for idx, entry in enumerate(entries, start=1):
        def get_value(label_text):
            rows = entry.find_all("div", class_="row")
            for row in rows:
                label = row.find("label")
                if label and label_text in label.get_text(strip=True):
                    value_div = row.find("div", class_="col-sm-8")
                    if value_div:
                        # Collect all small tag strings; fall back to any direct text
                        small_tags = value_div.find_all("small")
                        if small_tags:
                            combined = " ".join(" ".join(tag.stripped_strings) for tag in small_tags)
                        else:
                            combined = " ".join(value_div.stripped_strings)
                        return normalize(combined)
            return "undefined"

        try:
            name = get_value("Naam")
            riziv_nr = get_value("RIZIV-nr")
            profession = get_value("Beroep")
            convention_state = get_value("Conv.")
            qualification = get_value("Kwalificatie")
            qualification_date_raw = get_value("Kwal. datum")
            address = get_value("Werkadres")

            # Normalize qualification date (allow 1 or 2 digit day/month) -> ISO yyyy-mm-dd
            qualification_date = qualification_date_raw
            if qualification_date_raw and qualification_date_raw != "undefined":
                m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", qualification_date_raw)
                if m:
                    d, mth, y = map(int, m.groups())
                    try:
                        qualification_date = date(y, mth, d).isoformat()
                    except ValueError:
                        logging.warning(f"Invalid date values in '{qualification_date_raw}' for {name} ({riziv_nr}). Keeping raw.")

            # City extraction heuristic: look for last two tokens that look like postal code + city
            city = "undefined"
            if address != "undefined" and "geen hoofdwerkadres" not in address.lower():
                tokens = address.split()
                # Find token that is 4 digits (Belgian postal code) and take the rest as city
                for i, tok in enumerate(tokens):
                    if re.fullmatch(r"\d{4}", tok):
                        city_part = " ",
                        city_tokens = tokens[i:]
                        if len(city_tokens) >= 2:
                            city = normalize(" ".join(city_tokens[1:])) or "undefined"
                        break
                if city == "undefined" and len(tokens) >= 2:
                    city = normalize(tokens[-2] + ", " + tokens[-1])

            record = (name, riziv_nr, profession, convention_state, qualification, qualification_date, address, city)
            logging.debug(f"Parsed card #{idx}: name={name!r} riziv={riziv_nr!r} profession={profession!r} date={qualification_date!r}")
            data.append(record)
        except Exception as e:
            logging.exception(f"Error processing entry: {e}")

    logging.info(f"Extracted {len(data)} entries from the page.")
    # Log a sample for debugging
    for sample in data[:3]:
        logging.debug(f"Sample extracted record: {sample}")
    return data

# Remove duplicates from the database
def clean_duplicates(conn):
    logging.info("Cleaning duplicate entries in the database.")
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM doctors
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM doctors
            GROUP BY riziv_nr
        )
    """)
    conn.commit()

# Save data to the SQLite database
def save_data(conn, data):
    logging.info(f"Saving {len(data)} entries to the database.")
    cursor = conn.cursor()
    inserted = 0
    skipped = 0
    for record in data:
        try:
            sig = _record_signature(record)
            if sig in inserted_signatures:
                skipped += 1
                continue
            # Use OR IGNORE to respect UNIQUE constraint (riziv_nr) without throwing
            cursor.execute(
                """
                INSERT OR IGNORE INTO doctors
                (name, riziv_nr, profession, convention_state, qualification, qualification_date, address, city)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                record,
            )
            if cursor.rowcount == 1:  # actually inserted
                inserted_signatures.add(sig)
                inserted += 1
            else:
                skipped += 1
        except Exception as e:
            logging.warning(f"Failed to insert record {record}: {e}")
    conn.commit()
    logging.info(f"Inserted {inserted} new records; skipped {skipped} duplicates.")

# Fetch and store data
def fetch_and_store_data_thread(progress_bar, status_label, fetch_button, root, max_consecutive_empty=2, max_pages=1000, postal_codes=None, include_unknown_pass=True):
    """Fetch pages for each provided Belgian postal code (Form.Location) and store results.

    Stops paginating a postal code after `max_consecutive_empty` empty pages or reaching `max_pages`.
    """
    if not postal_codes:
        logging.error("No postal codes provided; aborting crawl.")
        status_label.config(text="No postal codes provided.")
        return

    conn = initialize_database()
    postal_codes = [pc for pc in postal_codes if re.fullmatch(r"\d{4}", pc)]
    if not postal_codes:
        logging.error("Postal code list after validation is empty; aborting.")
        status_label.config(text="Postal code list invalid.")
        return

    total_units = max_pages * len(postal_codes)
    progress_bar["value"] = 0
    progress_bar["maximum"] = total_units

    metrics = {}

    def update_gui(pc, page, empty_streak):
        idx = postal_codes.index(pc)
        progress_bar["value"] = min(idx * max_pages + page, progress_bar["maximum"])
        status_label.config(text=f"PC {pc} page {page} (empty {empty_streak})")
        root.update_idletasks()

    for pc in postal_codes:
        if stop_event.is_set():
            logging.info("Stop requested before starting next postal code loop.")
            break
        logging.info(f"=== Starting crawl for postal code {pc} ===")
        current_page = 1
        consecutive_empty = 0
        approx_inserted = 0
        while current_page <= max_pages and consecutive_empty < max_consecutive_empty:
            if stop_event.is_set():
                logging.info("Stop requested; breaking current postal code loop.")
                break
            html = fetch_page(current_page, pc)
            if not html:
                consecutive_empty += 1
                logging.warning(f"PC {pc} page {current_page}: fetch failed (no HTML) streak={consecutive_empty}")
                update_gui(pc, current_page, consecutive_empty)
                current_page += 1
                time.sleep(0.6)
                continue
            data = extract_data(html)
            if data:
                seen_riziv = set()
                unique_page = []
                for rec in data:
                    riziv = rec[1]
                    if riziv and riziv not in seen_riziv:
                        seen_riziv.add(riziv)
                        unique_page.append(rec)
                save_data(conn, unique_page)
                approx_inserted += len(unique_page)
                logging.info(f"PC {pc} page {current_page}: raw {len(data)} unique {len(unique_page)} cumulative ~{approx_inserted}")
                consecutive_empty = 0
            else:
                consecutive_empty += 1
                logging.info(f"PC {pc} page {current_page}: 0 entries (streak {consecutive_empty})")
            update_gui(pc, current_page, consecutive_empty)
            current_page += 1
            time.sleep(0.6)
        metrics[pc] = {
            "pages_crawled": current_page - 1,
            "approx_inserted": approx_inserted,
            "stopped_reason": (
                f"{consecutive_empty} empty pages" if consecutive_empty >= max_consecutive_empty else f"reached max_pages={max_pages}"
            )
        }
        logging.info(f"=== Finished postal code {pc}: {metrics[pc]} ===")

    # Optional additional pass to capture unknown addresses using Form.Location=0
    if include_unknown_pass and not stop_event.is_set():
        unknown_code = "0"
        # Allow a separate page cap for the unknown pass via env var (default: max_pages or 1000 if max_pages < 1000)
        try:
            env_unknown = os.environ.get("SCRAPER_UNKNOWN_MAX_PAGES")
            if env_unknown is not None:
                unknown_max_pages = int(env_unknown)
            else:
                # If user used a small per-postcode max_pages (like 100), still allow deeper unknown pass up to 1000 by default
                unknown_max_pages = 1000 if max_pages < 1000 else max_pages
        except ValueError:
            unknown_max_pages = max_pages
        logging.info(f"=== Starting unknown-address pass (Form.Location=0) up to {unknown_max_pages} pages ===")
        current_page = 1
        consecutive_empty = 0
        approx_inserted = 0
        # Extend progress bar maximum to reflect extra pass (difference only)
        progress_bar["maximum"] += unknown_max_pages
        while current_page <= unknown_max_pages and consecutive_empty < max_consecutive_empty:
            html = fetch_page(current_page, unknown_code)
            if not html:
                consecutive_empty += 1
                logging.info(f"UNKNOWN pass page {current_page}: fetch failed (streak {consecutive_empty})")
                current_page += 1
                continue
            data = extract_data(html)
            # Filter to records with no known address
            filtered = []
            for rec in data:
                address_val = (rec[6] or '').lower()
                if (not address_val) or ('geen hoofdwerkadres' in address_val) or address_val == 'undefined':
                    filtered.append(rec)
            if filtered:
                # Deduplicate within page by riziv
                seen_r = set()
                unique_page = []
                for rec in filtered:
                    riziv = rec[1]
                    if riziv and riziv not in seen_r:
                        seen_r.add(riziv)
                        unique_page.append(rec)
                save_data(conn, unique_page)
                approx_inserted += len(unique_page)
                consecutive_empty = 0
                logging.info(f"UNKNOWN pass page {current_page}: raw {len(data)} filtered {len(filtered)} inserted {len(unique_page)} cumulative {approx_inserted}")
            else:
                consecutive_empty += 1
                logging.info(f"UNKNOWN pass page {current_page}: 0 qualifying entries (streak {consecutive_empty})")
            progress_bar["value"] = min(progress_bar["value"] + 1, progress_bar["maximum"])
            status_label.config(text=f"Unknown pass page {current_page} (empty {consecutive_empty})")
            root.update_idletasks()
            current_page += 1
        metrics['UNKNOWN'] = {
            'pages_crawled': current_page - 1,
            'approx_inserted': approx_inserted,
            'stopped_reason': (
                f"{consecutive_empty} empty pages" if consecutive_empty >= max_consecutive_empty else f"reached unknown_max_pages={unknown_max_pages}"
            )
        }
        logging.info(f"=== Finished unknown-address pass: {metrics['UNKNOWN']} ===")

    clean_duplicates(conn)
    # Log final distinct count
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(DISTINCT riziv_nr) FROM doctors")
        total_distinct = cursor.fetchone()[0]
        logging.info(f"Total distinct RIZIV after crawl: {total_distinct}")
    except Exception as e:
        logging.warning(f"Could not compute distinct count: {e}")
    conn.close()
    progress_bar["value"] = progress_bar["maximum"]
    if stop_event.is_set():
        status_label.config(text="Stopped by user.")
        logging.info("Data fetching stopped by user.")
    else:
        status_label.config(text="Fetching Complete!")
        logging.info(f"Data fetching complete. Metrics: {metrics}")
    # Re-enable fetch button
    fetch_button.config(state="normal")

# Function to start fetching data in a thread
def start_fetching(progress_bar, status_label, fetch_button, postal_codes_entry, include_unknown_pass=True):
    fetch_button.config(state="disabled")
    stop_event.clear()
    global scrape_start_time
    scrape_start_time = time.time()
    raw_codes = postal_codes_entry.get("1.0", tk.END)
    postal_codes = []
    for token in re.split(r"\s+|,|;", raw_codes):
        token = token.strip()
        if re.fullmatch(r"\d{4}", token):
            # Filter out clearly invalid Belgian postal codes (<1000)
            if int(token) >= 1000:
                postal_codes.append(token)
    postal_codes = list(dict.fromkeys(postal_codes))  # preserve order, remove dups
    logging.info(f"User provided {len(postal_codes)} postal codes.")
    max_empty = int(os.environ.get("SCRAPER_MAX_EMPTY", "2"))
    max_pages = int(os.environ.get("SCRAPER_MAX_PAGES", "100"))  # lower default for per-postcode crawl
    threading.Thread(
        target=fetch_and_store_data_thread,
        args=(progress_bar, status_label, fetch_button, root, max_empty, max_pages, postal_codes, include_unknown_pass),
        daemon=True
    ).start()

# GUI Creation
def create_gui(include_unknown_pass=True):
    global root
    root = tk.Tk()
    root.title("Doctor Data Scraper")
    root.geometry("900x600")  # Increased width to accommodate the new column

    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    # Postal codes input
    postal_frame = tk.Frame(root)
    postal_frame.pack(padx=10, fill="x")
    tk.Label(postal_frame, text="Postal Codes (4-digit, separated by space/newline):").pack(anchor="w")
    postal_codes_entry = tk.Text(postal_frame, height=6)
    postal_codes_entry.pack(fill="x")
    # Attempt to preload from zips.txt if present
    def load_postal_codes_file(path=None):
        # If a path is explicitly provided, use it; else attempt default zips.txt
        if path is None:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zips.txt")
            if not os.path.isfile(path):
                messagebox.showinfo("Postal Codes", "Select a postal codes file (one 4-digit code per line).")
                path = askopenfilename(title="Select postal codes file", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
                if not path:
                    return
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
            # Remove header if present
            if lines and not re.fullmatch(r"\d{4}", lines[0]):
                lines = [ln for ln in lines[1:] if re.fullmatch(r"\d{4}", ln)]
            # Filter invalid (<1000) and dedup preserving order
            filtered = []
            seen = set()
            for code in lines:
                if re.fullmatch(r"\d{4}", code) and int(code) >= 1000 and code not in seen:
                    seen.add(code)
                    filtered.append(code)
            postal_codes_entry.delete("1.0", tk.END)
            postal_codes_entry.insert("1.0", "\n".join(filtered))
            logging.info(f"Loaded {len(filtered)} postal codes from zips.txt")
        except Exception as e:
            logging.error(f"Failed loading zips.txt: {e}")
            messagebox.showerror("Postal Codes", f"Failed to load zips.txt: {e}")

    load_postal_codes_file()  # attempt auto-load; will prompt if missing

    def choose_postal_codes_file():
        path = askopenfilename(title="Select postal codes file", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if path:
            load_postal_codes_file(path)

    btns_frame = tk.Frame(postal_frame)
    btns_frame.pack(anchor="e", pady=2, fill="x")
    tk.Button(btns_frame, text="Reload default", command=lambda: load_postal_codes_file(None)).pack(side=tk.RIGHT, padx=4)
    tk.Button(btns_frame, text="Load file...", command=choose_postal_codes_file).pack(side=tk.RIGHT)


    fetch_button = tk.Button(
        button_frame,
        text="Fetch Data",
        command=lambda: start_fetching(progress_bar, status_label, fetch_button, postal_codes_entry, include_unknown_pass),
        width=20,
    )
    fetch_button.pack(side=tk.LEFT, padx=10)

    def stop_fetch():
        stop_event.set()
        logging.info("Stop requested by user.")

    stop_button = tk.Button(
        button_frame,
        text="Stop",
        command=stop_fetch,
        width=10,
    )
    stop_button.pack(side=tk.LEFT, padx=10)

    export_button = tk.Button(
        button_frame, text="Export to Excel", command=export_to_excel, width=20
    )
    export_button.pack(side=tk.LEFT, padx=10)

    preview_button = tk.Button(
        root, text="Preview Data", command=lambda: preview_data(tree), width=20
    )
    preview_button.pack(pady=10)

    progress_bar = ttk.Progressbar(root, orient="horizontal", mode="determinate")
    progress_bar.pack(fill="x", padx=10, pady=5)

    # Info frame (elapsed time + distinct count)
    info_frame = tk.Frame(root)
    info_frame.pack(fill="x", padx=10)
    elapsed_label = tk.Label(info_frame, text="Elapsed: 0s")
    elapsed_label.pack(side=tk.LEFT, padx=(0,15))
    count_label = tk.Label(info_frame, text="Distinct doctors: 0")
    count_label.pack(side=tk.LEFT, padx=(0,15))

    status_label = tk.Label(root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
    status_label.pack(side=tk.BOTTOM, fill=tk.X)

    # In-GUI log list
    log_list = tk.Listbox(root, height=8)
    log_list.pack(fill="x", padx=10, pady=4)

    class ListboxHandler(logging.Handler):
        def __init__(self, listbox, max_lines=200):
            super().__init__()
            self.listbox = listbox
            self.max_lines = max_lines
        def emit(self, record):
            msg = self.format(record)
            def append():
                try:
                    self.listbox.insert(tk.END, msg)
                    if self.listbox.size() > self.max_lines:
                        # keep last max_lines lines
                        excess = self.listbox.size() - self.max_lines
                        for _ in range(excess):
                            self.listbox.delete(0)
                    self.listbox.yview_moveto(1)
                except Exception:
                    pass
            try:
                self.listbox.after(0, append)
            except Exception:
                pass

    gui_handler = ListboxHandler(log_list)
    gui_handler.setLevel(logging.INFO)
    gui_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"))
    logging.getLogger().addHandler(gui_handler)

    def periodic_update():
        # Elapsed time and distinct count refresh
        if scrape_start_time:
            elapsed = int(time.time() - scrape_start_time)
            elapsed_label.config(text=f"Elapsed: {elapsed}s")
            # Update distinct count every 3 seconds
            if elapsed % 3 == 0:
                try:
                    conn = sqlite3.connect("doctor_data.db")
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(DISTINCT riziv_nr) FROM doctors")
                    cnt = cur.fetchone()[0]
                    conn.close()
                    count_label.config(text=f"Distinct doctors: {cnt}")
                except Exception:
                    pass
        root.after(1000, periodic_update)

    periodic_update()

    tree_frame = tk.Frame(root)
    tree_frame.pack(fill="both", expand=True)

    # Create vertical scrollbar
    tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
    tree_scroll_y.pack(side=tk.RIGHT, fill="y")

    # Create horizontal scrollbar
    tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
    tree_scroll_x.pack(side=tk.BOTTOM, fill="x")

    # Add "City" column to the Treeview
    tree = ttk.Treeview(
        tree_frame,
        columns=(
            "Name",
            "RIZIV-nr",
            "Profession",
            "Convention State",
            "Qualification",
            "Qualification Date",
            "Address",
            "City",
        ),
        show="headings",
        yscrollcommand=tree_scroll_y.set,  # Link vertical scrollbar
        xscrollcommand=tree_scroll_x.set,  # Link horizontal scrollbar
    )
    tree.pack(fill="both", expand=True)

    # Configure the scrollbars to control the treeview
    tree_scroll_y.config(command=tree.yview)
    tree_scroll_x.config(command=tree.xview)

    # Set column headings and widths
    for col in tree["columns"]:
        tree.heading(col, text=col)
        if col == "Address":  # Make the "Address" column wider
            tree.column(col, width=200)
        elif col == "City":  # Adjust the width for the "City" column
            tree.column(col, width=100)
        else:
            tree.column(col, width=120)

    root.mainloop()

def preview_data(tree):
    conn = sqlite3.connect("doctor_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, riziv_nr, profession, convention_state, qualification, qualification_date, address, city
    FROM doctors
    ORDER BY name COLLATE NOCASE ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    tree.delete(*tree.get_children())
    for row in rows:
        tree.insert("", "end", values=row)

def export_to_excel_thread():
    """
    Function to export data to an Excel file in a separate thread.
    """
    try:
        conn = sqlite3.connect("doctor_data.db")
        df = pd.read_sql_query("SELECT * FROM doctors", conn)
        conn.close()
        df = df.drop_duplicates(subset=["riziv_nr"])
        file_path = asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")]
        )
        if file_path:
            df.to_excel(file_path, index=False)
            messagebox.showinfo("Export Complete", f"Data has been exported to {file_path}")
    except Exception as e:
        logging.error(f"Error exporting to Excel: {e}")
        messagebox.showerror("Export Failed", f"An error occurred while exporting: {e}")

def export_to_excel():
    """
    Function to start the Excel export in a separate thread.
    """
    threading.Thread(target=export_to_excel_thread, daemon=True).start()


def start_proxy():
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy", "server.js")
    subprocess.run(
        ["node", script_path],
        creationflags=subprocess.CREATE_NO_WINDOW
    )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Doctor Data Scraper")
    parser.add_argument("--no-unknown-pass", action="store_true", help="Disable the unknown pass (Form.Location=0)")
    args, unknown = parser.parse_known_args()
    threading.Thread(target=start_proxy, daemon=True).start()
    # Pass the toggle to the GUI
    create_gui(include_unknown_pass=not args.no_unknown_pass)
