import os
import time
import random
from collections import defaultdict
from datetime import timedelta
import aiohttp
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
from google import genai
import database as db
import tiktok_watcher

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=GEMINI_API_KEY
)

app = Flask('')


@app.route('/')
def home():
    return "Bot Discord Aktif 24/7"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

keep_alive()


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ====== KONFIGURASI ======
XP_MIN = 15              
XP_MAX = 25               
XP_COOLDOWN_SECONDS = 60  

# ====== KONFIGURASI ANTI-SPAM ======
SPAM_WARNING_COUNT = 3        
SPAM_MUTE_COUNT = 5           
SPAM_TIME_WINDOW_SECONDS = 20 
SPAM_MUTE_DURATION_MINUTES = 10  

# ====== KONFIGURASI NOTIFIKASI TIKTOK ======
TIKTOK_USERNAME = "poiloristo"    
TIKTOK_NOTIFY_CHANNEL_ID = 1537375115149578252   
TIKTOK_CHECK_INTERVAL_MINUTES = 15                 


LEVEL_ROLES = {
    10: 1527384406917124316,
    20: 1533494275420066022,
    50: 1537386450146951218,
}


intents = discord.Intents.default()
intents.message_content = True
intents.members = True 

bot = commands.Bot(command_prefix="!", intents=intents)


async def give_level_roles(member: discord.Member, level: int) -> list[str]:
    """
    Beri semua role reward yang levelnya <= level member saat ini dan belum dimiliki.
    Mengembalikan daftar nama role yang baru diberikan (untuk ditampilkan di pesan).
    """
    diberikan = []
    for role_level, role_id in LEVEL_ROLES.items():
        if level < role_level:
            continue
 
        role = member.guild.get_role(role_id)
        if role is None:
            print(f"[Peringatan] Role dengan ID {role_id} tidak ditemukan di server {member.guild.name}.")
            continue
 
        if role not in member.roles:
            try:
                await member.add_roles(role, reason=f"Mencapai level {level}")
                diberikan.append(role.name)
            except discord.Forbidden:
                print(f"[Peringatan] Bot tidak punya izin memberi role '{role.name}'. Cek posisi role bot.")
 
    return diberikan



spam_tracker = defaultdict(lambda: {"content": None, "count": 0, "last_ts": 0.0, "warned": False})


async def check_spam(message: discord.Message) -> bool:
    """
    Cek apakah pesan ini bagian dari rentetan spam (pesan sama berulang, lintas channel).
    Mengirim peringatan di hitungan ke-SPAM_WARNING_COUNT, dan mute di hitungan ke-SPAM_MUTE_COUNT.
    Return True kalau user baru saja kena mute (supaya caller tahu untuk menghentikan proses lain).
    """
    content = message.content.strip().lower()
    if not content:
        return False

    now = time.time()
    state = spam_tracker[message.author.id]


    if content != state["content"] or (now - state["last_ts"]) > SPAM_TIME_WINDOW_SECONDS:
        state["content"] = content
        state["count"] = 1
        state["warned"] = False
        state["last_ts"] = now
        return False

 
    state["count"] += 1
    state["last_ts"] = now

    if state["count"] >= SPAM_MUTE_COUNT:
        state["count"] = 0
        state["warned"] = False

        member = message.author
        try:
            await member.timeout(
                timedelta(minutes=SPAM_MUTE_DURATION_MINUTES),
                reason="Brisik woi jan spam",
            )
            await message.channel.send(
                f"🔇 {member.mention} di-**mute selama {SPAM_MUTE_DURATION_MINUTES} menit** "
                f"MAMPUS GW MUTE AJG."
            )
        except discord.Forbidden:
            await message.channel.send(
                f"⚠️ Terdeteksi spam dari {member.mention}, tapi bot tidak punya izin untuk mute. "
                f"Cek permission **Moderate Members** dan posisi role bot."
            )
        return True

    if state["count"] >= SPAM_WARNING_COUNT and not state["warned"]:
        state["warned"] = True
        await message.channel.send(
            f"⚠️ {message.author.mention}, diam atau aku mute. "
        )

    return False

@bot.event
async def on_ready():
    print(f"Bot berhasil login sebagai {bot.user}")

    try:
        await db.client.admin.command('ping')
        print("🟢 MongoDb: Berhasil")
    except Exception as e:
        print(f"🔴 MongoDB: Gagal, Error:{e}")

    if not check_tiktok.is_running():
        check_tiktok.start()



_last_video_id = None
_was_live = False


