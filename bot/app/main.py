import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from app.config import get_settings
from app.handlers.alert import alert_command
from app.handlers.commands import help_command, start
from app.handlers.fomo import fomo_command, radar_command
from app.handlers.message import handle_message
from app.handlers.wallet import wallet_command
from app.jobs.fomo_leaderboard_alert import fomo_leaderboard_alert_job
from app.jobs.fomo_token_refresh import fomo_token_monitor_job
from app.jobs.fomo_watching_alert import fomo_watching_alert_job
from app.jobs.radar_alert_dispatcher import radar_alert_dispatcher_job
from app.jobs.volume_alert import volume_alert_job
from app.jobs.wallet_tracking_job import wallet_tracking_job
from app.services.fomo_client import FomoClient
from app.services.zerion_client import ZerionClient

logging.basicConfig(level=logging.INFO)

_VOLUME_ALERT_INTERVAL = 300  # 5 minutes
_FOMO_ALERT_INTERVAL = 300  # 5 minutes
_TOKEN_MONITOR_INTERVAL = 300  # 5 minutes
_RADAR_DISPATCH_INTERVAL = 15  # 15 seconds


def main() -> None:
    settings = get_settings()
    request = HTTPXRequest(
        connection_pool_size=20,
        pool_timeout=20.0,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
    )
    get_updates_request = HTTPXRequest(
        connection_pool_size=5,
        pool_timeout=20.0,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
    )
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .request(request)
        .get_updates_request(get_updates_request)
        .build()
    )

    # Pre-load fomo client using full token provider with auto-refresh support
    from app.jobs.fomo_token_refresh import get_token_provider
    import app.handlers.fomo as _fomo_handler
    _fomo_handler._fomo_client = FomoClient(get_token_provider())

    # Pre-load zerion client
    if settings.zerion_api_key:
        import app.handlers.wallet as _wallet_handler
        _wallet_handler._zerion_client = ZerionClient(settings.zerion_api_key)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("alert", alert_command))
    app.add_handler(CommandHandler("fomo", fomo_command))
    app.add_handler(CommandHandler("radar", radar_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
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
        app.job_queue.run_repeating(
            fomo_watching_alert_job,
            interval=_FOMO_ALERT_INTERVAL,
            first=60,
        )
        app.job_queue.run_repeating(
            wallet_tracking_job,
            interval=_FOMO_ALERT_INTERVAL,
            first=90,
        )
        app.job_queue.run_repeating(
            fomo_token_monitor_job,
            interval=_TOKEN_MONITOR_INTERVAL,
            first=15,
        )
        app.job_queue.run_repeating(
            radar_alert_dispatcher_job,
            interval=_RADAR_DISPATCH_INTERVAL,
            first=5,
        )

    app.run_polling()


if __name__ == "__main__":
    main()
