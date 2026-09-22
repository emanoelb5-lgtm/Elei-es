#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
from io import StringIO
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "historical-backtest.json"

WIKI_2022 = "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2022_Brazilian_presidential_election"
TSE_RESULT_SOURCE = "https://www.tse.jus.br/comunicacao/noticias/2022/Outubro/100-das-secoes-totalizadas-confira-como-ficou-o-quadro-eleitoral-apos-o-1o-turno"
ELECTION_DATE = date(2022, 10, 2)

RESULT_VALID = {
    "lula": 48.43,
    "bolsonaro": 43.20,
    "tebet": 4.16,
    "gomes": 3.04,
}

ALIASES = {
    "lula": ["lula"],
    "bolsonaro": ["bolsonaro"],
    "tebet": ["tebet"],
    "gomes": ["gomes", "ciro"],
}

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).lower()).strip()

def flatten_columns(df: pd.DataFrame) -> List[str]:
    out=[]
    for col in df.columns:
        if isinstance(col, tuple):
            parts=[]
            for x in col:
                sx=str(x).strip()
                if sx and not sx.startswith("Unnamed") and sx not in parts:
                    parts.append(sx)
            out.append(" ".join(parts))
        else:
            out.append(str(col))
    return out

def find_col(cols: List[str], terms: List[str]) -> str | None:
    for c in cols:
        low=norm(c)
        if any(t in low for t in terms):
            return c
    return None

def candidate_col(cols: List[str], aliases: List[str]) -> str | None:
    for c in cols:
        low=norm(c)
        if any(a in low for a in aliases):
            return c
    return None

MONTHS = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12
}

def parse_end_date(value) -> date | None:
    text=str(value).replace("–","-").replace("—","-")
    # examples: 27-29 Sep 2022; 30 Sep - 1 Oct 2022; 1 Oct 2022
    hits=re.findall(r"(\d{1,2})\s*([A-Za-z]{3})?\s*(?:2022)?", text)
    if not hits:
        return None
    day_s, mon_s=hits[-1]
    if mon_s:
        month=MONTHS.get(mon_s.lower()[:3])
    else:
        # inherit the last explicit month in string
        mons=re.findall(r"([A-Za-z]{3})", text)
        month=MONTHS.get(mons[-1].lower()[:3]) if mons else None
    if not month:
        return None
    try:
        return date(2022,month,int(day_s))
    except ValueError:
        return None

def pct(v) -> float | None:
    m=re.search(r"(\d+(?:\.\d+)?)", str(v).replace(",","."))
    if not m:
        return None
    x=float(m.group(1))
    return x if 0 <= x <= 100 else None

def sample_n(v) -> int:
    digits=re.sub(r"\D","",str(v))
    if not digits:
        return 2000
    n=int(digits)
    return n if 300 <= n <= 100000 else 2000

def load_2022_polls() -> List[dict]:
    response=requests.get(
        WIKI_2022,
        headers={"User-Agent":"TermometroEleicoes/0.4.1 historical-backtest"},
        timeout=30,
    )
    response.raise_for_status()
    tables=pd.read_html(StringIO(response.text))
    polls=[]
    for df in tables:
        df=df.copy()
        df.columns=flatten_columns(df)
        cols=list(df.columns)
        ccols={cid:candidate_col(cols, aliases) for cid,aliases in ALIASES.items()}
        if sum(1 for x in ccols.values() if x) < 4:
            continue
        pollster=find_col(cols,["pollster","polling firm","firm","source"])
        dates=find_col(cols,["date","dates conducted","fieldwork"])
        sample=find_col(cols,["sample"])
        if not pollster or not dates:
            continue
        for _,row in df.iterrows():
            end=parse_end_date(row.get(dates))
            if end is None or end > ELECTION_DATE:
                continue
            values={}
            ok=True
            for cid,col in ccols.items():
                if not col:
                    ok=False; break
                value=pct(row.get(col))
                if value is None:
                    ok=False; break
                values[cid]=value
            if not ok:
                continue
            inst=str(row.get(pollster,"")).strip()
            if not inst or inst.lower()=="nan":
                continue
            polls.append({
                "date":end,
                "institute":inst,
                "sample":sample_n(row.get(sample)) if sample else 2000,
                "method":"histórico não padronizado",
                "values":values,
            })
    # dedupe by content
    seen={}
    for p in polls:
        key=(norm(p["institute"]),p["date"].isoformat(),p["sample"],tuple(sorted(p["values"].items())))
        seen[key]=p
    return sorted(seen.values(), key=lambda p:(p["date"],norm(p["institute"])))

