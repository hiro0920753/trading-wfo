import math


def calculate_metrics(*, initial_balance, final_balance, trades, equity_curve):
    profits = [float(trade["realized_profit"]) for trade in trades]
    gross_profit = sum(profit for profit in profits if profit > 0)
    gross_loss = abs(sum(profit for profit in profits if profit < 0))
    winning_trades = sum(profit > 0 for profit in profits)
    losing_trades = sum(profit < 0 for profit in profits)
    total_trades = len(profits)
    net_profit = float(final_balance) - float(initial_balance)

    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    peak = float(initial_balance)
    for point in equity_curve:
        equity = float(point["equity"])
        peak = max(peak, equity)
        drawdown = peak - equity
        drawdown_pct = 0.0 if peak == 0 else drawdown / peak * 100
        max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = math.inf
    else:
        profit_factor = 0.0

    return {
        "initial_balance": float(initial_balance),
        "final_balance": float(final_balance),
        "net_profit": net_profit,
        "return_pct": (
            0.0
            if initial_balance == 0
            else net_profit / float(initial_balance) * 100
        ),
        "total_trades": total_trades,
        "winning_trades": winning_trades,
        "losing_trades": losing_trades,
        "win_rate": (
            0.0 if total_trades == 0 else winning_trades / total_trades * 100
        ),
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "max_drawdown_pct": max_drawdown_pct,
    }
