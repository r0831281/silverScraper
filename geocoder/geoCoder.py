from colorama import Fore, Style, init
init(autoreset=True)
from tqdm import tqdm
import pandas as pd
import time
import os
import json
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import tkinter as tk
from tkinter import filedialog

# === Settings ===
root = tk.Tk()
root.withdraw()

INPUT_FILE = filedialog.askopenfilename(title="Select input CSV file")
if not INPUT_FILE:
    raise Exception("No input file selected.")


# Output as XLSX
OUTPUT_FILE = filedialog.asksaveasfilename(title="Save output XLSX file as", defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
if not OUTPUT_FILE:
    raise Exception("No output file selected.")

CACHE_FILE = filedialog.asksaveasfilename(title="Select cache JSON file", defaultextension=".json", filetypes=[("JSON files", "*.json")])
if not CACHE_FILE:
    raise Exception("No cache file selected.")

# === Load Data ===
try:
    if INPUT_FILE.lower().endswith('.csv'):
        df = pd.read_csv(INPUT_FILE)
    elif INPUT_FILE.lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(INPUT_FILE)
    else:
        raise Exception(f"Unsupported file type: {INPUT_FILE}")
    if df.empty:
        raise Exception("The selected file is empty.")
except Exception as e:
    print(f"Error loading input file: {e}")
    raise

# === Load or create cache ===
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}
    # Create the cache file immediately if it doesn't exist
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

# === Setup Geolocator ===
geolocator = Nominatim(user_agent="doctor-mapper", timeout=15)
# Increase delay to 3 seconds to avoid rate limiting
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=3)

# === Function with caching ===

# Enhanced geocode: try address, then city if address fails
def cached_geocode_row(row):
    address = str(row['address'])
    address_query = f"{address}, Belgium"

    # Try address cache first
    if address_query in cache:
        tqdm.write(f"{Fore.CYAN}Address found in cache:{Style.RESET_ALL} {address_query} -> {cache[address_query]}")
        return cache[address_query]

    # Try geocoding address (with retries)
    result = (None, None)
    for attempt in range(3):
        try:
            location = geocode(address_query)
            if location:
                result = (location.latitude, location.longitude)
                tqdm.write(f"{Fore.GREEN}Address geocoded{Style.RESET_ALL}: {address_query} -> {result}")
                break
        except Exception as e:
            tqdm.write(f"{Fore.YELLOW}Attempt {attempt+1}/3{Style.RESET_ALL}: Error geocoding {address_query}: {e}")
            time.sleep(2)

    # If address fails, try city
    if result == (None, None) and 'city' in row and pd.notnull(row['city']):
        city = str(row['city'])
        city_query = f"{city}, Belgium"
        city_key = f"city:{city_query}"

        # Try city cache first
        if city_key in cache:
            tqdm.write(f"{Fore.CYAN}Address not found, found city in cache{Style.RESET_ALL}: {city_query} -> {cache[city_key]}")
            result = cache[city_key]
        else:
            for attempt in range(3):
                try:
                    location_city = geocode(city_query)
                    if location_city:
                        result = (location_city.latitude, location_city.longitude)
                        tqdm.write(f"{Fore.GREEN}Address not found, found by geocoding city{Style.RESET_ALL}: {city_query} -> {result}")
                        break
                except Exception as e:
                    tqdm.write(f"{Fore.YELLOW}Attempt {attempt+1}/3{Style.RESET_ALL}: Error geocoding city {city_query}: {e}")
                    time.sleep(1)
            cache[city_key] = result

    if result == (None, None):
        tqdm.write(f"{Fore.RED}Geocoding failed for{Style.RESET_ALL}: {address_query}{f' / {city_query}' if 'city' in row and pd.notnull(row['city']) else ''}")
    # Cache the result for the address
    cache[address_query] = result
    return result

# === Geocode addresses ===
if 'address' not in df.columns:
    raise Exception(f"The input file must contain a column named 'address'. Found columns: {list(df.columns)}\n")
if 'city' not in df.columns:
    print("Warning: No 'city' column found. Will only geocode using 'address'.")

# Progress bar for geocoding
results = []
for _, row in tqdm(df.iterrows(), total=len(df), desc="Geocoding"):
    results.append(cached_geocode_row(row))
df[["lat", "lon"]] = results

# === Save cache for next run ===
with open(CACHE_FILE, "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)


# === Save final dataset as XLSX or CSV ===
file_ext = os.path.splitext(OUTPUT_FILE)[1].lower()
if file_ext in [".xlsx", ".xls"]:
    df.to_excel(OUTPUT_FILE, index=False)
    print(f"{Fore.GREEN}✅ Geocoding complete. Saved to {OUTPUT_FILE} (Excel format){Style.RESET_ALL}")
elif file_ext == ".csv":
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"{Fore.GREEN}✅ Geocoding complete. Saved to {OUTPUT_FILE} (CSV, UTF-8 encoding){Style.RESET_ALL}")
else:
    raise Exception(f"Unsupported output file type: {OUTPUT_FILE}")
