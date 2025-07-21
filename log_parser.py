import yaml
import datetime
from pathlib import Path
import argparse
import csv
import sys
import holidays

class WorkLog:
    """
    An object-oriented class to parse, analyze, and report on work logs.
    """
    def __init__(self, file_path):
        """Initializes the WorkLog object by loading and parsing the YAML file."""
        self._raw_dict = yaml.safe_load(Path(file_path).read_text())
        
        self.logs = self._raw_dict.get('logs', [])
        self.config = self._raw_dict.get('config', {})
        self.project_codes = self._raw_dict.get('project_codes', {})
        self.payperiod_config = self._raw_dict.get('payperiod', {})
        self.vacation_config = self._raw_dict.get('vacation', [])

        # Caching for per-project data and totals
        self._minutes_per_day_by_project = None
        self._weekly_hours_by_project = None
        self._pay_period_hours_by_project = None
        self._flex_time = None

    @property
    def minutes_per_day_by_project(self):
        """
        Calculates minutes per day, broken down by project.
        Logs without a project are grouped under 'Unassigned'.
        """
        if self._minutes_per_day_by_project is None:
            data = {}
            for log in self.logs:
                date = datetime.datetime.strptime(log['date'], '%d/%m/%Y').date()
                # If project is missing or empty, default to "Unassigned"
                project = log.get('project') or "Unassigned"
                duration = log.get('end', 0) - log.get('start', 0)
                
                if date not in data:
                    data[date] = {}
                data[date][project] = data[date].get(project, 0) + duration
            self._minutes_per_day_by_project = data
        return self._minutes_per_day_by_project

    @property
    def weekly_hours_by_project(self):
        """Calculates hours per week, broken down by project."""
        if self._weekly_hours_by_project is None:
            data = {}
            for date, projects in self.minutes_per_day_by_project.items():
                key = (date.year, date.isocalendar().week)
                if key not in data:
                    data[key] = {}
                for project, mins in projects.items():
                    data[key][project] = data[key].get(project, 0) + (mins / 60)
            self._weekly_hours_by_project = data
        return self._weekly_hours_by_project

    @property
    def pay_period_hours_by_project(self):
        """Calculates hours per pay period, broken down by project."""
        if self._pay_period_hours_by_project is None:
            data = {}
            payperiod_type, start_date = self._get_payperiod_type_and_start()
            for date, projects in self.minutes_per_day_by_project.items():
                key = self._get_payperiod_key(date, payperiod_type, start_date)
                if key not in data:
                    data[key] = {}
                for project, mins in projects.items():
                    data[key][project] = data[key].get(project, 0) + (mins / 60)
            self._pay_period_hours_by_project = data
        return self._pay_period_hours_by_project

    @property
    def flex_time(self):
        """Calculates and caches the flex time balance."""
        if self._flex_time is None:
            total_logged_hours = sum(sum(p.values()) for p in self.minutes_per_day_by_project.values()) / 60
            if not self.minutes_per_day_by_project:
                self._flex_time = 0
                return self._flex_time

            hours_per_week = self.config.get('hours_per_week', 37.5)
            region = self.config.get('holiday_region')
            regional_holidays = holidays.country_holidays(region) if region else {}
            
            vacation_periods = [(datetime.datetime.strptime(v['start'], '%d/%m/%Y').date(), datetime.datetime.strptime(v['end'], '%d/%m/%Y').date()) for v in self.vacation_config]

            first_day = min(self.minutes_per_day_by_project.keys())
            last_day = datetime.date.today()
            
            expected_hours = 0
            current_day = first_day
            while current_day <= last_day:
                is_on_vacation = any(start <= current_day <= end for start, end in vacation_periods)
                if current_day.weekday() < 5 and current_day not in regional_holidays and not is_on_vacation:
                    expected_hours += hours_per_week / 5
                current_day += datetime.timedelta(days=1)
            
            self._flex_time = total_logged_hours - expected_hours
        return self._flex_time

    def _get_payperiod_type_and_start(self):
        payperiod_type = self.payperiod_config.get('type', 'biweekly').lower()
        start_str = self.payperiod_config.get('start')
        start_date = datetime.datetime.strptime(start_str, '%d/%m/%Y').date() if start_str else datetime.date(2024, 1, 22)
        return payperiod_type, start_date

    def _get_payperiod_key(self, date, payperiod_type, period_start):
        if payperiod_type == 'monthly': return (date.year, date.month)
        day_delta = (date - period_start).days
        period_delta = day_delta // 14
        return period_start + datetime.timedelta(days=period_delta * 14)
    
    def display_summary(self):
        """Prints a full summary report to the console in a formatted table."""
        today = datetime.date.today()
        
        # --- 1. Define Headers and Rows ---
        # Dynamically get all projects that have logged time
        all_projects_in_logs = set()
        for weekly_data in self.weekly_hours_by_project.values():
            all_projects_in_logs.update(weekly_data.keys())
        project_headers = sorted(list(all_projects_in_logs))
        
        headers = ["Period"] + project_headers + ["Total"]
        
        table_rows = []

        # --- 2. Gather Data for Each Row ---
        # Today
        today_data = self.minutes_per_day_by_project.get(today, {})
        table_rows.append(self._create_table_row("Today", today_data, project_headers, is_minutes=True))

        # This Week
        week_key = (today.year, today.isocalendar().week)
        this_week_data = self.weekly_hours_by_project.get(week_key, {})
        table_rows.append(self._create_table_row("This Week", this_week_data, project_headers))

        # Last Week
        last_week_date = today - datetime.timedelta(weeks=1)
        last_week_key = (last_week_date.year, last_week_date.isocalendar().week)
        last_week_data = self.weekly_hours_by_project.get(last_week_key, {})
        table_rows.append(self._create_table_row("Last Week", last_week_data, project_headers))

        # Pay Periods
        payperiod_type, start_date = self._get_payperiod_type_and_start()
        this_pp_key = self._get_payperiod_key(today, payperiod_type, start_date)
        this_pp_data = self.pay_period_hours_by_project.get(this_pp_key, {})
        table_rows.append(self._create_table_row("This Pay Period", this_pp_data, project_headers))
        
        # Grand Total
        total_data = {}
        for weekly_data in self.weekly_hours_by_project.values():
            for project, hours in weekly_data.items():
                total_data[project] = total_data.get(project, 0) + hours
        table_rows.append(self._create_table_row("Grand Total", total_data, project_headers))

        # --- 3. Format and Print Table ---
        self._print_table(headers, table_rows)
        
        # --- 4. Print Additional Info ---
        print("\n## Totals & Balances ##")
        if self.config:
            print(f"Flex Time Balance: {self.flex_time:.2f} hours")

    def _create_table_row(self, period_name, data_dict, project_headers, is_minutes=False):
        """Helper to build a single row dictionary for the table."""
        row = {"Period": period_name}
        total = 0
        for p_header in project_headers:
            val = data_dict.get(p_header, 0)
            # Use project code itself as label if not in project_codes, e.g. for "Unassigned"
            label = self.project_codes.get(p_header, p_header)
            hours = val / 60 if is_minutes else val
            row[label] = f"{hours:.2f}"
            total += hours
        row["Total"] = f"{total:.2f}"
        return row

    def _print_table(self, headers, rows):
        """Helper to format and print a list of dicts as a pretty table."""
        # Map project codes to their labels for the header row
        header_labels = [self.project_codes.get(h, h) for h in headers]
        
        widths = {h: len(l) for h, l in zip(headers, header_labels)}
        for row in rows:
            for h in headers:
                label = self.project_codes.get(h, h)
                widths[h] = max(widths[h], len(row.get(label, '')))

        # Print header
        header_line = " | ".join(l.ljust(widths[h]) for h, l in zip(headers, header_labels))
        print("--- Work Hours Summary ---")
        print(header_line)
        print("-|-".join('-' * widths[h] for h in headers)) # Separator

        # Print rows
        for row in rows:
            row_line_parts = []
            for h in headers:
                label = self.project_codes.get(h, h)
                row_line_parts.append(row.get(label, '0.00').rjust(widths[h]))
            print(" | ".join(row_line_parts))

    def output_csv_basic(self):
        """Outputs a basic CSV of project, date, and hours."""
        writer = csv.writer(sys.stdout)
        writer.writerow(['project', 'date', 'hours'])
        for log in self.logs:
            project_code = log.get('project')
            # Use the project code as the label if it's not in project_codes, or show "Unassigned"
            project_label = self.project_codes.get(project_code, project_code or "Unassigned")
            hours = (log['end'] - log['start']) / 60 if 'end' in log and 'start' in log else ''
            writer.writerow([project_label, log['date'], f"{hours:.2f}"])

    def output_csv_detailed(self):
        """Outputs a detailed CSV with all log fields."""
        all_keys = sorted({k for log in self.logs for k in log.keys()})
        if 'hours' not in all_keys: all_keys.append('hours')
        if 'project_label' not in all_keys: all_keys.insert(0, 'project_label')

        writer = csv.DictWriter(sys.stdout, fieldnames=all_keys)
        writer.writeheader()
        for log in self.logs:
            row = {k: log.get(k, '') for k in all_keys}
            project_code = log.get('project')
            row['project_label'] = self.project_codes.get(project_code, project_code or "Unassigned")
            row['hours'] = (log['end'] - log['start']) / 60 if 'end' in log and 'start' in log else ''
            writer.writerow(row)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="An object-oriented tool to parse and analyze work logs.")
    parser.add_argument('path', help='Path to the YAML log file')
    parser.add_argument('--csv-basic', help='Output a basic CSV report', action='store_true')
    parser.add_argument('--csv-detailed', help='Output a detailed CSV report', action='store_true')
    
    args = parser.parse_args()
    try:
        work_log = WorkLog(args.path)

        if args.csv_basic:
            work_log.output_csv_basic()
        elif args.csv_detailed:
            work_log.output_csv_detailed()
        else:
            work_log.display_summary()

    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)