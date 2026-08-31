import asyncio
import time
import database as db

async def test_insert():
    print("⏳ Mengirim data tes ke MongoDB...")
    # Mencoba menambah XP untuk user dummy
    result = await db.add_xp(guild_id="12345", user_id="67890", amount=50, timestamp=int(time.time()))
    print(f"✅ Data tes BERHASIL dikirim ke MongoDB! Hasil: {result}")

asyncio.run(test_insert())