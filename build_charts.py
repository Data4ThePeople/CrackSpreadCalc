#!/usr/bin/env python3
"""
build_charts.py  —  Data4ThePeople weekly chart builder (Eric)
========================================================

WHAT IT DOES
  Pulls weekly spot prices from EIA and writes two files into ./output:

    crack_spread_321_weekly.html   (interactive 3-2-1 crack spread, 1986-present)
    crack_spread_data.csv          (the same numbers, for eyeballing/diffing)

  The HTML file is fully standalone (one file, no dependencies to upload) and
  works on both desktop and mobile. Nothing to download by hand, ever.

WHERE THE DATA COMES FROM
  1. The EIA Open Data API, if a key is configured. Preferred: it names each
     series explicitly, so an EIA column reshuffle cannot silently swap one
     product for another.
  2. If the API is unreachable, the script downloads EIA's weekly spot-price
     spreadsheet from eia.gov instead and builds from that. EIA's /data/ API
     endpoint has real outages; the spreadsheet stays up through them.
  Either path yields identical numbers. The run prints which one it used.

API KEY (one time, optional but preferred)
    Register for a free key at  https://www.eia.gov/opendata/register.php
    then save it in a file named  .env  next to this script:

           EIA_API_KEY=your_key_here

    That file is gitignored, so the key never reaches GitHub. An EIA_API_KEY
    environment variable, or  --api-key YOUR_KEY  on the command line, also work.
    With no key at all the script still runs, straight off the spreadsheet.

HOW TO RUN
    1. Install Python 3 (one time).  Check with:  python3 --version
    2. One time, install the libraries this needs:
           pip install -r requirements.txt
    3. From the script's folder run:
           python3 build_charts.py
    4. Grab the finished .html file from the ./output folder and publish it.

That's it. Re-run weekly — EIA publishes the new week each Wednesday.
"""

import os
import sys
import json
import time
import datetime as dt
import urllib.error
import urllib.parse
import urllib.request

try:
    import pandas as pd
except ImportError:
    sys.exit("ERROR: pandas not installed. Run:  pip install pandas")

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "output")
INDIR = os.path.join(HERE, "input")
os.makedirs(OUTDIR, exist_ok=True)

# EIA Open Data API v2 — weekly spot prices for crude and refined products.
# Browse the series at https://www.eia.gov/opendata/browser/petroleum/pri/spt
EIA_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
REGISTER_URL = "https://www.eia.gov/opendata/register.php"
PAGE = 5000          # the API refuses to return more than 5,000 JSON rows at once

# Fallback: the same weekly data as a spreadsheet, straight off eia.gov.
# No API key, and it stays up when the API does not.
WORKBOOK_URL = "https://www.eia.gov/dnav/pet/xls/PET_PRI_SPT_S1_W.xls"
WORKBOOK_FILE = os.path.join(INDIR, "PET_PRI_SPT_S1_W.xls")

# column name -> (EIA series id, workbook sheet, positional column in that sheet)
SERIES = {
    "WTI":     ("RWTC",                       "Data 1", 1),  # Cushing WTI           $/bbl
    "GAS_NY":  ("EER_EPMRU_PF4_Y35NY_DPG",    "Data 2", 1),  # NY conv. gasoline     $/gal
    "GAS_GC":  ("EER_EPMRU_PF4_RGC_DPG",      "Data 2", 2),  # GC conv. gasoline     $/gal
    "HO_NY":   ("EER_EPD2F_PF4_Y35NY_DPG",    "Data 4", 1),  # NY No. 2 heating oil  $/gal
    "ULSD_GC": ("EER_EPD2DXL0_PF4_RGC_DPG",   "Data 5", 2),  # GC ULSD               $/gal
}


class EIADown(Exception):
    """The API could not be reached or refused us — caller should fall back."""

# ----------------------------------------------------------------------------- helpers

KEY_NAMES = ("EIA_API_KEY", "EIA_KEY")   # either name works, in .env or the environment


def _key_from_dotenv():
    """Read a KEY=value line out of ./.env. Kept deliberately tiny so there is no
    python-dotenv dependency. The .env file is gitignored — keep it that way."""
    for path in (os.path.join(HERE, ".env"),
                 os.path.expanduser("~/.claude/d4tp-process/.env")):  # central keys
        if not os.path.exists(path):
            continue
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip().upper() in KEY_NAMES:
                    return value.strip().strip('"').strip("'")
    return ""


