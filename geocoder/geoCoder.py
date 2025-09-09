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

# === Setup Geolocator ===
geolocator = Nominatim(user_agent="doctor-mapper", timeout=10)
# Increase delay to 3 seconds to avoid rate limiting
geocode = RateLimiter(geolocator.geocode, min_delay_seconds=3)

# === Function with caching ===

# Enhanced geocode: try address, then city if address fails
def cached_geocode_row(row):
    address = str(row['address'])
    city = str(row['city']) if 'city' in row and pd.notnull(row['city']) else None
    if city and (city.strip().lower() == 'undefined' or city.strip() == ''):
        city = None
    if address in cache:
        return cache[address]
    # Retry logic for address
    result = (None, None)
    for attempt in range(3):
        try:
            location = geocode(address)
            if location:
                result = (location.latitude, location.longitude)
                break
        except Exception as e:
            print(f"Attempt {attempt+1}/3: Error geocoding {address}: {e}")
            time.sleep(2)
    # If address fails, try city with retry logic
    if result == (None, None) and city:
        print(f"Address not found, trying city: {city}")
        if city in cache:
            result = cache[city]
        else:
            for attempt in range(3):
                try:
                    location_city = geocode(city)
                    if location_city:
                        result = (location_city.latitude, location_city.longitude)
                        break
                except Exception as e:
                    print(f"Attempt {attempt+1}/3: Error geocoding city {city}: {e}")
                    time.sleep(2)
            cache[city] = result
    cache[address] = result
    return result

# === Geocode addresses ===
if 'address' not in df.columns:
    raise Exception(f"The input file must contain a column named 'address'. Found columns: {list(df.columns)}")
if 'city' not in df.columns:
    print("Warning: No 'city' column found. Will only geocode using 'address'.")
df[["lat", "lon"]] = df.apply(lambda row: pd.Series(cached_geocode_row(row)), axis=1)

# === Save cache for next run ===
with open(CACHE_FILE, "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)


# === Save final dataset as XLSX ===
df.to_excel(OUTPUT_FILE, index=False)

print(f"✅ Geocoding complete. Saved to {OUTPUT_FILE}")
