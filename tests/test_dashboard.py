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
                            "time": 1,
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
            trade_chart = self.get(app, "/trade-chart.js")
            chart_export = self.get(app, "/chart-export.js")
            progress = self.get(app, "/api/progress")
            result_status = self.get(app, "/api/result/status")

        self.assertEqual(health.status_code, 200)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(progress.json()["status"], "idle")
        self.assertTrue(result_status.json()["exists"])
        self.assertEqual(result.json()["aggregate_metrics"]["net_profit"], 1250)
        self.assertIn("Strategy overview", index.text)
        self.assertIn("Optimization vs validation", index.text)
        self.assertIn('data-page="overview"', index.text)
        self.assertIn('data-page="trades"', index.text)
        self.assertIn('data-page="progress"', index.text)
        self.assertIn("Walk-forward progress", index.text)
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
        self.assertIn("renderTradeChart", script.text)
        self.assertIn("loadProgress", script.text)
        self.assertIn("pollResult", script.text)
        self.assertIn("/plotly.min.js", index.text)
        self.assertIn("theme-toggle", index.text)
        self.assertIn("trading-wfo-theme", index.text)
        self.assertIn("toggleTheme", script.text)
        self.assertEqual(trade_chart.status_code, 200)
        self.assertIn("Market prices", trade_chart.text)
        self.assertIn("mode:'markers'", trade_chart.text)
        self.assertIn("annotations", trade_chart.text)
        self.assertIn("scrollZoom:false", trade_chart.text)
        self.assertIn("state.chartHoverValues", trade_chart.text)
        self.assertIn("renderTradeChartV2", trade_chart.text)
        self.assertNotIn("name:'Close'", trade_chart.text)
        self.assertIn("dash:'dot'", trade_chart.text)
        self.assertEqual(chart_export.status_code, 200)
        self.assertIn("trading-wfo-all-charts.png", chart_export.text)
        self.assertIn("saveCanvas", chart_export.text)
        self.assertIn("trading-wfo-all-trades.zip", chart_export.text)
        self.assertIn("Autoscale X &amp; Y axes", chart_export.text)
        self.assertIn("Autoscale Y axes", chart_export.text)
        self.assertIn("Fit X axes", chart_export.text)
        self.assertIn("showSaveFilePicker", chart_export.text)
        self.assertIn("Show cursor values", chart_export.text)
        self.assertIn("canvas[id]", chart_export.text)
        self.assertIn("save-all-charts", index.text)
        self.assertIn("save-all-trades", index.text)
        self.assertNotIn("chart-hover-values", index.text)

    def test_accepts_simulation_result_for_backtest_dashboard(self):
        simulation = {
            "metrics": {
                "initial_balance": 10000,
                "net_profit": 250,
                "return_pct": 2.5,
                "max_drawdown_pct": 1.2,
                "profit_factor": 1.4,
                "win_rate": 55,
                "total_trades": 1,
                "steps_processed": 50,
                "total_steps": 100,
                "progress_pct": 50,
                "status": "running",
            },
            "trades": [{
                "position_id": 1, "time": 1, "exit_time": 2,
                "side": "long", "entry_price": 150, "exit_price": 150.25,
                "realized_profit": 250, "realized_pips": 25,
            }],
            "equity_curve": [
                {"time": 1, "balance": 10000, "equity": 10000},
                {"time": 2, "balance": 10250, "equity": 10250},
            ],
            "rejected_orders": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "backtest.json"
            path.write_text(json.dumps(simulation), encoding="utf-8")
            app = create_dashboard_app(path)
            result = self.get(app, "/api/result")
            script = self.get(app, "/app.js")
            index = self.get(app, "/")

        payload = result.json()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(payload["result_type"], "backtest")
        self.assertEqual(payload["aggregate_metrics"]["net_profit"], 250)
        self.assertEqual(payload["windows"][0]["validation_result"]["trades"], simulation["trades"])
        self.assertIn("applyResultMode", script.text)
        self.assertIn("renderBacktestStatus", script.text)
        self.assertIn("Backtest overview", script.text)
        self.assertIn("data-wfo-only", index.text)
        self.assertIn("data-backtest-only", index.text)

    def test_market_directory_and_log_series_are_available_to_chart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            result_path.write_text(json.dumps(dashboard_payload()), encoding="utf-8")
            market = root / "market" / "USDJPY" / "M15"
            market.mkdir(parents=True)
            market.joinpath("prices.csv").write_text(
                "time,open,high,low,close,bid,ask,volume\n"
                "2026-01-01T00:00:00Z,150,151,149,150.5,150.49,150.51,10\n"
                "2026-01-01T00:15:00Z,150.5,152,150,151,150.99,151.01,20\n"
                "2026-01-01T00:30:00Z,151,153,150.5,152,151.99,152.01,30\n",
                encoding="utf-8",
            )
            logs = root / "logs"
            logs.mkdir()
            logs.joinpath("strategy.csv").write_text(
                "time,rsi,prediction\n"
                "2026-01-01T00:00:00Z,45,0.4\n"
                "2026-01-01T00:15:00Z,55,0.7\n",
                encoding="utf-8",
            )
            app = create_dashboard_app(
                result_path, market_data_directory=market.parent, log_directory=logs
            )
            config = self.get(app, "/api/chart/config")
            candles = self.get(
                app,
                "/api/chart/market?start=1767225600&end=1767227400&timeframe=1800",
            )
            log_rows = self.get(
                app, "/api/chart/logs?start=1767225600&end=1767227400"
            )
            invalid = self.get(
                app,
                "/api/chart/market?start=1767225600&end=1767227400&timeframe=300",
            )
            plotly = self.get(app, "/plotly.min.js")

        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.json()["base_timeframe_seconds"], 900)
        self.assertIn(1800, config.json()["allowed_timeframes"])
        self.assertEqual(config.json()["log_columns"], ["rsi", "prediction"])
        self.assertEqual(candles.status_code, 200)
        self.assertEqual(len(candles.json()["records"]), 2)
        self.assertEqual(candles.json()["records"][0]["high"], 152)
        self.assertEqual(len(log_rows.json()["records"]), 2)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(plotly.status_code, 200)
        self.assertGreater(len(plotly.content), 100_000)

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
