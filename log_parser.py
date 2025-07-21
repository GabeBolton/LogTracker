import yaml
import datetime
from pathlib import Path
import argparse
import csv
import sys
import holidays # Added for holiday tracking

def get_log_dict(path="log.yaml"):
    log_dict = yaml.safe_load(Path(path).read_text())
    return log_dict

def get_mins(log_dict):
    mins_dict = {}
    for log in log_dict['logs']:
        date = datetime.datetime.strptime(log['date'], '%d/%m/%Y').date()
        # The .get() method is slightly safer here
        mins_dict[date] = mins_dict.get(date, 0) + (log['end'] - log['start'])
    return mins_dict

def get_weekly_hours(mins_dict):
    weekly_hours = {}
    for date, mins in mins_dict.items():
        key = (date.year, date.isocalendar().week)
        weekly_hours[key] = weekly_hours.get(key, 0) + mins / 60
    return weekly_hours

def get_payperiod_type_and_start(log_dict):
    payperiod = log_dict.get('payperiod', {})
    if isinstance(payperiod, dict):
        payperiod_type = payperiod.get('type', 'biweekly').lower()
        period_start_str = payperiod.get('start')
        if period_start_str:
            period_start = datetime.datetime.strptime(period_start_str, '%d/%m/%Y').date()
        else:
            # Default to a known date if not specified
            period_start = datetime.date(2024, 1, 22)
    else:
        payperiod_type = payperiod.lower() if isinstance(payperiod, str) else 'biweekly'
        period_start = datetime.date(2024, 1, 22)
    return payperiod_type, period_start

def get_payperiod_key(date, payperiod_type, period_start):
    if payperiod_type == 'monthly':
        return (date.year, date.month)
    elif payperiod_type == 'biweekly':
        day_delta = (date - period_start).days
        period_delta = day_delta // 14
        period_start_date = period_start + datetime.timedelta(days=period_delta * 14)
        return period_start_date
    else:
        raise ValueError(f"Unknown payperiod type: {payperiod_type}")

def get_payperiod_hours(mins_dict, payperiod_type, period_start):
    payperiod_hours = {}
    for date, mins in mins_dict.items():
        key = get_payperiod_key(date, payperiod_type, period_start)
        payperiod_hours[key] = payperiod_hours.get(key, 0) + mins / 60
    return payperiod_hours

# --- Calculate Flex Time ---
def get_flex_time(log_dict, mins_dict):
    """Calculates flex time based on logged hours, expected hours, holidays, and vacation."""
    config = log_dict.get('config', {})
    hours_per_week = config.get('hours_per_week', 37.5) # Default to 37.5 if not set
    region = config.get('holiday_region')

    # Initialize holidays for the specified region
    regional_holidays = holidays.country_holidays(region) if region else {}

    # Parse vacation periods
    vacation_periods = []
    for v in log_dict.get('vacation', []):
        start = datetime.datetime.strptime(v['start'], '%d/%m/%Y').date()
        end = datetime.datetime.strptime(v['end'], '%d/%m/%Y').date()
        vacation_periods.append((start, end))

    total_logged_hours = sum(mins_dict.values()) / 60

    if not mins_dict:
        return 0

    # Determine the date range from the logs
    first_day = min(mins_dict.keys())
    last_day = datetime.date.today() # Calculate expected hours up to today

    expected_hours = 0
    current_day = first_day
    while current_day <= last_day:
        is_on_vacation = any(start <= current_day <= end for start, end in vacation_periods)

        # A day counts towards expected hours if it's a weekday, not a holiday, and not vacation
        if current_day.weekday() < 5 and current_day not in regional_holidays and not is_on_vacation:
            expected_hours += hours_per_week / 5

        current_day += datetime.timedelta(days=1)

    return total_logged_hours - expected_hours

def output_csv_basic(log_dict):
    project_codes = log_dict.get('project_codes', {})
    writer = csv.writer(sys.stdout)
    writer.writerow(['project', 'date', 'hours'])
    for log in log_dict['logs']:
        project_code = log.get('project', '')
        if project_code not in project_codes:
            raise ValueError(f"Project code '{project_code}' not found in project_codes mapping.")
        project_label = project_codes[project_code]
        try:
            hours = (float(log['end']) - float(log['start'])) / 60
        except (ValueError, KeyError):
            hours = ''
        writer.writerow([project_label, log['date'], hours])