@tasks.loop(minutes=TIKTOK_CHECK_INTERVAL_MINUTES)
async def check_tiktok():
    global _last_video_id, _was_live

    channel = bot.get_channel(TIKTOK_NOTIFY_CHANNEL_ID)
    if channel is None:
        print("[TikTok] Channel notifikasi tidak ditemukan. Cek TIKTOK_NOTIFY_CHANNEL_ID.")
        return

    print(f"[TikTok] Mengecek @{TIKTOK_USERNAME}...")

    async with aiohttp.ClientSession() as session:
        video = await tiktok_watcher.get_latest_video(session, TIKTOK_USERNAME)
        if video is None:
            print("[TikTok] Gagal mengambil data video (lihat error di atas kalau ada).")
        elif _last_video_id is None:
            _last_video_id = video["id"]
            print(f"[TikTok] Baseline diset ke video ID {video['id']} (video ini TIDAK akan dinotif).")
        elif video["id"] != _last_video_id:
            _last_video_id = video["id"]
            print(f"[TikTok] Video baru terdeteksi: {video['id']}")
            embed = discord.Embed(
                title="🎬 Postingan TikTok baru!",
                description=video["desc"],
                url=video["url"],
                color=discord.Color.from_rgb(255, 0, 80),
            )
            embed.set_footer(text=f"@{TIKTOK_USERNAME}")
            await channel.send(embed=embed)
        else:
            print(f"[TikTok] Tidak ada video baru (masih ID {video['id']}).")

        live_now = await tiktok_watcher.is_live(session, TIKTOK_USERNAME)
        print(f"[TikTok] Status live: {live_now}")
        if live_now and not _was_live:
            await channel.send(
                f"🔴 **@{TIKTOK_USERNAME} sedang LIVE di TikTok sekarang!**\n"
                f"https://www.tiktok.com/@{TIKTOK_USERNAME}/live"
            )
        _was_live = live_now


@check_tiktok.before_loop
async def before_check_tiktok():
    await bot.wait_until_ready()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        await bot.process_commands(message)
        return

    if message.mention_everyone and "@everyone" in message.content:
        await message.channel.send("Aja sendiri")

    kena_mute = await check_spam(message)
    if kena_mute:
        return 
    user = await db.get_user(message.guild.id, message.author.id)
    now = int(time.time())

    if now - user["last_message_ts"] >= XP_COOLDOWN_SECONDS:
        xp_gain = random.randint(XP_MIN, XP_MAX)
        result = await db.add_xp(message.guild.id, message.author.id, xp_gain, now)

        if result["leveled_up"]:
            embed = discord.Embed(
                description=f"🎉 Anjay {message.author.mention}, lu naik ke **Level {result['new_level']}**!",
                color=discord.Color.green(),
            )
            await message.channel.send(embed=embed)

            role_baru = await give_level_roles(message.author, result["new_level"])
            if role_baru:
                await message.channel.send(
                    f"🎁 {message.author.mention} Nih gw kasih role: **{', '.join(role_baru)}**"
                )

    await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    await ctx.send("Nape?")


@bot.command()
async def dadu(ctx):
    angka = random.randint(1, 6)
    await ctx.send(f"🎲 Kamu mendapatkan angka: **{angka}**")


@bot.command()
async def join(ctx):
    """Panggil bot masuk ke voice channel yang sedang kamu tempati. Contoh: !join"""
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("Lumasuk dulu kocak.")
        return
 
    channel = ctx.author.voice.channel
    voice_client = ctx.guild.voice_client
 
    try:
        if voice_client is None:
            await channel.connect()
            await ctx.send(f"🔊 Bot bergabung ke **{channel.name}**.")
        elif voice_client.channel.id != channel.id:
            await voice_client.move_to(channel)
            await ctx.send(f"🔊 Bot pindah ke **{channel.name}**.")
        else:
            await ctx.send(f"Bot sudah ada di **{channel.name}**.")
    except discord.Forbidden:
        await ctx.send("Gw gabisa masuk ke channel itu kocak")
    except discord.ClientException as e:
        await ctx.send(f"Ga bisa le: {e}")
 
 
@bot.command()
async def leave(ctx):
    """Keluarkan bot dari voice channel. Contoh: !leave"""
    voice_client = ctx.guild.voice_client
    if voice_client is None:
        await ctx.send("Gw kaga masuk channel woi.")
        return
 
    await voice_client.disconnect()
    await ctx.send("Cabut lah")


