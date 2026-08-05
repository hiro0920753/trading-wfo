import argparse
from pathlib import Path


def build_parser():
    parser = argparse.ArgumentParser(prog="trading-wfo")
    subcommands = parser.add_subparsers(dest="command", required=True)
    dashboard = subcommands.add_parser(
        "dashboard", help="view a saved WFO JSON result in a local browser"
    )
    dashboard.add_argument(
        "--result",
        type=Path,
        default=Path("results/wfo_result.json"),
        help="path to WalkForwardResult or SimulationResult JSON",
    )
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8000)
    dashboard.add_argument(
        "--market-data-dir",
        type=Path,
        help="directory containing market CSV files for Trade Inspector charts",
    )
    dashboard.add_argument(
        "--log-dir",
        type=Path,
        help="directory containing time-series CSV logs",
    )
    dashboard.add_argument(
        "--progress-file", type=Path,
        help="live ProgressTracker JSON (default: RESULT.progress.json)",
    )
    dashboard.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow binding to a non-loopback host",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "dashboard":
        if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote:
            raise SystemExit(
                "refusing non-local host; pass --allow-remote explicitly"
            )
        from uvicorn import run

        from .dashboard import create_dashboard_app

        try:
            app = create_dashboard_app(
                args.result,
                market_data_directory=args.market_data_dir,
                log_directory=args.log_dir,
                progress_path=args.progress_file,
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error
        print(f"Dashboard: http://{args.host}:{args.port}")
        print(f"Result: {args.result.resolve()}")
        if args.market_data_dir:
            print(f"Market data: {args.market_data_dir.resolve()}")
        if args.log_dir:
            print(f"Logs: {args.log_dir.resolve()}")
        if args.progress_file:
            print(f"Progress: {args.progress_file.resolve()}")
        run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
