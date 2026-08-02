import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


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


def create_dashboard_app(result_path):
    """Create a read-only localhost dashboard for one WFO result JSON file."""
    result_path = Path(result_path).expanduser().resolve()
    static_directory = Path(__file__).with_name("static")
    app = FastAPI(
        title="trading-wfo dashboard",
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "result_path": str(result_path)}

    @app.get("/api/result")
    def result():
        return JSONResponse(_load_result(result_path))

    app.mount("/", StaticFiles(directory=static_directory, html=True), name="dashboard")
    return app