def normalize4(values: Dict[str,float]) -> Dict[str,float]:
    total=sum(max(values.get(k,0.0),0.0) for k in RESULT_VALID)
    if total<=0:
        return {}
    return {k:100*max(values.get(k,0.0),0.0)/total for k in RESULT_VALID}

RESULT4=normalize4(RESULT_VALID)

def model_mean(polls:List[dict], cutoff:date, weighted:bool) -> Dict[str,float]:
    eligible=[p for p in polls if p["date"]<=cutoff and 0 <= (cutoff-p["date"]).days <= 30]
    if not eligible:
        return {}
    counts={}
    for p in eligible:
        key=norm(p["institute"]); counts[key]=counts.get(key,0)+1
    sums={k:0.0 for k in RESULT_VALID}; sw={k:0.0 for k in RESULT_VALID}
    for p in eligible:
        age=max((cutoff-p["date"]).days,0)
        if weighted:
            w=math.exp(-age/10.0)
            w*=min(max(math.sqrt(max(p["sample"],300)/2000.0),0.65),1.60)
            w*=1.0/math.sqrt(max(counts[norm(p["institute"])],1))
        else:
            w=1.0
        for k,v in p["values"].items():
            if k in sums:
                sums[k]+=v*w; sw[k]+=w
    raw={k:sums[k]/sw[k] for k in sums if sw[k]>0}
    return normalize4(raw)

def mae(pred:Dict[str,float]) -> float | None:
    if len(pred)<4:
        return None
    return sum(abs(pred[k]-RESULT4[k]) for k in RESULT4)/len(RESULT4)

def run_backtest(polls:List[dict]) -> dict:
    horizons=[30,21,14,7,3,1]
    rows=[]
    for days in horizons:
        cutoff=ELECTION_DATE-timedelta(days=days)
        eligible=[p for p in polls if p["date"]<=cutoff and 0 <= (cutoff-p["date"]).days <= 30]
        institutes=len({norm(p["institute"]) for p in eligible})
        weighted=model_mean(polls,cutoff,True)
        simple=model_mean(polls,cutoff,False)
        rows.append({
            "daysBeforeElection":days,
            "cutoff":cutoff.isoformat(),
            "pollCount":len(eligible),
            "instituteCount":institutes,
            "weightedMae":round(mae(weighted),2) if mae(weighted) is not None else None,
            "simpleMae":round(mae(simple),2) if mae(simple) is not None else None,
            "weightedEstimate":{k:round(v,2) for k,v in weighted.items()},
            "simpleEstimate":{k:round(v,2) for k,v in simple.items()},
        })
    valid=[r for r in rows if r["weightedMae"] is not None]
    return {
        "status":"ok" if valid else "insufficient-data",
        "year":2022,
        "round":"1º turno",
        "electionDate":ELECTION_DATE.isoformat(),
        "pollSource":WIKI_2022,
        "resultSource":TSE_RESULT_SOURCE,
        "pollCountTotal":len(polls),
        "resultComparisonBasis":"votos dos quatro candidatos comuns normalizados para 100%",
        "officialResultCommonSet":{k:round(v,2) for k,v in RESULT4.items()},
        "horizons":rows,
        "averageWeightedMae":round(sum(r["weightedMae"] for r in valid)/len(valid),2) if valid else None,
        "averageSimpleMae":round(sum(r["simpleMae"] for r in valid)/len(valid),2) if valid else None,
        "correctionApplied":False,
        "note":"Backtest histórico separado. Não altera pesos, médias ou candidatos de 2026.",
    }

def main():
    polls=load_2022_polls()
    result=run_backtest(polls)
    payload={
        "schemaVersion":1,
        "generatedAt":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "studies":[result],
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n","utf-8")
    print("Backtest histórico:",result["status"],"pesquisas=",len(polls),"MAE ponderado=",result["averageWeightedMae"],"MAE simples=",result["averageSimpleMae"])

if __name__=="__main__":
    main()
