from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from time import sleep
from selenium.webdriver.common.by import By

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import math
import pandas as pd

import pyautogui

# Add this to your imports at the top
import questionary
import pandas as pd
import sys


def send_keystrokes(keys):
    for key in keys:
        pyautogui.press(key)

def round_dt_to_nearest_hour(dt):
    """
    Rounds a datetime object to the NEAREST hour.
    e.g., 10:29 -> 10:00
          10:30 -> 11:00
    """
    # Add 30 minutes to push it over the hour if it's at or past the halfway point
    rounded_dt = dt + timedelta(minutes=30)

    # Truncate down to the hour
    return rounded_dt.replace(minute=0, second=0, microsecond=0)

def round_dt_to_nearest_15min(dt):
    """
    Rounds a datetime object to the NEAREST 15-minute interval.
    e.g., 17:04 -> 17:00
          17:08 -> 17:15
          17:22 -> 17:15
    """
    # Add half of the interval (7.5 minutes)
    half_interval = timedelta(minutes=7, seconds=30)
    rounded_dt = dt + half_interval

    # Truncate down to the last 15-minute mark
    new_minute = (rounded_dt.minute // 15) * 15

    # Return the new datetime with seconds and microseconds cleared
    return rounded_dt.replace(minute=new_minute, second=0, microsecond=0)

def parse(start_filter, end_filter):
    # Parse the HTML data with BeautifulSoup
    filename = "Attendance Listing.html"
    with open(filename) as fp:
        soup = BeautifulSoup(fp, "lxml")

    rows = soup.find_all("tr", class_="lrow rowOdd")
    rows = rows + soup.find_all("tr", class_="lrow rowEven")
    rows = [row for row in rows if row.find("td", class_="lcell", attrs={"data-field": "Name"}).text == ""]

    visit_data = []
    for row in rows:
        time_cell = row.find("td", attrs={"data-field": "Time"})
        duration_cell = row.find("td", attrs={"data-field": "Dur"})

        if time_cell and duration_cell:
            # Date and Time parsing
            time_text = time_cell.get_text().replace('\xa0', ' ').strip()
            parts = time_text.split(',')
            date_str = parts[0].strip()
            year_str = parts[1].strip()
            time_part_raw = parts[2].strip()

            # Duration and Billing
            duration_text = duration_cell.get_text().strip()
            duration_formatted = duration_text.replace('h ', ':').replace('m', '')
            try:
                h, m = map(int, duration_formatted.split(':'))
            except:
                h = 0
                m = duration_formatted
                duration_formatted = f"{h}:{m}"
            print(duration_formatted, h,m)
            total_minutes = (int(h) * 60) + int(m)
            billed_time_mins = round(total_minutes / 15) * 15
            billed_time_hours = billed_time_mins / 60.0
            # ... inside your 'for row in rows:' loop

            time_to_parse = f"{time_part_raw[:-3]}:{time_part_raw[-3:-1]}{time_part_raw[-1].upper()}M"
            start_dt_original = datetime.strptime(time_to_parse, "%I:%M%p")

            # --- NEW: Round start time UP to nearest 15 min ---
            adjusted_start_dt = round_dt_to_nearest_hour(start_dt_original)

            # --- Calculate the *original* end time ---
            # (Using total_minutes, not billed_time_mins, as we fixed before)
            original_end_dt = start_dt_original + timedelta(minutes=total_minutes)

            # --- NEW: Round *original* end time UP to nearest 15 min ---
            adjusted_end_dt = round_dt_to_nearest_15min(original_end_dt)

            # --- Final formatting (unchanged) ---
            start_time_24h = adjusted_start_dt.strftime("%H:%M")
            end_time_24h = adjusted_end_dt.strftime("%H:%M")

            # --- Calculate original end time (for display) (unchanged) ---
            original_end_time_24h = original_end_dt.strftime("%H:%M")

            # --- Calculate net difference in minutes (unchanged) ---
            net_difference_mins = (adjusted_end_dt - original_end_dt).total_seconds() / 60

            visit_data.append({
                "date_str": date_str,
                "year": year_str,
                "start_time": start_time_24h,
                "end_time": end_time_24h,
                "original_end_time": original_end_time_24h,
                "duration_mins": total_minutes,
                "billed_time_mins": billed_time_mins,
                "billed_time_hours": billed_time_hours,
                "net_difference_mins": net_difference_mins
            })

    # --- 2. Load list into a pandas DataFrame ---
    df = pd.DataFrame(visit_data)

    # --- 3. Parse the date and set it as the index ---
    # Combine the string columns into a full date string
    full_date_str = df['date_str'] + ' ' + df['year']
    # Convert the string column into a proper datetime object
    df['date'] = pd.to_datetime(full_date_str, format='%b %d %Y')
    # Set the new 'date' column as the index
    df = df.set_index('date')
    # Clean up the original helper columns
    df = df.drop(columns=['date_str', 'year'])
    # Sort the DataFrame by the new date index
    df = df.sort_index()



    # --- 4. Filter the DataFrame by the date range ---
    filtered_df = df.loc[start_filter:end_filter]

    # Add a new column with the date formatted as MM/DD/YYYY

    # Display the original, un-filtered DataFrame
    # Display the final, filtered DataFrame
    print(f"--- Filtered for {start_filter} to {end_filter} ---")

    filtered_df['formatted_date'] = filtered_df.index.strftime('%m/%d/%Y')

    # 4. Extract the day of the week name
    filtered_df['day_of_week'] = filtered_df.index.day_name()
    filtered_df['optional'] = "ST"

    print(filtered_df)
    return filtered_df

# ... [Keep your existing methods: send_keystrokes, round_dt..., parse] ...

def fuzzy_select_timeblock(csv_path='timeblocks.csv'):
    """
    Reads the timeblocks CSV and prompts the user with a fuzzy-searchable menu.
    Returns a tuple of (start_filter, end_filter).
    """
    try:
        # Load the timeblocks data
        blocks_df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"Error: Could not find {csv_path}. Make sure the file exists.")
        sys.exit(1)

    # Create a mapping dictionary for the menu options 
    # We use the period, start, and end columns to create a clean display string 
    choices_dict = {
        f"Period {row['period']:>2}: {row['start']} to {row['end']}": (row['start'], row['end'])
        for _, row in blocks_df.iterrows()
    }

    # Generate the interactive menu
    selected_display = questionary.select(
        "Fuzzy find and select a timeblock (type to filter/search):",
        choices=list(choices_dict.keys()),
        use_indicator=True, # Shows a pointer next to the selection
    ).ask()

    # Handle user cancellation (e.g., pressing Ctrl+C)
    if selected_display is None:
        print("\nSelection cancelled. Exiting.")
        sys.exit(0)

    # Return the (start, end) tuple associated with the chosen string
    return choices_dict[selected_display]

if __name__ == "__main__":
    # Call the new fuzzy finder instead of using hardcoded variables
    start_filter, end_filter = fuzzy_select_timeblock('timeblocks.csv')
    
    print(f"\nProceeding with date range: {start_filter} to {end_filter}...\n")
    
    df = parse(start_filter, end_filter)
    
    # Calculate stats
    billed_hours = df["billed_time_hours"].sum()
    pay = 17.5
    raw_comp = billed_hours * pay
    estimate_net = raw_comp * 0.7
    
    print(f"\nStats:------- \n\tTotal Billed Hours: {billed_hours}hrs\n\tRaw Comp [${raw_comp:.2f}] | Estimate Net [${estimate_net:.2f}]")
    
    # Save to CSV
    text = f"{start_filter}_{end_filter}.csv"
    df.to_csv(text)
    print(f"\nSaved export to {text}")
