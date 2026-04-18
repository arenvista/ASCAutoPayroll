import sys
import subprocess
import questionary

def run_script(script_name):
    """Executes a Python script using subprocess."""
    print(f"\n{'='*40}")
    print(f"Executing: {script_name}")
    print(f"{'='*40}\n")
    try:
        # sys.executable ensures we use the same Python environment
        subprocess.run([sys.executable, script_name], check=True)
    except subprocess.CalledProcessError as e:
        print(f"\nError: {script_name} exited with status {e.returncode}")
    except FileNotFoundError:
        print(f"\nError: Could not find {script_name}")
    print(f"\n{'='*40}")
    print(f"Finished: {script_name}")
    print(f"{'='*40}\n")

def main():
    """Main menu loop."""
    scripts = {
        "1. Generate Time Blocks (generate_time_blocks.py)": "generate_time_blocks.py",
        "2. Pull Timesheet HTML (pull_sheet.py)": "pull_sheet.py",
        "3. Parse HTML to CSV (parser.py)": "parser.py",
        "4. Auto-Input Timesheet (inputer.py)": "inputer.py",
        "5. Exit": None
    }

    while True:
        choice = questionary.select(
            "What would you like to do?",
            choices=list(scripts.keys()),
            use_indicator=True
        ).ask()

        # Handle Ctrl+C or Exit
        if choice is None or choice == "5. Exit":
            print("\nExiting. Goodbye!")
            sys.exit(0)

        # Run the selected script
        script_to_run = scripts[choice]
        run_script(script_to_run)

if __name__ == "__main__":
    main()
