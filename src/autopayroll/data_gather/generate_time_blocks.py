import csv
from datetime import datetime, timedelta

class TimeBlockGenerator:
    """Generates consecutive two-week time blocks and saves them to a CSV."""

    def __init__(self, timeblock_path: str = "timeblocks.csv"):
        """Initialize the generator with a target CSV timeblock_path."""
        self.timeblock_path = timeblock_path

    def get_next_n_periods(self, start_filter: str, end_filter: str, n: int) -> list[dict]:
        """
        Calculates the next 'n' two-week periods after the given start/end dates.
        
        @Args:
            start_filter (str): The starting date in 'YYYY-MM-DD' format.
            end_filter (str): The ending date in 'YYYY-MM-DD' format.
            n (int): The number of future periods to generate.
            
        @Returns:
            list[dict]: A list of dictionaries containing the period data.
        """
        periods = []
        start_dt = datetime.strptime(start_filter, '%Y-%m-%d')
        end_dt = datetime.strptime(end_filter, '%Y-%m-%d')
        
        for i in range(1, n + 1):
            next_start = start_dt + timedelta(weeks=2 * i)
            next_end = end_dt + timedelta(weeks=2 * i)
            
            periods.append({
                'period': i,
                'start': next_start.strftime('%Y-%m-%d'),
                'end': next_end.strftime('%Y-%m-%d'),
            })
            
        return periods

    def export_to_csv(self, periods: list[dict]) -> None:
        """Saves a list of period dictionaries to the initialized CSV file."""
        with open(self.timeblock_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['period', 'start', 'end'])
            writer.writeheader()
            # writerows is cleaner and faster than looping through writerow
            writer.writerows(periods)
            
        print(f"Successfully saved {len(periods)} periods to '{self.timeblock_path}'.")

    def run(self, start_filter: str, end_filter: str, n: int) -> list[dict]:
        """Convenience method to generate periods and save them directly."""
        periods = self.get_next_n_periods(start_filter, end_filter, n)
        self.export_to_csv(periods)
        return periods


if __name__ == "__main__":
    # Example usage:
    generator = TimeBlockGenerator(timeblock_path="timeblocks.csv")
    generator.run(start_filter="2026-03-22", end_filter="2026-04-04", n=10)
