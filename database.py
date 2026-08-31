import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load .env di sini juga, supaya tidak tergantung urutan import di main.py/test_db.py
load_dotenv()

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI tidak ditemukan. Pastikan file .env berisi MONGO_URI=mongodb+srv://..."
    )

client = AsyncIOMotorClient(MONGO_URI)
db = client["discord_bot"]
levels_col = db["levels"]


def xp_needed_for_level(level: int) -> int:
    """XP yang dibutuhkan untuk naik dari `level` ke level berikutnya."""
    return int(100 * (level + 1) ** 1.5)


async def get_user(guild_id: int, user_id: int) -> dict:
    guild_id, user_id = str(guild_id), str(user_id)
    user = await levels_col.find_one({"guild_id": guild_id, "user_id": user_id})
    if user is None:
        user = {
            "guild_id": guild_id,
            "user_id": user_id,
            "xp": 0,
            "level": 0,
            "last_message_ts": 0,
        }
        await levels_col.insert_one(user)
    return user


async def add_xp(guild_id: int, user_id: int, amount: int, timestamp: int) -> dict:
    """Tambah XP ke user. Mengembalikan info level up."""
    user = await get_user(guild_id, user_id)
    xp = max(0, user["xp"] + amount)
    level = user["level"]
    old_level = level

    needed = xp_needed_for_level(level)
    while xp >= needed:
        xp -= needed
        level += 1
        needed = xp_needed_for_level(level)

    await levels_col.update_one(
        {"guild_id": str(guild_id), "user_id": str(user_id)},
        {"$set": {"xp": xp, "level": level, "last_message_ts": timestamp}},
    )

    return {
        "leveled_up": level > old_level,
        "old_level": old_level,
        "new_level": level,
        "xp": xp,
        "xp_needed": needed,
    }


async def set_level(guild_id: int, user_id: int, level: int):
    await get_user(guild_id, user_id)  # pastikan dokumen ada
    await levels_col.update_one(
        {"guild_id": str(guild_id), "user_id": str(user_id)},
        {"$set": {"level": level, "xp": 0}},
    )


async def get_leaderboard(guild_id: int, limit: int = 10):
    cursor = levels_col.find({"guild_id": str(guild_id)}).sort(
        [("level", -1), ("xp", -1)]
    ).limit(limit)
    return await cursor.to_list(length=limit)


async def get_rank_position(guild_id: int, level: int, xp: int) -> int:
    count = await levels_col.count_documents(
        {
            "guild_id": str(guild_id),
            "$or": [
                {"level": {"$gt": level}},
                {"level": level, "xp": {"$gt": xp}},
            ],
        }
    )
    return count + 1
