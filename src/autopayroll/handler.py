import sys
import pandas as pd
from pathlib import Path
import subprocess
import questionary

# def run_script(script_name):
#     """Executes a Python script using subprocess."""
#     print(f"\n{'='*40}")
#     print(f"Executing: {script_name}")
#     print(f"{'='*40}\n")
#     try:
#         # sys.executable ensures we use the same Python environment
#         subprocess.run([sys.executable, script_name], check=True)
#     except subprocess.CalledProcessError as e:
#         print(f"\nError: {script_name} exited with status {e.returncode}")
#     except FileNotFoundError:
#         print(f"\nError: Could not find {script_name}")
#     print(f"\n{'='*40}")
#     print(f"Finished: {script_name}")
#     print(f"{'='*40}\n")
#

class Handler:
    def __init__ (self, timeblocks_path):
        self.timeblocks_path = timeblocks_path
        return 
    def select_timeblock(self):
        """
        Reads the timeblocks CSV and prompts the user with a fuzzy-searchable menu.
        Returns a tuple of (start_filter, end_filter).
        """
        try:
            blocks_df = pd.read_csv(self.timeblocks_path)
        except FileNotFoundError:
            print(f"Error: Could not find {self.timeblocks_path}. Make sure the file exists.")
            sys.exit(1)

        # Create a mapping dictionary for the menu options 
        choices_dict = {
            f"Period {row['period']:>2}: {row['start']} to {row['end']}": (row['start'], row['end'])
            for _, row in blocks_df.iterrows()
        }

        # Generate the interactive menu
        selected_display = questionary.select(
            "Fuzzy find and select a timeblock (type to filter/search)  :",
            choices=list(choices_dict.keys()),
            use_indicator=True, # Shows a pointer next to the selection
        ).ask()

        # Handle user cancellation (e.g., pressing Ctrl+C)
        if selected_display is None:
            print("\nSelection cancelled. Exiting.")
            sys.exit(0)

        # Return the (start, end) tuple associated with the chosen string
        return choices_dict[selected_display]

