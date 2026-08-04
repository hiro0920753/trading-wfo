import json
import math
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


MARKET_REQUIRED_COLUMNS = {"time", "open", "high", "low", "close", "bid", "ask"}


def _load_result(path):
    try:
        with path.open(encoding="utf-8") as file:
            payload = json.load(file)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404, detail=f"result file not found: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=422, detail=f"invalid result JSON: {error}"
        ) from error
    except OSError as error:
        raise HTTPException(
            status_code=500, detail=f"could not read result file: {error}"
        ) from error

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="result JSON must be an object")
    if "aggregate_metrics" not in payload or "windows" not in payload:
        raise HTTPException(
            status_code=422,
            detail="result JSON must contain aggregate_metrics and windows",
        )
    if not isinstance(payload["windows"], list):
        raise HTTPException(status_code=422, detail="windows must be a list")
    return payload


def _csv_files(directory):
    return sorted(directory.rglob("*.csv")) if directory is not None else []


def _read_csv_files(files, *, required_columns, kind, deduplicate=False):
    frames = []
    errors = []
    for path in files:
        try:
            frame = pd.read_csv(path)
        except (OSError, UnicodeError, pd.errors.ParserError) as error:
            errors.append(f"{path.name}: {error}")
            continue
        missing = required_columns.difference(frame.columns)
        if missing:
            errors.append(f"{path.name}: missing {', '.join(sorted(missing))}")
            continue
        frame = frame.copy()
        frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
        frame = frame.dropna(subset=["time"])
        frame["_source"] = path.name
        frames.append(frame)
    if not frames:
        detail = f"no usable {kind} CSV files found"
        if errors:
            detail += ": " + "; ".join(errors[:3])
        raise HTTPException(status_code=422, detail=detail)
    result = pd.concat(frames, ignore_index=True).sort_values("time", kind="stable")
    return result.drop_duplicates("time") if deduplicate else result


def _infer_interval_seconds(frame):
    differences = frame["time"].sort_values().diff().dropna().dt.total_seconds()
    differences = differences[differences > 0]
    if differences.empty:
        raise HTTPException(status_code=422, detail="cannot infer market timeframe")
    return int(round(float(differences.median())))


def _timeframe_options(base_seconds):
    standard = [60, 300, 900, 1800, 3600, 14_400, 86_400, 604_800]
    values = [value for value in standard if value >= base_seconds and value % base_seconds == 0]
    if base_seconds not in values:
        values.insert(0, base_seconds)
    return values


def _label_timeframe(seconds):
    if seconds % 86_400 == 0:
        return f"{seconds // 86_400}D"
    if seconds % 3_600 == 0:
        return f"{seconds // 3_600}H"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _clean_value(value):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _records(frame, columns):
    return [
        {column: _clean_value(row[column]) for column in columns}
        for _, row in frame[columns].iterrows()
    ]


def _resample_market(frame, seconds):
    indexed = frame.set_index("time")
    rules = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "bid": "last",
        "ask": "last",
    }
    for column in frame.columns:
        if column not in rules and column not in {"time", "_source"}:
            if pd.api.types.is_numeric_dtype(frame[column]):
                rules[column] = "last"
    result = indexed.resample(f"{seconds}s", origin="epoch").agg(rules)
    return result.dropna(subset=["open", "high", "low", "close"]).reset_index()


def _resolve_directory(value, label):
    if value is None:
        return None
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"{label} directory not found: {path}")
    return path


