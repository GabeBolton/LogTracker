import yaml
import datetime
from pathlib import Path
import argparse
import csv
import sys

def get_log_dict(path="log.yaml"):
    log_dict = yaml.safe_load(Path(path).read_text())
    return log_dict

def get_mins(log_dict):
    mins_dict = {}
    for log in log_dict['logs']:
        date = datetime.datetime.strptime(log['date'], '%d/%m/%Y').date()
        if date in mins_dict.keys():
            mins_dict[date] += log['end'] - log['start']
        else:
            mins_dict[date] = log['end'] - log['start']

    return mins_dict

def get_hours_dict(mins_dict):
    hours_dict = {}
    for date, mins in mins_dict.items():
        hours_dict[date] = mins/60
    return hours_dict

def get_weekly_hours(mins_dict, weekday_start=1):
    weekly_hours = {}
    for date, mins in mins_dict.items():
        key = (date.year, date.isocalendar().week)
        if key in weekly_hours.keys():
            weekly_hours[key] += mins/60
        else:
            weekly_hours[key] = mins/60
    return weekly_hours

# def get_payperiod_key(date):
#     # payperiod start day
#     start_date = datetime.date(year=2024, month=1, day=22)
#     end_date = start_date + datetime.timedelta(days=13)

#     day_delta = (date-start_date).days 
#     period_delta = int((day_delta - day_delta % 14)/14)

#     return end_date+period_delta * datetime.timedelta(days=14)

# def get_payperiod_hours(mins_dict):
#     payperiod_hours = {}
#     for date, mins in mins_dict.items():
#         key = get_payperiod_key(date)
#         if key in payperiod_hours.keys():
#             payperiod_hours[key] += mins/60
#         else:
#             payperiod_hours[key] = mins/60
#     return payperiod_hours

def get_fy_key(date):
    start_date = datetime.date(year=2023, month=7, day=1)
    end_date = datetime.date(year=2023, month=6, day=30)
    
    day_delta = (date-start_date).days 
    year_delta = int((day_delta - day_delta % 365)/365)

    return end_date+ datetime.timedelta(years=1*year_delta)

def get_fy_hours(payperiod_hours):

    for date, mins in mins_dict.items():
        key = get_payperiod_key(date)
        if key in payperiod_hours.keys():
            payperiod_hours[key] += mins/60
        else:
            payperiod_hours[key] = mins/60
    return payperiod_hours

def get_fy_hours(weekly_hours, weekday_start=1):
    fy_hours = {}
    for date, mins in mins_dict.items():
        key = (date.year, date.isocalendar().week)
        if key in weekly_hours.keys():
            weekly_hours[key] += mins/60
        else:
            weekly_hours[key] = mins/60
    return weekly_hours

def get_payperiod_type_and_start(log_dict):
    payperiod = log_dict.get('payperiod', {})
    # Support both old and new formats
    if isinstance(payperiod, dict):
        payperiod_type = payperiod.get('type', 'biweekly').lower()
        period_start_str = payperiod.get('start')
        if period_start_str:
            period_start = datetime.datetime.strptime(period_start_str, '%d/%m/%Y').date()
        elif payperiod_type == 'monthly':
            # Default to first of current year if not specified
            period_start = datetime.date(datetime.date.today().year, 1, 1)
        else:
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
        period_delta = int(day_delta // 14)
        period_start_date = period_start + datetime.timedelta(days=period_delta * 14)
        return period_start_date
    else:
        raise ValueError(f"Unknown payperiod type: {payperiod_type}")

def get_payperiod_hours(mins_dict, payperiod_type, period_start):
    payperiod_hours = {}
    for date, mins in mins_dict.items():
        key = get_payperiod_key(date, payperiod_type, period_start)
        if key in payperiod_hours:
            payperiod_hours[key] += mins / 60
        else:
            payperiod_hours[key] = mins / 60
    return payperiod_hours

def output_csv_basic(log_dict):
    project_codes = log_dict.get('project_codes', {})
    writer = csv.writer(sys.stdout)
    writer.writerow(['project', 'date', 'hours'])
    for log in log_dict['logs']:
        project_code = log.get('project', '')
        if project_code not in project_codes:
            raise ValueError(f"Project code '{project_code}' not found in project_codes mapping.")
        project_label = project_codes[project_code]
        date = log['date']
        try:
            start = float(log['start'])
            end = float(log['end'])
            hours = (end - start) / 60
        except Exception:
            hours = ''
        writer.writerow([project_label, date, hours])

def output_csv_detailed(log_dict):
    project_codes = log_dict.get('project_codes', {})
    # Collect all possible keys
    all_keys = set()
    for log in log_dict['logs']:
        all_keys.update(log.keys())
    all_keys = sorted(all_keys)
    if 'hours' not in all_keys:
        all_keys.append('hours')
    if 'project_label' not in all_keys:
        all_keys.insert(0, 'project_label')
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
        except Exception:
            row['hours'] = ''
        writer.writerow(row)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('path', help='path to log file')
    parser.add_argument('-d', '--daily_log', help='print hours from each minutes dict', action='store_true')
    parser.add_argument('--csv-basic', help='output basic CSV (project, date, hours)', action='store_true')
    parser.add_argument('--csv-detailed', help='output detailed CSV (all fields)', action='store_true')
    args = parser.parse_args()

    log_dict = get_log_dict(args.path)
    mins_dict = get_mins(log_dict)
    weekly_hours = get_weekly_hours(mins_dict=mins_dict)

    # Get payperiod type and start from YAML
    payperiod_type, period_start = get_payperiod_type_and_start(log_dict)
    payperiod_hours = get_payperiod_hours(mins_dict=mins_dict, payperiod_type=payperiod_type, period_start=period_start)

    if args.csv_basic:
        output_csv_basic(log_dict)
        sys.exit(0)

    if args.csv_detailed:
        output_csv_detailed(log_dict)
        sys.exit(0)

    if args.daily_log:
        for day, minutes in mins_dict.items():
            print(day.strftime('%Y/%m/%d')+': {:02d}:{:02d}'.format(*divmod(minutes, 60)))

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

    pass