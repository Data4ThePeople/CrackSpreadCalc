#!/usr/bin/env python3
"""
build_charts.py  —  Data4ThePeople weekly chart builder
========================================================

WHAT IT DOES
  Reads one EIA .xls file from the ./input subfolder and writes a publish-ready,
  self-contained HTML chart file into the ./output subfolder:

    crack_spread_321_weekly.html   (interactive 3-2-1 crack spread, 1986-present)

  The HTML file is fully standalone (one file, no dependencies to upload) and
  works on both desktop and mobile.

REQUIRED FILE (download from EIA, drop in ./input, keep this name):
    PET_PRI_SPT_S1_W.xls   Weekly spot prices (crude + products)
                           https://www.eia.gov/dnav/pet/PET_PRI_SPT_S1_W.htm  -> "Download Series History"

HOW TO RUN
    1. Install Python 3 (one time).  Check with:  python3 --version
    2. One time, install the two libraries this needs:
           pip install pandas xlrd
    3. Put the .xls file in the ./input folder next to this script.
    4. From the script's folder run:
           python3 build_charts.py
    5. Grab the finished .html file from the ./output folder and publish it.

That's it. Re-run weekly after downloading a fresh file.
"""

import os
import sys
import json
import datetime as dt

try:
    import pandas as pd
except ImportError:
    sys.exit("ERROR: pandas not installed. Run:  pip install pandas xlrd")

HERE = os.path.dirname(os.path.abspath(__file__))
INDIR = os.path.join(HERE, "input")
OUTDIR = os.path.join(HERE, "output")
SOURCE_FILE = "PET_PRI_SPT_S1_W.xls"
os.makedirs(INDIR, exist_ok=True)
os.makedirs(OUTDIR, exist_ok=True)

# ----------------------------------------------------------------------------- helpers

def _read(path, sheet, value_col_index):
    """Read one EIA sheet. Columns are taken POSITIONALLY (col 0 = date,
    value_col_index = the series) so the script survives EIA changing the
    long header text. Header row is row 3 (header=2)."""
    df = pd.read_excel(path, sheet_name=sheet, header=2)
    df = df.iloc[:, [0, value_col_index]].copy()
    df.columns = ["Date", "Value"]
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    return df.dropna()

# ----------------------------------------------------------------------------- crack spread

def build_crack():
    f = os.path.join(INDIR, SOURCE_FILE)
    if not os.path.exists(f):
        print(f"  - SKIP crack spread: {SOURCE_FILE} not found in {INDIR}")
        return
    # positional columns within each sheet
    wti  = _read(f, "Data 1", 1).rename(columns={"Value": "WTI"})
    gasN = _read(f, "Data 2", 1).rename(columns={"Value": "GAS_NY"})
    gasG = _read(f, "Data 2", 2).rename(columns={"Value": "GAS_GC"})
    hoN  = _read(f, "Data 4", 1).rename(columns={"Value": "HO_NY"})
    dG   = _read(f, "Data 5", 2).rename(columns={"Value": "ULSD_GC"})

    m = wti
    for d in (gasN, gasG, hoN, dG):
        m = m.merge(d, on="Date", how="outer")
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
    print(f"  + crack_spread_321_weekly.html   (latest week {latest})")

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
    print(f"Data4ThePeople chart builder — {dt.date.today()}")
    print(f"Reading EIA file from: {INDIR}")
    print(f"Writing HTML to:       {OUTDIR}\n")
    build_crack()
    print("\nDone. Publish the .html file in the output folder.")

if __name__ == "__main__":
    main()
