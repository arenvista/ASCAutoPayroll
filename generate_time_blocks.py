def get_next_N_period(start_filter, end_filter, N, filename):
    """
    Takes the start and end dates (YYYY-MM-DD) as strings,
    generates the next (N) two-week periods after the given period,
    and saves them to a CSV file (filename).
    Each CSV row contains the period number, start date, and end date.
    """
    import csv
    from datetime import datetime, timedelta

    periods = []
    start_dt = datetime.strptime(start_filter, '%Y-%m-%d')
    end_dt = datetime.strptime(end_filter, '%Y-%m-%d')
    for i in range(1, N+1):
        next_start = start_dt + timedelta(weeks=2*i)
        next_end = end_dt + timedelta(weeks=2*i)
        periods.append({
            'period': i,
            'start': next_start.strftime('%Y-%m-%d'),
            'end': next_end.strftime('%Y-%m-%d'),
        })
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['period', 'start', 'end'])
        writer.writeheader()
        for period in periods:
            writer.writerow(period)

# Example usage:
print(get_next_N_period("2026-03-22", "2026-04-04", 10, "timeblocks.csv"))
