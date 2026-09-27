from telegram import Update
from telegram.ext import ContextTypes

HELP_TEXT = (
    "🤖 *Token Search Bot*\n\n"
    "Gửi địa chỉ contract EVM bất kỳ, bot sẽ tra cứu và trả báo cáo.\n\n"
    "Ví dụ:\n"
    "`0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48`\n\n"
    "Hoặc nhắn kèm text:\n"
    "_\"Kiểm tra token này: 0xA0b86991...\"_\n\n"
    "Hỗ trợ: Ethereum, BSC\n\n"
    "📡 *Volume Alert*\n"
    "`/alert on` — Bật thông báo token volume cao mỗi 5 phút\n"
    "`/alert off` — Tắt thông báo\n"
    "`/alert` — Xem trạng thái\n\n"
    "🏆 *Fomo Leaderboard Alert*\n"
    "`/fomo on` — Bật alert top trader fomo.family\n"
    "`/fomo off` — Tắt alert\n"
    "`/fomo top` — Xem top 10 leaderboard ngay\n"
    "`/fomo watching` — Xem danh sách đang follow + notify trade mới\n"
    "`/fomo token <jwt>` — Cập nhật Privy token\n"
    "`/fomo` — Xem trạng thái\n\n"
    "🔍 *Wallet Tracker (Zerion)*\n"
    "`/wallet <addr>` — Portfolio overview\n"
    "`/wallet txs <addr>` — Lịch sử giao dịch\n"
    "`/wallet track <addr>` — Theo dõi ví (notify trade mới)\n"
    "`/wallet untrack <addr>` — Bỏ theo dõi\n"
    "`/wallet list` — Danh sách ví đang theo dõi"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