def output_csv_detailed(log_dict):
    project_codes = log_dict.get('project_codes', {})
    all_keys = sorted({k for log in log_dict['logs'] for k in log.keys()})
    if 'hours' not in all_keys: all_keys.append('hours')
    if 'project_label' not in all_keys: all_keys.insert(0, 'project_label')

    writer = csv.DictWriter(sys.stdout, fieldnames=all_keys)
    writer.writeheader()
    for log in log_dict['logs']:
        row = {k: log.get(k, '') for k in all_keys}
        project_code = log.get('project', '')
        if project_code not in project_codes:
            raise ValueError(f"Project code '{project_code}' not found in project_codes mapping.")
        row['project_label'] = project_codes[project_code]
        try:
            row['hours'] = (float(log['end']) - float(log['start'])) / 60
        except (ValueError, KeyError):
            row['hours'] = ''
        writer.writerow(row)

def assert_all_logs_have_project(log_dict):
    for i, log in enumerate(log_dict['logs']):
        if 'project' not in log or not log['project']:
            raise ValueError(f"Log entry at index {i} and date {log.get('date', 'unknown')} is missing a 'project' field.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('path', help='path to log file')
    parser.add_argument('-d', '--daily_log', help='print hours from each minutes dict', action='store_true')
    parser.add_argument('--csv-basic', help='output basic CSV (project, date, hours)', action='store_true')
    parser.add_argument('--csv-detailed', help='output detailed CSV (all fields)', action='store_true')
    args = parser.parse_args()

    log_dict = get_log_dict(args.path)
    assert_all_logs_have_project(log_dict)
    mins_dict = get_mins(log_dict)
    weekly_hours = get_weekly_hours(mins_dict=mins_dict)

    payperiod_type, period_start = get_payperiod_type_and_start(log_dict)
    payperiod_hours = get_payperiod_hours(mins_dict=mins_dict, payperiod_type=payperiod_type, period_start=period_start)

    if args.csv_basic:
        output_csv_basic(log_dict)
        sys.exit(0)

    if args.csv_detailed:
        output_csv_detailed(log_dict)
        sys.exit(0)

    if args.daily_log:
        for day, minutes in sorted(mins_dict.items()):
            print(f"{day.strftime('%Y/%m/%d')}: {minutes // 60:02d}:{minutes % 60:02d}")

    # --- This is your original printout, untouched ---
    today = datetime.datetime.now().date()
    try:
        print(f"hours today: {mins_dict[today]/60:.2f}")
    except KeyError:
        print('no hours today')
    
    try:
        print(f"hours this week: {weekly_hours[(today.year, today.isocalendar().week)]:.2f}")
    except KeyError:
        print('no hours this week')

    try:
        print(f"hours last week: {weekly_hours[(today.year, today.isocalendar().week-1)]:.2f}")
    except KeyError:
        print('no hours last week')

    # Print hours this payperiod
    try:
        this_period_key = get_payperiod_key(today, payperiod_type, period_start)
        print(f"hours this payperiod: {payperiod_hours[this_period_key]:.2f}")
    except KeyError:
        print('no hours this payperiod')

    # Print hours last payperiod
    try:
        if payperiod_type == 'monthly':
            last_month = today.month - 1 if today.month > 1 else 12
            last_year = today.year if today.month > 1 else today.year - 1
            last_period_key = (last_year, last_month)
        else:  # biweekly
            last_period_key = get_payperiod_key(today - datetime.timedelta(days=14), payperiod_type, period_start)
        print(f"hours last payperiod: {payperiod_hours[last_period_key]:.2f}")
    except KeyError:
        print('no hours last payperiod')

    print(f"total hours: {sum(weekly_hours.values()):.2f}")
    # --- End of original printout ---

    # --- New flex time calculation and printout, added to the end ---
    if 'config' in log_dict:
        flex_hours = get_flex_time(log_dict, mins_dict)
        print(f"flex time balance: {flex_hours:.2f}")

    pass