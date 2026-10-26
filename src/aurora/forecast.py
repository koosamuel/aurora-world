"""Fixed-origin naive / seasonal-naive forecasting and time-respecting evaluation.

Method references (independent implementation, no copied paper code):
Hyndman & Koehler, Another look at measures of forecast accuracy (MASE),
https://robjhyndman.com/papers/mase.pdf.
M4 benchmarks: https://doi.org/10.1016/j.ijforecast.2019.04.014.
Synthetic seasonal scale m=52 differs from M4 weekly evaluation m=1;
this project does not claim replication of competition scores.
"""
from __future__ import annotations
import hashlib
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path

DEFAULT = dict(seed=42, skus=50, weeks=156, horizon=4, season_length=52,
               validation_origins=3, assumption_version="demo-A01-A11-v1")
MODELS = ("naive", "seasonal_naive")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def config_for(options=None):
    options = {} if options is None else options
    if not isinstance(options, dict) or set(options) - set(DEFAULT):
        raise ValueError("허용되지 않은 설정입니다.")
    c = DEFAULT | options
    for k, lo, hi in (("seed", 0, 2**31 - 1), ("skus", 1, 100), ("weeks", 20, 520),
                      ("horizon", 1, 12), ("season_length", 1, 104), ("validation_origins", 1, 5)):
        if type(c[k]) is not int or not lo <= c[k] <= hi:
            raise ValueError(f"{k}: {lo}~{hi} 범위의 정수가 필요합니다.")
    if c["weeks"] <= c["horizon"] * (c["validation_origins"] + 1):
        raise ValueError("검증·최종 평가를 나눌 이력이 부족합니다.")
    if not isinstance(c["assumption_version"], str) or not 1 <= len(c["assumption_version"]) <= 80:
        raise ValueError("가정 버전을 확인하세요.")
    return c


def synthetic_data(options=None):
    c = config_for(options)
    rng = random.Random(c["seed"])
    kinds = ("constant", "zero", "seasonal", "intermittent", "short", "missing", "returns", "trend")
    result = []
    for i in range(c["skus"]):
        kind = kinds[i % len(kinds)]
        values, statuses = [], []
        for t in range(c["weeks"]):
            value = max(0, round(18 + 10 * math.sin(2 * math.pi * t / 52)
                                  + rng.gauss(0, 2)))
            status = "observed"
            if kind == "constant": value = 10.0
            elif kind == "zero": value = 0.0
            elif kind == "seasonal": value = float((t % 52) + 1)
            elif kind == "intermittent": value = float(rng.randint(1, 35) if rng.random() < 0.22 else 0)
            elif kind == "short" and t < c["weeks"] - 12: value, status = None, "not_started"
            elif kind == "missing" and t % 29 == 7: value, status = None, "missing"
            elif kind == "returns" and t % 31 == 9: value, status = -3.0, "return"
            elif kind == "trend": value = max(0, round(5 + t * 0.2 + rng.gauss(0, 1)))
            values.append(value)
            statuses.append(status)
        result.append(dict(sku=f"SKU-{i+1:03}", pattern=kind, values=values, statuses=statuses))
    return result


def usable(value):
    return value is not None and math.isfinite(value) and value >= 0


def predict(train, horizon, model, season_length=52):
    """Only the supplied history can affect a fixed-origin forecast; no forward fill."""
    if model not in MODELS: raise ValueError("지원하지 않는 기준선입니다.")
    if model == "naive":
        if not train or not usable(train[-1]): return None, "last_period_unobserved"
        return [float(train[-1])] * horizon, None
    if len(train) < season_length: return None, "insufficient_seasonal_history"
    points = [train[len(train) - season_length + (h % season_length)] for h in range(horizon)]
    if not all(usable(x) for x in points): return None, "seasonal_period_unobserved"
    return [float(x) for x in points], None


def mase_scale(train, season_length):
    diffs = [abs(train[i] - train[i-season_length]) for i in range(season_length, len(train))
             if usable(train[i]) and usable(train[i-season_length])]
    if not diffs: return None
    scale = sum(diffs) / len(diffs)
    return scale if scale > 0 else None


