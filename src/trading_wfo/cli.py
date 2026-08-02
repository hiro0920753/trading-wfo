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
        help="path to WalkForwardResult JSON",
    )
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8000)
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

        app = create_dashboard_app(args.result)
        print(f"Dashboard: http://{args.host}:{args.port}")
        print(f"Result: {args.result.resolve()}")
        run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