def _api_key():
    """--api-key wins, then EIA_API_KEY / EIA_KEY in the environment, then ./.env."""
    if "--api-key" in sys.argv:
        i = sys.argv.index("--api-key")
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
        sys.exit("ERROR: --api-key given with no key after it.")

    for name in KEY_NAMES:
        key = os.environ.get(name, "").strip()
        if key:
            return key

    return _key_from_dotenv()   # "" if absent — caller falls back to the workbook


RETRIES = 3          # keep this short: there is a working fallback, so failing over beats waiting


def _backoff(attempt):
    return 5 * attempt          # 5s, 10s


def _get(url, tries=RETRIES):
    """One GET, retried a few times. EIA's CDN throws 503/504 in bursts, so a
    transient gateway error is expected and is not a sign of a bad request.
    Raises EIADown rather than exiting, so the caller can fall back."""
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (401, 403) and "API_KEY" in body.upper():
                raise EIADown(f"EIA rejected the API key (get one at {REGISTER_URL})")
            if e.code in (429, 500, 502, 503, 504) and attempt < tries:
                wait = _backoff(attempt)
                print(f"    (EIA returned {e.code}; retrying in {wait}s)", flush=True)
                time.sleep(wait)
                continue
            if e.code == 429:
                raise EIADown("EIA rate limit hit")
            raise EIADown(f"EIA API returned HTTP {e.code} after {attempt} attempts")
        except urllib.error.URLError as e:
            if attempt < tries:
                time.sleep(_backoff(attempt))
                continue
            raise EIADown(f"could not reach the EIA API ({e.reason})")


def _fetch_series(series_id, api_key):
    """Pull one weekly series from the EIA API as a Date/Value frame.

    IMPORTANT: sort direction must be desc. Verified against the live API on
    2026-08-06 — ascending returns total=2117 ending 2026-07-24, while
    descending returns total=2118 including 2026-07-31. Ascending silently
    omits the most recent week, which would quietly drop the newest point from
    the chart on every run. We sort back to ascending in pandas below.

    One series per request keeps each response small and each retry cheap.

    Returns the same Date/Value shape the old .xls reader did, so everything
    downstream is unchanged."""
    rows, offset, total = [], 0, None
    while total is None or len(rows) < total:
        params = [
            ("api_key", api_key),
            ("frequency", "weekly"),
            ("data[0]", "value"),
            ("facets[series][]", series_id),
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "desc"),
            ("offset", offset),
            ("length", PAGE),
        ]
        resp = _get(EIA_URL + "?" + urllib.parse.urlencode(params))["response"]
        total = int(resp.get("total", 0))
        page = resp.get("data", [])
        if not page:
            break
        rows.extend(page)
        offset += len(page)

    if not rows:
        raise EIADown(f"EIA returned no data for series {series_id}")

    df = pd.DataFrame(rows)[["period", "value"]]
    df.columns = ["Date", "Value"]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")   # API sends values as strings
    return _clean(df)


def _clean(df):
    return df.dropna().drop_duplicates("Date").sort_values("Date").reset_index(drop=True)

# ----------------------------------------------------------------------------- fallback: the workbook

