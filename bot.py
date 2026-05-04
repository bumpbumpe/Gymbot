import logging
import os
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from parser import parse_trainer_message, parse_athlete_message
from database import init_db, save_workout_plan, save_workout_result, get_exercises_list
from charts import send_exercise_chart
import subprocess

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "")
TRAINER_USERNAME = os.environ.get("TRAINER_USERNAME", "")  # без @


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    text = message.text
    user = message.from_user
    date = message.date

    # Определяем тип сообщения
    is_trainer = TRAINER_USERNAME and user.username == TRAINER_USERNAME

    if is_trainer:
        plan = parse_trainer_message(text)
        if plan:
            save_workout_plan(plan, date)
            await message.reply_text(
                f"✅ План записан: Цикл {plan['cycle']} Тренировка {plan['workout']}, "
                f"{len(plan['exercises'])} упражнений"
            )
    else:
        result = parse_athlete_message(text)
        if result:
            save_workout_result(result, date, user.username or str(user.id))
            await message.reply_text(
                f"✅ Результат записан: Цикл {result['cycle']} Тренировка {result['workout']}, "
                f"усталость {result.get('fatigue', '?')}/10"
            )


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💪 Gym Memory Bot\n\n"
        "Команды:\n"
        "/progress [упражнение] — график прогресса\n"
        "/exercises — список всех упражнений\n"
        "/stats — сводка за последний месяц\n\n"
        "Просто пишите тренировки в чат — бот всё запишет автоматически."
    )


async def cmd_exercises(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exercises = get_exercises_list()
    if not exercises:
        await update.message.reply_text("Упражнений пока нет в базе.")
        return
    text = "📋 Упражнения в базе:\n\n" + "\n".join(f"• {e}" for e in exercises)
    await update.message.reply_text(text)


async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        exercises = get_exercises_list()
        if exercises:
            await update.message.reply_text(
                "Укажи упражнение:\n/progress жим\n\n"
                "Доступные:\n" + "\n".join(f"• {e}" for e in exercises[:15])
            )
        else:
            await update.message.reply_text("База пустая. Сначала внеси тренировки.")
        return

    query = " ".join(args).lower()
    period = "all"
    
    # Период в конце: /progress жим неделя
    period_words = {"неделя": "week", "месяц": "month", "квартал": "quarter",
                    "полгода": "halfyear", "год": "year"}
    words = query.split()
    if words[-1] in period_words:
        period = period_words[words[-1]]
        query = " ".join(words[:-1])

    await send_exercise_chart(update, query, period)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from database import get_recent_stats
    stats = get_recent_stats(days=30)
    if not stats:
        await update.message.reply_text("Данных за последний месяц нет.")
        return
    
    lines = ["📊 Статистика за 30 дней:\n"]
    for s in stats:
        lines.append(
            f"*{s['exercise']}*\n"
            f"  Тренировок: {s['sessions']}\n"
            f"  Макс вес: {s['max_weight']} кг\n"
            f"  Средний RPE: {s['avg_rpe']:.1f}/10\n"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def main():
    init_db()
        subprocess.run(["python", "seed_db.py"], check=False)
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("exercises", cmd_exercises))
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
