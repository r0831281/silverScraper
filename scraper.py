import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.filedialog import asksaveasfilename
import threading
import subprocess
import os


# Initialize the SQLite database
def initialize_database():
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
    return conn


# Function to fetch a single page with retries
def fetch_page(page_number, retries=5):
    url = f"http://localhost:8080/https://webappsa.riziv-inami.fgov.be/silverpages/Home/SearchHcw/?PageNumber={page_number}&Form.Name=&Form.FirstName=&Form.Profession=&Form.Specialisation=&Form.ConventionState=&Form.Location=0&Form.NihdiNumber=&Form.Qualification=&Form.NorthEastLat=&Form.NorthEastLng=&Form.SouthWestLat=&Form.SouthWestLng=&Form.LocationLng=&Form.LocationLat="
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page_number}, attempt {attempt + 1}/{retries}: {e}")
            time.sleep(3)  # Wait before retrying
    return None


# Extract data from a single page
def extract_data(html):
    soup = BeautifulSoup(html, "html.parser")
    entries = soup.select(".card")
    data = []

    for entry in entries:
        def get_value(label_text):
            rows = entry.find_all("div", class_="row")
            for row in rows:
                label = row.find("label")
                if label and label_text in label.get_text(strip=True):
                    value_div = row.find("div", class_="col-sm-8")
                    if value_div:
                        small_tags = value_div.find_all("small")
                        return " ".join(" ".join(tag.stripped_strings) for tag in small_tags)
            return "undefined"

        # Extract fields
        name = get_value("Naam")
        riziv_nr = get_value("RIZIV-nr")
        profession = get_value("Beroep")
        convention_state = get_value("Conv.")
        qualification = get_value("Kwalificatie")
        qualification_date = get_value("Kwal. datum")
        address = get_value("Werkadres")

        # Extract city from address
        if address != "Geen hoofdwerkadres gekend":
            # Split the address into parts, assuming the city is the last word
            address_parts = address.split()
            city = address_parts[-2] + ", " + address_parts[-1] if len(address_parts) > 1 else "undefined"
        else:
            city = "undefined"

        # Add the data as a tuple (including city)
        data.append((name, riziv_nr, profession, convention_state, qualification, qualification_date, address, city))

    return data




def clean_duplicates(conn):
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
    cursor = conn.cursor()
    for record in data:
        riziv_nr = record[1]
        # Check if the riziv_nr already exists
        cursor.execute("SELECT COUNT(*) FROM doctors WHERE riziv_nr = ?", (riziv_nr,))
        if cursor.fetchone()[0] == 0:  # Only insert if no existing record
            cursor.execute("""
                INSERT INTO doctors (name, riziv_nr, profession, convention_state, qualification, qualification_date, address, city)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, record)
    conn.commit()


# Function to fetch and store data
def fetch_and_store_data_thread(progress_bar, status_label, root):
    conn = initialize_database()
    current_page = 1
    is_last_page = False
    progress_bar["value"] = 0
    progress_bar["maximum"] = 400  # Start with an estimated total

    def update_gui(page, total):
        progress_bar["maximum"] = total
        progress_bar["value"] = page
        status_label.config(text=f"Fetching page {page}...")
        root.update_idletasks()

    while not is_last_page:
        html = fetch_page(current_page)
        if html:
            data = extract_data(html)
            if data:
                save_data(conn, data)
                print(f"Page {current_page}: {len(data)} entries saved.")
                update_gui(current_page, progress_bar["maximum"])
            else:
                print(f"No data found on page {current_page}. Assuming last page.")
                is_last_page = True
        else:
            print(f"Failed to fetch page {current_page}. Moving on.")
            is_last_page = True  # Stop on a complete failure

        current_page += 1
        time.sleep(1)  # Prevent overwhelming the server

    clean_duplicates(conn)

    conn.close()
    progress_bar["value"] = progress_bar["maximum"]
    status_label.config(text="Fetching Complete!")


# Function to start fetching data in a thread
def start_fetching(progress_bar, status_label, fetch_button):
    fetch_button.config(state="disabled")
    threading.Thread(target=fetch_and_store_data_thread, args=(progress_bar, status_label, root)).start()


# GUI Creation
def create_gui():
    global root
    root = tk.Tk()
    root.title("Doctor Data Scraper")
    root.geometry("900x600")  # Increased width to accommodate the new column

    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)

    fetch_button = tk.Button(
        button_frame,
        text="Fetch Data",
        command=lambda: start_fetching(progress_bar, status_label, fetch_button),
        width=20,
    )
    fetch_button.pack(side=tk.LEFT, padx=10)

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

    status_label = tk.Label(root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
    status_label.pack(side=tk.BOTTOM, fill=tk.X)

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
    # Connect to the SQLite database
    conn = sqlite3.connect("doctor_data.db")
    cursor = conn.cursor()

    # Include the "city" column in the query
    cursor.execute("""
        SELECT name, riziv_nr, profession, convention_state, qualification, qualification_date, address, city
        FROM doctors
    """)
    rows = cursor.fetchall()
    conn.close()

    # Clear existing rows in the Treeview
    tree.delete(*tree.get_children())

    # Insert new data into the Treeview
    for row in rows:
        tree.insert("", "end", values=row)



def export_to_excel():
    conn = sqlite3.connect("doctor_data.db")
    df = pd.read_sql_query("SELECT * FROM doctors", conn)
    conn.close()

    # Remove duplicate rows based on 'riziv_nr'
    df = df.drop_duplicates(subset=["riziv_nr"])

    file_path = asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
    if file_path:
        df.to_excel(file_path, index=False)
        messagebox.showinfo("Export Complete", f"Data has been exported to {file_path}")


def start_proxy():
    # Path to the Node.js script
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy", "server.js")
    
    # Run the Node.js script with hidden CMD window (Windows-specific)
    subprocess.run(
        ["node", script_path],
        creationflags=subprocess.CREATE_NO_WINDOW
    )

if __name__ == "__main__":
    # Start the proxy server in a separate thread
    threading.Thread(target=start_proxy, daemon=True).start()
    create_gui()