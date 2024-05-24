# LogTracker
Log tracker for work hours

Dependencies: `pyyaml`

## Usage:

'Install' as a submodule `git submodule add https://github.com/GabeBolton/LogTracker.git`

Create a YAML file in the format:

```yaml
logs:
  - date: 24/05/2024
    start: 9:00
    end: 9:15
    work:
      - Installed LogTracker
      - Checked Emails
      - Preped notes for round-up

  - date: 24/05/2024
    start: 9:15
    end: 9:30
    work:
      - Morning Round-up |
        Wins - can nicely track my hours in my IDE parallel to my code
        Blockers - I'm saving just way too much hassle switching between code, my excel timesheet, and my work notes
          boss will give me more work to do to fill the time
```

Then run `python ./LogTracker/log_parser.py contract_x_log_file.yaml`