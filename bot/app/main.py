import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.config import get_settings
from app.handlers.alert import alert_command
from app.handlers.commands import help_command, start
from app.handlers.fomo import fomo_command
from app.handlers.message import handle_message
from app.jobs.fomo_leaderboard_alert import fomo_leaderboard_alert_job
from app.jobs.volume_alert import volume_alert_job
from app.services.fomo_client import FomoClient

logging.basicConfig(level=logging.INFO)

_VOLUME_ALERT_INTERVAL = 300  # 5 minutes
_FOMO_ALERT_INTERVAL = 300  # 5 minutes


def main() -> None:
    settings = get_settings()
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Pre-load fomo client from env token if provided
    if settings.fomo_token:
        import app.handlers.fomo as _fomo_handler
        _fomo_handler._fomo_client = FomoClient(settings.fomo_token)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("alert", alert_command))
    app.add_handler(CommandHandler("fomo", fomo_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if app.job_queue:
        app.job_queue.run_repeating(
            volume_alert_job,
            interval=_VOLUME_ALERT_INTERVAL,
            first=10,
        )
        app.job_queue.run_repeating(
            fomo_leaderboard_alert_job,
            interval=_FOMO_ALERT_INTERVAL,
            first=30,
        )

    app.run_polling()


if __name__ == "__main__":
    main()
