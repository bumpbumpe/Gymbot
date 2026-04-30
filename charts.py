import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from telegram import Update
from database import get_exercise_history


PERIOD_LABELS = {
    "week": "неделя",
    "month": "месяц",
    "quarter": "квартал",
    "halfyear": "полгода",
    "year": "год",
    "all": "всё время",
}


async def send_exercise_chart(update: Update, query: str, period: str = "all"):
    history = get_exercise_history(query, period)

    if not history:
        await update.message.reply_text(
            f"Нет данных по '{query}' за период: {PERIOD_LABELS.get(period, period)}.\n"
            "Попробуй другое название или период."
        )
        return

    exercise_name = history[0]["name"]
    dates = [datetime.strptime(h["date"], "%Y-%m-%d") for h in history]
    weights = [h["weight"] for h in history]
    rpes = [h["rpe"] for h in history]

    has_rpe = any(r is not None for r in rpes)

    # ── figure ────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(
        2 if has_rpe else 1, 1,
        figsize=(10, 7 if has_rpe else 4),
        sharex=True
    )
    fig.patch.set_facecolor("#1a1a2e")

    if not has_rpe:
        axes = [axes]

    ax1 = axes[0]
    ax1.set_facecolor("#16213e")
    ax1.plot(dates, weights, color="#e94560", linewidth=2, marker="o", markersize=5)
    ax1.fill_between(dates, weights, alpha=0.15, color="#e94560")
    ax1.set_ylabel("Рабочий вес, кг", color="#eaeaea", fontsize=11)
    ax1.tick_params(colors="#aaaaaa")
    ax1.spines[:].set_color("#333355")
    ax1.yaxis.label.set_color("#eaeaea")

    # Annotate max
    if weights:
        max_w = max(w for w in weights if w is not None)
        max_idx = next(i for i, w in enumerate(weights) if w == max_w)
        ax1.annotate(
            f"{max_w} кг",
            xy=(dates[max_idx], max_w),
            xytext=(8, 8), textcoords="offset points",
            color="#ffcc00", fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#ffcc00", lw=1),
        )

    if has_rpe:
        ax2 = axes[1]
        ax2.set_facecolor("#16213e")
        rpe_dates = [d for d, r in zip(dates, rpes) if r is not None]
        rpe_vals = [r for r in rpes if r is not None]
        ax2.bar(rpe_dates, rpe_vals, color="#0f3460", width=1.5, edgecolor="#e94560", linewidth=0.5)
        ax2.set_ylim(0, 10)
        ax2.set_ylabel("RPE / 10", color="#eaeaea", fontsize=11)
        ax2.axhline(y=7, color="#ffcc00", linestyle="--", linewidth=0.8, alpha=0.5)
        ax2.tick_params(colors="#aaaaaa")
        ax2.spines[:].set_color("#333355")
        ax2.yaxis.label.set_color("#eaeaea")

    # X axis formatting
    ax_bottom = axes[-1]
    if len(dates) <= 14:
        ax_bottom.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    elif len(dates) <= 60:
        ax_bottom.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax_bottom.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    else:
        ax_bottom.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax_bottom.xaxis.set_major_locator(mdates.MonthLocator())

    plt.setp(ax_bottom.xaxis.get_majorticklabels(), rotation=30, ha="right", color="#aaaaaa")

    period_label = PERIOD_LABELS.get(period, period)
    fig.suptitle(
        f"{exercise_name}\n{period_label} · {len(history)} тренировок",
        color="#eaeaea", fontsize=13, fontweight="bold", y=0.98
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    # ── send ──────────────────────────────────────────────────────────────────
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)

    await update.message.reply_photo(
        photo=buf,
        caption=f"📈 {exercise_name} · {period_label}"
    )