def _download_workbook():
    """Grab the weekly spot-price workbook straight off eia.gov. Needs no API key
    and stays up when the API does not. Falls back to a previously downloaded copy
    if even this fails."""
    os.makedirs(INDIR, exist_ok=True)
    try:
        req = urllib.request.Request(WORKBOOK_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            data = r.read()
        if len(data) < 100_000:
            raise EIADown(f"workbook download looks truncated ({len(data)} bytes)")
        with open(WORKBOOK_FILE, "wb") as fh:
            fh.write(data)
        print(f"  . downloaded {os.path.basename(WORKBOOK_FILE)} ({len(data):,} bytes)")
    except (urllib.error.URLError, EIADown) as e:
        if os.path.exists(WORKBOOK_FILE):
            print(f"  ! could not download the workbook ({e}); using the copy already on disk")
        else:
            sys.exit(f"ERROR: the EIA API is unavailable and the workbook download failed too ({e}).\n"
                     "       Nothing to build from. Try again in a few minutes.")
    return WORKBOOK_FILE


def _read_workbook(path, sheet, value_col_index):
    """Read one workbook sheet. Columns are taken POSITIONALLY (col 0 = date,
    value_col_index = the series) so this survives EIA changing the long header
    text. Header row is row 3 (header=2)."""
    df = pd.read_excel(path, sheet_name=sheet, header=2)
    df = df.iloc[:, [0, value_col_index]].copy()
    df.columns = ["Date", "Value"]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    return _clean(df)

# ----------------------------------------------------------------------------- crack spread

def _load_series(api_key):
    """API first, as intended. If it is unreachable — EIA's /data/ endpoint has
    outages — fall back to the workbook so the chart still builds. Both paths
    return identical numbers; verified to produce a byte-identical chart."""
    if api_key:
        try:
            frames = {}
            for col, (series_id, _sheet, _c) in SERIES.items():
                frames[col] = _fetch_series(series_id, api_key)
                time.sleep(1)   # be polite to EIA's edge between series
            return frames, "EIA API"
        except EIADown as e:
            print(f"\n  ! EIA API unavailable: {e}")
            print("  ! falling back to the spreadsheet download from eia.gov\n")
    else:
        print("  ! no API key set — using the spreadsheet download from eia.gov")
        print(f"  ! (a free key from {REGISTER_URL} enables the API path)\n")

    path = _download_workbook()
    frames = {col: _read_workbook(path, sheet, c) for col, (_s, sheet, c) in SERIES.items()}
    return frames, "eia.gov workbook"


def build_crack(api_key):
    frames, source = _load_series(api_key)
    for col, df in frames.items():
        print(f"  . {col:<8} {SERIES[col][0]:<26} {len(df):>5} weeks "
              f"through {df['Date'].iloc[-1]:%Y-%m-%d}")
    frames = {c: d.rename(columns={"Value": c}) for c, d in frames.items()}

    m = frames["WTI"]
    for col in ("GAS_NY", "GAS_GC", "HO_NY", "ULSD_GC"):
        m = m.merge(frames[col], on="Date", how="outer")
    m = m.sort_values("Date").reset_index(drop=True)

    # 3-2-1: (2*gasoline + 1*distillate)*42 - 3*WTI, all /3, in $/bbl
    m["crack_NY"] = ((2 * m["GAS_NY"] + m["HO_NY"]) * 42 - 3 * m["WTI"]) / 3
    m["crack_GC"] = ((2 * m["GAS_GC"] + m["ULSD_GC"]) * 42 - 3 * m["WTI"]) / 3
    m["date"] = m["Date"].dt.strftime("%Y-%m-%d")

    out = m[["date", "crack_NY", "crack_GC", "WTI"]].round(2)
    recs = out.where(pd.notna(out), None).to_dict("records")
    latest = out.dropna(subset=["crack_NY"])["date"].iloc[-1]

    html = CRACK_TEMPLATE.replace("__DATA__", json.dumps(recs)).replace("__LATEST__", latest)
    path = os.path.join(OUTDIR, "crack_spread_321_weekly.html")
    with open(path, "w") as fh:
        fh.write(html)
    print(f"\n  + crack_spread_321_weekly.html   (latest week {latest})")

    csv_path = os.path.join(OUTDIR, "crack_spread_data.csv")
    out.to_csv(csv_path, index=False)
    print(f"  + crack_spread_data.csv          ({len(out)} weekly rows)")
    print(f"    source: {source}")

# ----------------------------------------------------------------------------- HTML template

CRACK_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>U.S. 3-2-1 Crack Spread</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box}html,body{height:100%}body{font-family:Arial,Helvetica,sans-serif;margin:0;padding:24px;background:#fff;color:#1a1a1a;-webkit-text-size-adjust:100%;display:flex;flex-direction:column}
h1{font-size:21px;margin:0 0 4px}.sub{font-size:13px;color:#666;margin:0 0 14px}.wrap{max-width:1060px;margin:0 auto;width:100%;flex:1;display:flex;flex-direction:column;min-height:0}
.chartbox{position:relative;flex:1;min-height:240px;width:100%}.controls{font-size:13px;margin:0 0 10px;color:#444}
.controls label{display:inline-flex;align-items:center;gap:5px;margin-right:16px;cursor:pointer;line-height:1.9}.controls input{width:16px;height:16px}
.presets{margin:4px 0 12px;display:flex;flex-wrap:wrap;gap:6px}
.presets button{font-size:13px;padding:7px 12px;border:1px solid #ccc;background:#f7f7f7;border-radius:5px;cursor:pointer;-webkit-tap-highlight-color:transparent}
.presets button.active{background:#1e5ac8;color:#fff;border-color:#1e5ac8}
.range{font-size:13px;color:#555;margin:6px 0 14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.range select{font-size:16px;padding:6px;border:1px solid #ccc;border-radius:5px;max-width:46%}
.src{font-size:11px;color:#aaa;margin-top:10px}.bands{font-size:12px;color:#555;margin:10px 0 0;line-height:1.9}
.chip{display:inline-block;padding:2px 7px;border-radius:3px;margin-right:4px;font-size:11px}
@media(max-width:640px){body{padding:14px}h1{font-size:18px}.sub{font-size:12px}
.presets button{flex:1 1 auto;min-width:56px;text-align:center}.range select{flex:1 1 40%;max-width:none}}
</style></head><body><div class="wrap">
<h1>U.S. 3-2-1 Crack Spread — Weekly</h1>
<p class="sub">Refining margin proxy: (2 × gasoline + 1 × distillate) × 42 − 3 × WTI, divided by 3, in dollars per barrel. Built from EIA weekly spot prices.</p>
<div class="controls">
<label><input type="checkbox" id="cbNY" checked> NY Harbor (from 1986)</label>
<label><input type="checkbox" id="cbGC" checked> Gulf Coast (from 2006)</label>
<label><input type="checkbox" id="cbWTI"> WTI crude (right axis)</label></div>
<div class="presets" id="presets">
<button data-w="13">3M</button><button data-w="26">6M</button><button data-w="52">1Y</button>
<button data-w="156">3Y</button><button data-w="260">5Y</button><button data-w="520">10Y</button>
<button data-w="all" class="active">All</button></div>
<div class="range"><span>From</span><select id="fromSel"></select><span>to</span><select id="toSel"></select></div>
<div class="chartbox"><canvas id="c"></canvas></div>
<p class="bands">Rough operating bands often cited by analysts:
<span class="chip" style="background:#e8f5e9;">$10–20 normal</span>
<span class="chip" style="background:#fff3e0;">$20–30 firm</span>
<span class="chip" style="background:#ffebee;">$30–40 stressed</span>
<span class="chip" style="background:#fbe0e0;">$40+ acute</span></p>
<p class="src">Source: EIA weekly spot prices (WTI Cushing; NY Harbor conventional gasoline &amp; No. 2 heating oil; U.S. Gulf Coast conventional gasoline &amp; ULSD). NY Harbor back to 1986; Gulf Coast ULSD from 2006. Latest week: __LATEST__. Note: this is a WTI-based, conventional-gasoline/heating-oil 3-2-1 for long history — it runs a few dollars per barrel above published Gulf Coast LLS/RBOB daily cracks.</p>
</div><script>
const RAW=__DATA__;const allLabels=RAW.map(r=>r.date);
function sliceData(a,b){return{labels:allLabels.slice(a,b+1),ny:RAW.slice(a,b+1).map(r=>r.crack_NY),gc:RAW.slice(a,b+1).map(r=>r.crack_GC),wti:RAW.slice(a,b+1).map(r=>r.WTI)};}
let fromIdx=0,toIdx=RAW.length-1;
const dsNY={label:'NY Harbor 3-2-1',borderColor:'rgba(30,90,200,0.95)',backgroundColor:'rgba(30,90,200,0.95)',borderWidth:1.5,pointRadius:0,pointHoverRadius:3,tension:0.1,spanGaps:true,yAxisID:'y'};
const dsGC={label:'Gulf Coast 3-2-1',borderColor:'rgba(200,60,30,0.9)',backgroundColor:'rgba(200,60,30,0.9)',borderWidth:1.5,pointRadius:0,pointHoverRadius:3,tension:0.1,spanGaps:true,yAxisID:'y'};
const dsWTI={label:'WTI crude ($ per barrel)',borderColor:'rgba(120,120,120,0.55)',backgroundColor:'rgba(120,120,120,0.55)',borderWidth:1.1,pointRadius:0,pointHoverRadius:3,tension:0.1,spanGaps:true,yAxisID:'y2',hidden:true};
const bands={id:'bands',beforeDraw(chart){const{ctx,chartArea:{left,right,top,bottom},scales:{y}}=chart;if(!y)return;const zones=[[10,20,'rgba(76,175,80,0.06)'],[20,30,'rgba(255,152,0,0.06)'],[30,40,'rgba(244,67,54,0.06)'],[40,80,'rgba(244,67,54,0.11)']];ctx.save();ctx.beginPath();ctx.rect(left,top,right-left,bottom-top);ctx.clip();const clamp=p=>Math.max(top,Math.min(bottom,p));zones.forEach(([lo,hi,col])=>{const yhi=clamp(y.getPixelForValue(hi)),ylo=clamp(y.getPixelForValue(lo));if(ylo<=yhi)return;ctx.fillStyle=col;ctx.fillRect(left,yhi,right-left,ylo-yhi);});ctx.restore();}};
const isMobile=window.matchMedia('(max-width:640px)').matches;
const chart=new Chart(document.getElementById('c'),{type:'line',data:{labels:[],datasets:[dsNY,dsGC,dsWTI]},
options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
plugins:{legend:{display:false},tooltip:{titleFont:{size:isMobile?13:12},bodyFont:{size:isMobile?13:12},callbacks:{label:(ctx)=>`${ctx.dataset.label}: ${ctx.parsed.y==null?'—':'$'+ctx.parsed.y.toFixed(2)}`}}},
scales:{y:{title:{display:!isMobile,text:'Crack spread ($ per barrel)'},ticks:{callback:v=>'$'+v}},
y2:{position:'right',display:false,title:{display:!isMobile,text:'WTI ($ per barrel)'},grid:{drawOnChartArea:false},ticks:{callback:v=>'$'+v}},
x:{ticks:{maxTicksLimit:isMobile?6:14,autoSkip:true,maxRotation:45,minRotation:45,callback:function(val){const lbl=this.getLabelForValue(val);return lbl?lbl.slice(0,7):lbl;}},title:{display:!isMobile,text:'Week'}}}},plugins:[bands]});
function render(){const s=sliceData(fromIdx,toIdx);chart.data.labels=s.labels;dsNY.data=s.ny;dsGC.data=s.gc;dsWTI.data=s.wti;chart.update();}
const fromSel=document.getElementById('fromSel'),toSel=document.getElementById('toSel');
allLabels.forEach((d,i)=>{const o1=document.createElement('option');o1.value=i;o1.textContent=d;fromSel.appendChild(o1);const o2=document.createElement('option');o2.value=i;o2.textContent=d;toSel.appendChild(o2);});
function syncSel(){fromSel.value=fromIdx;toSel.value=toIdx;}
fromSel.onchange=e=>{fromIdx=Math.min(+e.target.value,toIdx);syncSel();clearPreset();render();};
toSel.onchange=e=>{toIdx=Math.max(+e.target.value,fromIdx);syncSel();clearPreset();render();};
const pbtns=[...document.querySelectorAll('#presets button')];
function clearPreset(){pbtns.forEach(b=>b.classList.remove('active'));}
pbtns.forEach(btn=>{btn.onclick=()=>{clearPreset();btn.classList.add('active');toIdx=RAW.length-1;if(btn.dataset.w==='all'){fromIdx=0;}else{fromIdx=Math.max(0,RAW.length-(+btn.dataset.w));}syncSel();render();};});
document.getElementById('cbNY').onchange=e=>{dsNY.hidden=!e.target.checked;chart.update();};
document.getElementById('cbGC').onchange=e=>{dsGC.hidden=!e.target.checked;chart.update();};
document.getElementById('cbWTI').onchange=e=>{dsWTI.hidden=!e.target.checked;chart.options.scales.y2.display=e.target.checked;chart.update();};
syncSel();render();
</script></body></html>"""

# ----------------------------------------------------------------------------- main

def main():
    key = _api_key()
    print(f"Data4ThePeople chart builder — {dt.date.today()}")
    print("Pulling weekly spot prices from the EIA API")
    print(f"Writing output to:     {OUTDIR}\n")
    build_crack(key)
    print("\nDone. Publish the .html file in the output folder.")

if __name__ == "__main__":
    main()