def split_origins(c):
    h, end = c["horizon"], c["weeks"] - c["horizon"]
    return [("validation", end - h * k) for k in range(c["validation_origins"], 0, -1)] + [("test", end)]


def evaluate(series, c):
    rows, skips = [], []
    for split, origin in split_origins(c):
        for item in series:
            train = item["values"][:origin]
            scale = mase_scale(train, c["season_length"])
            for model in MODELS:
                preds, reason = predict(train, c["horizon"], model, c["season_length"])
                if preds is None:
                    skips.append(dict(sku=item["sku"], split=split, origin=origin,
                                      model=model, reason=reason)); continue
                for h, pred in enumerate(preds):
                    actual = item["values"][origin+h]
                    if not usable(actual):
                        skips.append(dict(sku=item["sku"], split=split, origin=origin,
                                          model=model, reason="target_unobserved", horizon=h+1)); continue
                    rows.append(dict(sku=item["sku"], split=split, origin=origin, horizon=h+1,
                                     model=model, actual=float(actual), predicted=pred, mase_scale=scale))
    # Paired comparisons use identical SKU/origin/target keys for BOTH models.
    keys_by_model = {m: {(r["sku"],r["split"],r["origin"],r["horizon"]) for r in rows if r["model"]==m}
                     for m in MODELS}
    common = keys_by_model[MODELS[0]] & keys_by_model[MODELS[1]]
    paired = [r for r in rows if (r["sku"],r["split"],r["origin"],r["horizon"]) in common]
    def summarize(data):
        summaries = []
        for split in ("validation", "test"):
            for model in MODELS:
                rs = [r for r in data if r["split"]==split and r["model"]==model]
                errors = [r["predicted"]-r["actual"] for r in rs]
                scaled = [abs(r["predicted"]-r["actual"])/r["mase_scale"] for r in rs if r["mase_scale"] is not None]
                summaries.append(dict(split=split, model=model, n=len(rs),
                    skus=len({r["sku"] for r in rs}),
                    mae=sum(abs(e) for e in errors)/len(errors) if errors else None,
                    bias=sum(errors)/len(errors) if errors else None,
                    mase=sum(scaled)/len(scaled) if scaled else None, mase_n=len(scaled)))
        return summaries
    return dict(metrics=summarize(rows), paired_metrics=summarize(paired),
                predictions=rows, skipped=skips)


def run_baseline(options=None):
    c = config_for(options)
    series = synthetic_data(c)
    dates = [(date(2023, 1, 2) + timedelta(weeks=t)).isoformat() for t in range(c["weeks"])]
    return run_series(series,c,dates,"synthetic-v1")


def run_series(series,c,periods,dataset_version,input_manifest=None,input_quality=None):
    evaluation = evaluate(series, c)
    last=date.fromisoformat(periods[-1])
    dates=list(periods)+[(last+timedelta(weeks=t+1)).isoformat() for t in range(c["horizon"])]
    views = []
    for item in series:
        future = {}
        unavailable = {}
        for model in MODELS:
            future[model], unavailable[model] = predict(item["values"], c["horizon"], model, c["season_length"])
        views.append(dict(sku=item["sku"], pattern=item["pattern"],
            history=[dict(period=dates[t], value=item["values"][t], status=item["statuses"][t])
                     for t in range(max(0,c["weeks"]-26),c["weeks"])],
            future_periods=dates[c["weeks"]:], forecast=future, unavailable=unavailable))
    from .decisions import build
    decisions = build(series, c)
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return dict(schema_version="aurora-baseline-v1", synthetic=True, config=c,
                dataset_version=dataset_version, input_manifest=input_manifest, dataset_checksum=digest(series),
                config_hash=digest(c), code_revision=code_hash,
                split_version="fixed-origin-v1", splits=[dict(split=s, origin=o,
                    train_end=dates[o-1], target_start=dates[o], target_end=dates[o+c["horizon"]-1])
                    for s,o in split_origins(c)],
                quality=input_quality or dict(series=len(series), observations=c["skus"]*c["weeks"],
                    missing=sum(s=="missing" for x in series for s in x["statuses"]),
                    returns=sum(s=="return" for x in series for s in x["statuses"]),
                    not_started=sum(s=="not_started" for x in series for s in x["statuses"])),
                series=views, decisions=decisions, **evaluation)
