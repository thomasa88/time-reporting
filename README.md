# Configuration

Use `config.py.example` and `mapping.example.csv` as basis for configuring time-reporting. Save them without the `example` part.

`config.py` contains URL and credential settings.

`mapping.csv` contains a mapping table between accounting systems. Each system has one or several columns, with information needed to uniquely identify an account in that system. Each row identifies an account across all the systems.

# Running

## Fetch data

Fetch the SQLite database stored by the Time Recording Android app (not related to this project) on Google Drive.
```
./report.py timerec fetch 
```

TODO: More fetchers. Possibly an intermediate format.

## Report / Push data

```
./report.py xledger report 220101-220105
```

Specifying a range is optional. Date format is YYMMDD.

# Debugging

Enable verbose/debug logging using `-v`:

```
./report.py -v ...
```