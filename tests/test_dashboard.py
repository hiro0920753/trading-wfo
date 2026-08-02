import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from trading_wfo.cli import main
from trading_wfo.dashboard import create_dashboard_app


def dashboard_payload():
    return {
        "aggregate_metrics": {
            "net_profit": 1250,
            "return_pct": 12.5,
            "max_drawdown_pct": 4.2,
            "profit_factor": 1.8,
            "win_rate": 58.0,
            "total_trades": 12,
            "window_count": 1,
        },
        "windows": [
            {
                "index": 0,
                "optimization_start": "2026-01-01T00:00:00+00:00",
                "optimization_end": "2026-01-15T00:00:00+00:00",
                "validation_start": "2026-01-15T00:00:00+00:00",
                "validation_end": "2026-01-22T00:00:00+00:00",
                "optimization_result": {
                    "best_params": {"fast": 5, "slow": 20},
                    "best_score": 100,
                    "trials": [
                        {
                            "number": 0,
                            "params": {"fast": 5, "slow": 20},
                            "score": 100,
                            "metrics": {
                                "net_profit": 900,
                                "return_pct": 9.0,
                                "max_drawdown_pct": 3.1,
                            },
                            "feasible": True,
                            "status": "completed",
                            "violations": [],
                        }
                    ],
                },
                "validation_result": {
                    "metrics": {
                        "initial_balance": 10000,
                        "net_profit": 1250,
                        "return_pct": 12.5,
                        "max_drawdown_pct": 4.2,
                        "total_trades": 1,
                    },
                    "trades": [
                        {
                            "position_id": 1,
                            "side": "long",
                            "entry_price": 150.0,
                            "exit_price": 151.0,
                            "realized_profit": 1000,
                            "realized_pips": 100,
                            "exit_time": 2,
                            "exit_reason": "close_request",
                        }
                    ],
                    "equity_curve": [
                        {"time": 1, "balance": 10000, "equity": 10000},
                        {"time": 2, "balance": 11250, "equity": 11250},
                    ],
                },
                "validation_constraint_result": {
                    "feasible": True,
                    "violations": [],
                },
                "parameter_stability_result": {
                    "center_params": {"fast": 5, "slow": 20},
                    "variations": [
                        {
                            "params": {"fast": 4, "slow": 20},
                            "offsets": {"fast": -1},
                            "score": 80,
                            "metrics": {"net_profit": 800, "return_pct": 8, "max_drawdown_pct": 5, "total_trades": 2},
                            "feasible": True,
                            "status": "completed",
                            "violations": [],
                            "is_center": False,
                        },
                        {
                            "params": {"fast": 5, "slow": 20},
                            "offsets": {"fast": 0},
                            "score": 100,
                            "metrics": {"net_profit": 1250, "return_pct": 12.5, "max_drawdown_pct": 4.2, "total_trades": 1},
                            "feasible": True,
                            "status": "completed",
                            "violations": [],
                            "is_center": True,
                        },
                    ],
                },
            }
        ],
    }


class DashboardTest(unittest.TestCase):
    @staticmethod
    def get(app, path):
        async def request():
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                return await client.get(path)

        return asyncio.run(request())

    def test_serves_dashboard_and_result_api(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "result.json"
            result_path.write_text(
                json.dumps(dashboard_payload()), encoding="utf-8"
            )
            app = create_dashboard_app(result_path)

            health = self.get(app, "/api/health")
            result = self.get(app, "/api/result")
            index = self.get(app, "/")
            script = self.get(app, "/app.js")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["aggregate_metrics"]["net_profit"], 1250)
        self.assertIn("Strategy overview", index.text)
        self.assertIn("Optimization vs validation", index.text)
        self.assertIn('data-page="overview"', index.text)
        self.assertIn('data-page="trades"', index.text)
        self.assertIn("Validation trade diagnostics", index.text)
        self.assertIn("TRADE INSPECTOR", index.text)
        self.assertIn("renderMetrics", script.text)
        self.assertIn("appendParams", script.text)
        self.assertIn("appendParameterDetails", script.text)
        self.assertIn("+${entries.length-limit} more", script.text)
        self.assertIn("bestMetrics", script.text)
        self.assertIn("Date / time", script.text)
        self.assertIn("drawPips", script.text)
        self.assertIn("Cumulative pips", script.text)
        self.assertIn("Net profit", script.text)
        self.assertIn("renderStability", script.text)
        self.assertIn("Parameter variation", script.text)
        self.assertIn("Validation net profit", script.text)
        self.assertIn("renderTradeAnalysis", script.text)
        self.assertIn("drawTradeDistribution", script.text)
        self.assertIn("renderTradeInspector", script.text)
        self.assertIn("metadata.", script.text)

    def test_result_api_reports_missing_and_invalid_files(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = self.get(
                create_dashboard_app(Path(directory) / "missing.json"),
                "/api/result",
            )
            invalid_path = Path(directory) / "invalid.json"
            invalid_path.write_text("not json", encoding="utf-8")
            invalid = self.get(
                create_dashboard_app(invalid_path), "/api/result"
            )

        self.assertEqual(missing.status_code, 404)
        self.assertEqual(invalid.status_code, 422)

    def test_cli_starts_local_server_with_selected_result(self):
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "result.json"
            result_path.write_text(
                json.dumps(dashboard_payload()), encoding="utf-8"
            )
            with patch("uvicorn.run") as run_server:
                main(
                    [
                        "dashboard",
                        "--result",
                        str(result_path),
                        "--port",
                        "8765",
                    ]
                )

        run_server.assert_called_once()
        self.assertEqual(run_server.call_args.kwargs["host"], "127.0.0.1")
        self.assertEqual(run_server.call_args.kwargs["port"], 8765)

    def test_cli_requires_explicit_permission_for_remote_binding(self):
        with self.assertRaisesRegex(SystemExit, "allow-remote"):
            main(["dashboard", "--host", "0.0.0.0"])


if __name__ == "__main__":
    unittest.main()