def create_dashboard_app(result_path, *, market_data_directory=None, log_directory=None, progress_path=None):
    """Create a read-only localhost dashboard for one WFO result JSON file."""
    result_path = Path(result_path).expanduser().resolve()
    progress_path = (
        result_path.with_suffix(".progress.json")
        if progress_path is None else Path(progress_path).expanduser().resolve()
    )
    market_directory = _resolve_directory(market_data_directory, "market data")
    logs_directory = _resolve_directory(log_directory, "log")
    static_directory = Path(__file__).with_name("static")
    app = FastAPI(title="trading-wfo dashboard", docs_url=None, redoc_url=None)

    market_cache = None
    log_cache = None

    def market_frame():
        nonlocal market_cache
        if market_directory is None:
            raise HTTPException(status_code=404, detail="market data directory was not configured")
        if market_cache is None:
            market_cache = _read_csv_files(
                _csv_files(market_directory),
                required_columns=MARKET_REQUIRED_COLUMNS,
                kind="market data",
                deduplicate=True,
            )
        return market_cache

    def log_frame():
        nonlocal log_cache
        if logs_directory is None:
            raise HTTPException(status_code=404, detail="log directory was not configured")
        if log_cache is None:
            log_cache = _read_csv_files(
                _csv_files(logs_directory), required_columns={"time"}, kind="log"
            )
        return log_cache

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "result_path": str(result_path),
            "market_data_directory": str(market_directory) if market_directory else None,
            "log_directory": str(logs_directory) if logs_directory else None,
            "progress_path": str(progress_path),
        }

    @app.get("/api/result")
    def result():
        return JSONResponse(_load_result(result_path))

    @app.get("/api/result/status")
    def result_status():
        try:
            stat = result_path.stat()
        except FileNotFoundError:
            return {"exists": False, "signature": None}
        except OSError as error:
            raise HTTPException(status_code=500, detail=f"could not stat result file: {error}") from error
        return {"exists": True, "signature": f"{stat.st_mtime_ns}:{stat.st_size}"}

    @app.get("/api/progress")
    def progress():
        if not progress_path.is_file():
            return {"status": "idle", "message": "No active WFO progress file"}
        try:
            with progress_path.open(encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=503, detail=f"could not read progress: {error}") from error
        return JSONResponse(payload)

    @app.get("/api/chart/config")
    def chart_config():
        response = {"market_configured": market_directory is not None, "log_configured": logs_directory is not None}
        if market_directory is not None:
            frame = market_frame()
            base = _infer_interval_seconds(frame)
            numeric = [
                column for column in frame.columns
                if column not in {"time", "_source"} and pd.api.types.is_numeric_dtype(frame[column])
            ]
            response.update(
                {
                    "base_timeframe_seconds": base,
                    "timeframes": [
                        {"seconds": value, "label": _label_timeframe(value)}
                        for value in _timeframe_options(base)
                    ],
                    "allowed_timeframes": _timeframe_options(base),
                    "market_columns": numeric,
                    "market_start": frame["time"].iloc[0].isoformat(),
                    "market_end": frame["time"].iloc[-1].isoformat(),
                }
            )
        if logs_directory is not None:
            frame = log_frame()
            response["log_columns"] = [
                column for column in frame.columns
                if column not in {"time", "_source"} and pd.api.types.is_numeric_dtype(frame[column])
            ]
            response["log_sources"] = sorted(frame["_source"].unique().tolist())
        return response

    @app.get("/api/chart/market")
    def chart_market(
        start: float = Query(...),
        end: float = Query(...),
        timeframe: int = Query(..., gt=0),
    ):
        frame = market_frame()
        base = _infer_interval_seconds(frame)
        if timeframe < base or timeframe % base:
            raise HTTPException(
                status_code=422,
                detail=f"timeframe must be a multiple of the source timeframe ({base}s)",
            )
        start_time = pd.to_datetime(start, unit="s", utc=True)
        end_time = pd.to_datetime(end, unit="s", utc=True)
        selected = frame[(frame["time"] >= start_time) & (frame["time"] <= end_time)]
        if selected.empty:
            raise HTTPException(status_code=404, detail="no market rows in selected trade range")
        sampled = _resample_market(selected, timeframe)
        columns = [column for column in sampled.columns if column != "_source"]
        return {"timeframe_seconds": timeframe, "columns": columns, "records": _records(sampled, columns)}

    @app.get("/api/chart/logs")
    def chart_logs(start: float = Query(...), end: float = Query(...)):
        frame = log_frame()
        start_time = pd.to_datetime(start, unit="s", utc=True)
        end_time = pd.to_datetime(end, unit="s", utc=True)
        selected = frame[(frame["time"] >= start_time) & (frame["time"] <= end_time)]
        columns = [column for column in selected.columns if column != "_source"]
        return {"columns": columns, "records": _records(selected, columns)}

    @app.get("/plotly.min.js", include_in_schema=False)
    def plotly_javascript():
        import plotly

        path = Path(plotly.__file__).with_name("package_data") / "plotly.min.js"
        return FileResponse(path, media_type="application/javascript")

    app.mount("/", StaticFiles(directory=static_directory, html=True), name="dashboard")
    return app