@bot.command()
async def rank(ctx, member: discord.Member = None):
    """Cek level dan XP diri sendiri atau member lain. Contoh: !rank @nama"""
    target = member or ctx.author
    user = await db.get_user(ctx.guild.id, target.id)
    xp_needed = db.xp_needed_for_level(user["level"])
    position = await db.get_rank_position(ctx.guild.id, user["level"], user["xp"])

    bar_length = 20
    filled = round((user["xp"] / xp_needed) * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)

    embed = discord.Embed(
        title=f"Peringkat #{position}",
        color=discord.Color.blurple(),
    )
    embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
    embed.add_field(name="Level", value=str(user["level"]), inline=True)
    embed.add_field(name="XP", value=f"{user['xp']} / {xp_needed}", inline=True)
    embed.add_field(name="Progress", value=bar, inline=False)
    embed.set_thumbnail(url=target.display_avatar.url)

    await ctx.send(embed=embed)


@bot.command()
async def leaderboard(ctx, jumlah: int = 10):
    """Lihat papan peringkat level server ini. Contoh: !leaderboard 15"""
    jumlah = min(jumlah, 25)
    rows = await db.get_leaderboard(ctx.guild.id, jumlah)

    if not rows:
        await ctx.send("Malas gada leiderbrot")
        return

    medali = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(rows):
        label = medali[i] if i < 3 else f"**{i + 1}.**"
        member = ctx.guild.get_member(int(row["user_id"]))
        nama = member.display_name if member else f"Pengguna ({row['user_id']})"
        lines.append(f"{label} {nama} — Level {row['level']} ({row['xp']} XP)")

    embed = discord.Embed(
        title=f"🏆 Papan Yapping — {ctx.guild.name}",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    await ctx.send(embed=embed)


ADMIN_ROLE_NAME = 1411476274224042115 


@bot.command()
@commands.has_role(ADMIN_ROLE_NAME)
async def setlevel(ctx, member: discord.Member, level: int):
    """[Admin] Atur level member secara manual. Contoh: !setlevel @nama 5"""
    await db.set_level(ctx.guild.id, member.id, level)
    await ctx.send(f"✅ Level {member.mention} telah diatur ke **{level}**.")

    role_baru = await give_level_roles(member, level)
    if role_baru:
        await ctx.send(f"🎁 {member.mention} mendapatkan role: **{', '.join(role_baru)}**")


@setlevel.error
async def setlevel_error(ctx, error):
    if isinstance(error, (commands.MissingRole, commands.MissingAnyRole, commands.MissingPermissions)):
        await ctx.send(f"Lu butuh **{ADMIN_ROLE_NAME}** Buat ngebabu gw.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Isi member dulu kocak")


@bot.command()
@commands.has_role(ADMIN_ROLE_NAME)
async def addxp(ctx, member: discord.Member, jumlah: int):
    """[Admin] Tambah XP member secara manual. Contoh: !addxp @nama 50 (bisa negatif untuk mengurangi)"""
    result = await db.add_xp(ctx.guild.id, member.id, jumlah, int(time.time()))

    await ctx.send(f"✅ Menambahkan **{jumlah} XP** ke {member.mention}.")

    if result["leveled_up"]:
        embed = discord.Embed(
            description=f"🎉 Cihuy {member.mention}, kamu naik ke **Level {result['new_level']}**!",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

        role_baru = await give_level_roles(member, result["new_level"])
        if role_baru:
            await ctx.send(f"🎁 {member.mention} mendapatkan role: **{', '.join(role_baru)}**")


@addxp.error
async def addxp_error(ctx, error):
    if isinstance(error, (commands.MissingRole, commands.MissingAnyRole, commands.MissingPermissions)):
        await ctx.send(f"Lu butuh **{ADMIN_ROLE_NAME}** Buat ngebabu gw.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Isi member dulu woi")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Taro angka nyak. Contoh: `!addxp @nama 50`")

@bot.command()
async def ipul(ctx, *, pertanyaan):
    try:
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=pertanyaan
    )

    jawaban = response.text

    for i in range(0, len(jawaban), 1900):
        await ctx.send(jawaban[i:i+1900])

    except Exception as e:
        print(f"[AI ERROR] {type(e).__name__}: {e}")
        await ctx.send("Ai error, bntr dah")

# Jalankan bot
if TOKEN is None:
    raise RuntimeError(
        "DISCORD_TOKEN tidak ditemukan. Pastikan file .env ada dan berisi DISCORD_TOKEN=token_kamu"
    )

bot.run(TOKEN)