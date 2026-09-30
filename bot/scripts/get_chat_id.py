import asyncio
import sys
from pathlib import Path

BOT_DIR = Path(__file__).resolve().parent.parent
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from telegram import Bot
from app.config import get_settings


async def main():
    settings = get_settings()
    bot = Bot(token=settings.telegram_bot_token)
    me = await bot.get_me()
    print(f"[*] Bot: @{me.username} (ID: {me.id})")
    print("[*] Đang lắng nghe tin nhắn từ Telegram... Hãy gửi một tin nhắn vào bot hoặc group đã add bot.")
    
    offset = 0
    for _ in range(30):
        try:
            updates = await bot.get_updates(offset=offset, timeout=2)
            for u in updates:
                offset = u.update_id + 1
                chat = None
                if u.message:
                    chat = u.message.chat
                    text = u.message.text
                    sender = u.message.from_user.username if u.message.from_user else "unknown"
                    print(f"\n[+] Nhận tin nhắn từ @{sender}: '{text}'")
                elif u.my_chat_member:
                    chat = u.my_chat_member.chat
                    print(f"\n[+] Bot được cập nhật quyền trong: {chat.title}")
                elif u.channel_post:
                    chat = u.channel_post.chat
                    print(f"\n[+] Channel post trong: {chat.title}")
                
                if chat:
                    print(f"    👉 CHAT_ID CHÍNH XÁC LÀ: {chat.id}")
                    print(f"    👉 Loại: {chat.type} | Tên: {chat.title or chat.first_name}")
                    print(f"    👉 Cập nhật vào .env: ADMIN_CHAT_ID={chat.id}")
                    return
        except Exception as e:
            print("Error polling:", e)
        await asyncio.sleep(1)
    print("[-] Hết thời gian chờ (30s). Hãy đảm bảo đã chat với bot hoặc add bot vào group.")


if __name__ == "__main__":
    asyncio.run(main())
