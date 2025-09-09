# This script compares two Excel files and creates a new file containing
# the rows that are unique to each of the original files.
# It uses the pandas library for efficient data manipulation.

# Before running, make sure you have the necessary libraries installed:
# pip install pandas openpyxl

import pandas as pd
import os
import tkinter as tk
from tkinter import filedialog

def compare_excel_files(file1_path, file2_path, output_path, key_column1=None, key_column2=None, comparison_cols=None):
    print("Starting comparison...")

    if not os.path.exists(file1_path):
        print(f"Error: The file {file1_path} was not found.")
        return
    if not os.path.exists(file2_path):
        print(f"Error: The file {file2_path} was not found.")
        return

    try:
        df1 = pd.read_excel(file1_path)
        df2 = pd.read_excel(file2_path)
        df1_cols = list(df1.columns)
        df2_cols = list(df2.columns)
        common_cols = list(set(df1_cols).intersection(df2_cols))
        if comparison_cols:
            comparison_on_list = comparison_cols
            print(f"Comparing using the specified columns: {', '.join(comparison_on_list)}")
        elif key_column1 and key_column2:
            comparison_on_list = [col for col in common_cols if col != key_column1 and col != key_column2]
            print(f"Comparing using all columns except the specified key columns: {', '.join(comparison_on_list)}")
        else:
            comparison_on_list = common_cols
            print("Comparing all common columns in each row.")
        if not all(col in df1_cols for col in comparison_on_list) or not all(col in df2_cols for col in comparison_on_list):
            print("Error: The specified comparison columns do not exist in both files.")
            return
        merged_df = pd.merge(df1, df2, on=comparison_on_list, how='outer', indicator=True)
        diff_df = merged_df[merged_df['_merge'] != 'both']
        diff_df['Source File'] = diff_df['_merge'].apply(lambda x: file1_path if x == 'left_only' else file2_path)
        diff_df = diff_df.drop(columns=['_merge'])
        diff_df.to_excel(output_path, index=False)
        print(f"\nComparison complete! The differences have been saved to '{output_path}'.")
        print(f"Found {len(diff_df)} differing rows.")
    except FileNotFoundError:
        print("Error: One of the files was not found. Please check the file paths.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    print("Select the first Excel file.")
    input_file_1 = filedialog.askopenfilename(title="Select first Excel file", filetypes=[("Excel files", "*.xlsx;*.xls")])
    print("Select the second Excel file.")
    input_file_2 = filedialog.askopenfilename(title="Select second Excel file", filetypes=[("Excel files", "*.xlsx;*.xls")])
    print("Select location to save the differences file.")
    output_diff_file = filedialog.asksaveasfilename(title="Save differences file as", defaultextension=".xlsx", filetypes=[("Excel files", "*.xlsx")])
    compare_excel_files(input_file_1, input_file_2, output_diff_file, comparison_cols=["name"])

