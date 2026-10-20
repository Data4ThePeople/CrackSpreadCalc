# U.S. 3-2-1 Crack Spread, Weekly

A weekly chart of the U.S. 3-2-1 crack spread, a common rough measure of refining margins, built from U.S. Energy Information Administration (EIA) spot prices. It shows the spread for New York Harbor and the Gulf Coast, with WTI crude as an optional overlay, and it refreshes each week after EIA posts new prices.

## Live link

- Interactive chart: https://data4thepeople.github.io/CrackSpreadCalc/output/crack_spread_321_weekly.html
- GitHub Pages site: https://data4thepeople.github.io/CrackSpreadCalc/

## What's here

- `build_charts.py`: pulls the EIA price series, computes the crack spread, and writes the two files in `output/`.
- `output/crack_spread_321_weekly.html`: the finished chart. One standalone file that works on desktop and mobile. It has date presets, a from/to range picker, and toggles for each series.
- `output/crack_spread_data.csv`: the same weekly numbers as a table (date, NY Harbor spread, Gulf Coast spread, WTI price).
- `requirements.txt`: the Python libraries the build needs.
- `scripts/weekly.sh`: the unattended weekly refresh. It runs the build, and if a new full week of data arrived, commits and pushes the updated `output/` folder.
- `scripts/org.data4thepeople.crackspread-weekly.plist`: the macOS launchd schedule that runs `weekly.sh` on Wednesday afternoon, with a backup run on Thursday morning.

## Data sources

All prices are EIA weekly spot prices, from the EIA Open Data API (petroleum spot prices) or, as a fallback, EIA's weekly spot price spreadsheet on eia.gov.

| Series | Location | EIA series ID | Units |
|---|---|---|---|
| WTI crude oil | Cushing, OK | `RWTC` | $ per barrel |
| Conventional gasoline | New York Harbor | `EER_EPMRU_PF4_Y35NY_DPG` | $ per gallon |
| No. 2 heating oil | New York Harbor | `EER_EPD2F_PF4_Y35NY_DPG` | $ per gallon |
| Conventional gasoline | U.S. Gulf Coast | `EER_EPMRU_PF4_RGC_DPG` | $ per gallon |
| Ultra-low sulfur diesel (ULSD) | U.S. Gulf Coast | `EER_EPD2DXL0_PF4_RGC_DPG` | $ per gallon |

- API: https://api.eia.gov/v2/petroleum/pri/spt/data/
- Spreadsheet fallback: https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_W.xls

## How to rebuild

Requirements: Python 3, plus the libraries in `requirements.txt` (pandas, and xlrd for the spreadsheet fallback).

```sh
pip install -r requirements.txt
python3 build_charts.py
```

The chart and CSV are written to `output/`. EIA publishes the new week of spot prices each Wednesday.

API key: the EIA API path needs a free EIA API key, read from the `EIA_API_KEY` (or `EIA_KEY`) environment variable, a private `.env` file kept out of the repo, or `--api-key` on the command line. Register at https://www.eia.gov/opendata/register.php. Without a key, the script builds from the eia.gov spreadsheet instead. The script prints which source it used.

To automate the weekly refresh on a Mac, `scripts/weekly.sh` expects a virtual environment at `.venv/` and is scheduled by the launchd file in `scripts/`. The path inside that file points to one local machine, so edit it before loading it on another.

## Method notes

- The 3-2-1 crack spread prices turning three barrels of crude into two barrels of gasoline and one barrel of distillate: (2 × gasoline + 1 × distillate) × 42 − 3 × WTI, divided by 3, in dollars per barrel. Product prices are converted from dollars per gallon at 42 gallons per barrel.
- Both regions use WTI Cushing as the crude price. New York Harbor uses conventional gasoline and No. 2 heating oil, which gives the longest history. The Gulf Coast series uses conventional gasoline and ULSD and starts later.
- This WTI-based version, built on conventional gasoline and heating oil for long history, runs a few dollars per barrel above published Gulf Coast LLS/RBOB daily cracks, as the chart notes.
- The colored bands on the chart are rough operating ranges often cited by analysts. They are context, not thresholds from EIA.
- The API is queried newest-first, because an oldest-first query was found to leave out the most recent week. The weekly job also skips any week where one of the series has not posted yet, so a partly filled week is not published.

---

Data 4 The People
