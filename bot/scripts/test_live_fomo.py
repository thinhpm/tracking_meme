import asyncio
from pathlib import Path
import sys

BOT_DIR = Path(__file__).resolve().parent.parent
if str(BOT_DIR) not in sys.path:
    sys.path.insert(0, str(BOT_DIR))

from app.config import get_settings
from app.services.fomo_client import FomoClient, FomoTokenProvider

async def test():
    settings = get_settings()
    provider = FomoTokenProvider(fallback_token=settings.fomo_token)
    client = FomoClient(provider)
    print("Testing live get_leaderboard(limit=3)...")
    traders = await client.get_leaderboard(limit=3)
    print(f"Fetched {len(traders)} traders from Fomo API!")
    for t in traders:
        print(f"  #{t.rank}: @{t.user_handle} ({t.display_name}) | Sol: {t.address} | PnL: ${t.total_pnl:,.2f} | Volume: ${t.total_volume:,.2f}")

    if traders:
        top_trader_id = traders[0].id
        print(f"\nTesting live get_user_following_paginate for trader #{traders[0].rank} (@{traders[0].user_handle})...")
        following = await client.get_user_following_paginate(top_trader_id, page=1, limit=5)
        print(f"Fetched {len(following)} followed users!")
        for u in following:
            print(f"  - @{u.user_handle} ({u.display_name}) | Sol Addr: {u.address} | Badge: {u.badge} | PnL 24h: ${u.pnl24h:,.2f}")

if __name__ == "__main__":
    asyncio.run(test())
