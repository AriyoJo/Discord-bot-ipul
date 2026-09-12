import os
import time
import random
from collections import defaultdict, deque
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
import time
import asyncio

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

# ====== IMAGE SPAM ======
IMAGE_SPAM_LIMIT = 3
IMAGE_SPAM_WINDOW_SECONDS = 30

IMAGE_TIMEOUT_MIN_MINUTES = 10
IMAGE_TIMEOUT_MAX_MINUTES = 60

image_spam_tracker = defaultdict(deque)


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
        synced = await bot.tree.sync()
        print(f"✅ Slash command synced: {len(synced)}")
    except Exception as e:
        print(f"❌ Slash command sync gagal: {e}") 

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
    
    kena_image_spam = await check_image_spam(message)

    if kena_image_spam:
        return
    
    kena_mute = await check_spam(message)

    if kena_mute:
        return

    if message.mention_everyone and "@everyone" in message.content:
        await message.channel.send("Aja sendiri")

    if message.content.lower().strip() == "mole":
        await message.channel.send("Aja Sendiri")
    
    if message.content.lower().strip() == "valo":
        await message.channel.send("Aja Sendiri")

    if message.content.lower().strip() == "login":
        await message.channel.send("Aja Sendiri")

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
async def pul(ctx):
    await ctx.send("Nape?")


@bot.command()
async def dadu(ctx):
    angka = random.randint(1, 6)
    await ctx.send(f"🎲 Kamu mendapatkan angka: **{angka}**")


@bot.command()
async def sini(ctx):
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
async def yapping(ctx, jumlah: int = 10):
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

@tasks.loop(minutes=5)
async def voice_xp():
    for guild in bot.guilds:
        for channel in guild.voice_channels:
            members = [m for m in channel.members if not m.bot]

            if len(members) < 2:
                continue

            for member in members:

                if member.voice and member.voice.self_deaf:
                    continue
                
                xp_gain = random.randint(3, 7)
                now = int(time.time())

                result = await db.add_xp(
                    guild.id,
                    member.id,
                    xp_gain,
                    now
                )

                if result["leveled_up"]:
                    await give_level_roles(
                        member,
                        result["new_level"]
                    )

@bot.command()
async def status(ctx):
    gateway_latency = round(bot.latency * 1000)

    rest_start = time.perf_counter()
    msg = await ctx.send("Sabar ngecek cik")
    rest_latency = round((time.perf_counter() - rest_start) * 1000)

    db_start = time.perf_counter()
    await db.db.command("ping")
    db_latency = round((time.perf_counter() - db_start) * 1000)

    embed = discord.Embed(
        title="Bot Status",
        color=discord.Color.green()
    )

    embed.add_field(
        name="Discord Gateway",
        value=f"`{gateway_latency} ms`",
        inline=False
    )

    embed.add_field(
        name="Discord REST",
        value=f"`{rest_latency} ms`",
        inline=False
    )

    embed.add_field(
        name="Database",
        value=f"`{db_latency} ms`",
        inline=False
    )

    await msg.edit(
        content=None,
        embed=embed
    )

# =========================================================
# GIVEAWAY SYSTEM
# =========================================================


def parse_duration(value: str):
    """
    Mengubah input durasi menjadi detik.

    Contoh:
    30s -> 30 detik
    10m -> 600 detik
    2h  -> 7200 detik
    1d  -> 86400 detik
    """

    value = value.lower().strip()

    if len(value) < 2:
        return None

    angka = value[:-1]
    satuan = value[-1]

    if not angka.isdigit():
        return None

    angka = int(angka)

    if angka <= 0:
        return None

    if satuan == "s":
        return angka

    if satuan == "m":
        return angka * 60

    if satuan == "h":
        return angka * 60 * 60

    if satuan == "d":
        return angka * 60 * 60 * 24

    return None


async def ask_question(ctx, pertanyaan: str, timeout=120):
    """
    Bot mengirim pertanyaan lalu menunggu jawaban
    dari operator yang sama dan channel yang sama.
    """

    await ctx.send(pertanyaan)

    def check(message):
        return (
            message.author.id == ctx.author.id
            and message.channel.id == ctx.channel.id
            and not message.author.bot
        )

    try:
        message = await bot.wait_for(
            "message",
            check=check,
            timeout=timeout
        )

        return message.content.strip()

    except asyncio.TimeoutError:
        return None

class GiveawayView(discord.ui.View):
    def __init__(self, required_role=None):
        super().__init__(timeout=None)

        self.required_role = required_role
        self.entries = set()

    @discord.ui.button(
        label="Join Giveaway",
        style=discord.ButtonStyle.success,
        emoji="🎉"
    )
    async def join_giveaway(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        member = interaction.user

        # Kalau ada requirement role
        if self.required_role is not None:
            if self.required_role not in member.roles:
                await interaction.response.send_message(
                    "❌ Kamu tidak memiliki requirement untuk giveaway ini.",
                    ephemeral=True
                )
                return

        # Kalau user sudah join
        if member.id in self.entries:
            await interaction.response.send_message(
                "⚠️ Kamu sudah ikut giveaway ini.",
                ephemeral=True
            )
            return

        # Masukkan user ke peserta
        self.entries.add(member.id)

        await interaction.response.send_message(
            "✅ Kamu berhasil ikut giveaway!",
            ephemeral=True
        )

giveaway_sessions = set()


@bot.hybrid_command(
    name="giveaway",
    description="Membuat giveaway baru"
)
@commands.has_permissions(manage_messages=True)
async def giveaway(ctx):

    user_id = ctx.author.id

    if user_id in giveaway_sessions:
        await ctx.send(
            "⚠️ Kamu masih punya setup giveaway yang sedang berjalan."
        )
        return

    giveaway_sessions.add(user_id)

    try:
        hadiah = await ask_question(
            ctx,
            "🎁 **Hadiahnya apa tu?**\n"
            "Contoh: `robak`"
        )

        if hadiah is None:
            await ctx.send(
                "⏰ kebanyakan mikir"
            )
            return

        if hadiah.lower() == "cancel":
            await ctx.send("❌ Giveaway dibatalkan.")
            return

    finally:
        giveaway_sessions.discard(user_id)

    while True:

        durasi_input = await ask_question(
            ctx,
            "⏱️ **Lama ga?**\n\n"
            "Contoh:\n"
            "`30s` = 30 detik\n"
            "`10m` = 10 menit\n"
            "`2h` = 2 jam\n"
            "`1d` = 1 hari"
        )

        if durasi_input is None:
            await ctx.send(
                "⏰ Gada yg dateng jir"
            )
            return

        if durasi_input.lower() == "cancel":
            await ctx.send("❌ Keciwir.")
            return

        durasi_detik = parse_duration(durasi_input)

        if durasi_detik is not None:
            break

        await ctx.send(
            "❌ **Diliat bloon**\n"
            "Contoh: `10m`, `2h`, `30s`, atau `1d`."
        )

    while True:

        winner_input = await ask_question(
            ctx,
            "🏆 **Berapa yg menang kira kira**\n"
            "Contoh: `1`"
        )

        if winner_input is None:
            await ctx.send(
                "⏰ kebanyakan mikir"
            )
            return

        if winner_input.lower() == "cancel":
            await ctx.send("❌ Giveaway dibatalkan.")
            return

        if winner_input.isdigit():

            jumlah_pemenang = int(winner_input)

            if jumlah_pemenang > 0:
                break

        await ctx.send(
            "❌ Yg bener masukinya kocak\n"
            "Contoh: `1`, `2`, atau `3`."
        )
        
    while True:
        requirement_input = await ask_question(
            ctx,
            "📋 **Pake role ga?**\n\n"
            "Mau role apa?\n"
            "Contoh: `@Ertege`\n\n"
            "Ketik `-` jika tidak ada requirement."
        )

        if requirement_input is None:
            await ctx.send(
                "⏰ Kebanyakan Mikir"
            )
            return

        if requirement_input.lower() == "cancel":
            await ctx.send("❌ Giveaway dibatalkan.")
            return

        if requirement_input == "-":
            required_role = None
            requirement_text = "None"
            break


        if requirement_input.startswith("<@&") and requirement_input.endswith(">"):
            try:
                role_id = int(
                    requirement_input
                    .replace("<@&", "")
                    .replace(">", "")
                )

                required_role = ctx.guild.get_role(role_id)

                if required_role is not None:
                    requirement_text = required_role.mention
                    break

            except ValueError:
                pass

        await ctx.send(
            "❌ **Role Gada jing**\n"
            "Mention role Discord, contoh `@Atmin`, "
            "atau ketik `-` jika tidak ada restriction."
        )


    preview = discord.Embed(
        title="🎉 Giveaway Preview",
        description=(
            f"## 🎁 {hadiah}\n\n"
            f"**Duration:** {durasi_input}\n"
            f"**Winners:** {jumlah_pemenang}\n"
            f"**Requirement:** {requirement_text}"
        ),
        color=discord.Color.gold()
    )

    await ctx.send(embed=preview)

    konfirmasi = await ask_question(
        ctx,
        "✅ **Buat giveaway ini?**\n"
        "Ketik `yes` untuk membuat atau `no` untuk membatalkan."
    )

    if konfirmasi is None:
        await ctx.send(
            "⏰ Setup giveaway dibatalkan."
        )
        return

    if konfirmasi.lower() not in ["yes", "y", "ya"]:
        await ctx.send("❌ Giveaway dibatalkan.")
        return

    end_timestamp = int(time.time()) + durasi_detik

    giveaway_embed = discord.Embed(
        description=(
            "# 🎉 Giveaway\n\n"
            f"## {hadiah}\n\n"
            "Klik tombol **Join Giveaway** untuk ikut!\n\n"
            f"**Host:** {ctx.author.mention}\n"
            f"**Winners:** {jumlah_pemenang}\n"
            f"**Requirement:** {requirement_text}\n"
            f"**Ends:** <t:{end_timestamp}:R>"
        ),
        color=discord.Color.gold()
    )

    view = GiveawayView(
        required_role=required_role
    )

    giveaway_message = await ctx.send(
        embed=giveaway_embed,
        view=view
    )

    giveaway_id = giveaway_message.id


    giveaway_embed.description = (
        "# 🎉 Giveaway\n\n"
        f"## {hadiah}\n\n"
        "Klik tombol **Join Giveaway** untuk ikut!\n\n"
        f"**Host:** {ctx.author.mention}\n"
        f"**Winners:** {jumlah_pemenang}\n"
        f"**Giveaway ID:** `{giveaway_id}`\n"
        f"**Requirement:** {requirement_text}\n"
        f"**Ends:** <t:{end_timestamp}:R>"
    )

    await giveaway_message.edit(
        embed=giveaway_embed,
        view=view
    )

    await asyncio.sleep(durasi_detik)

    try:
        giveaway_message = await ctx.channel.fetch_message(
            giveaway_id
        )
    except discord.NotFound:
        return

    peserta = []

    for user_id in view.entries:

        member = ctx.guild.get_member(user_id)

        if member is not None:
            peserta.append(member)

    jumlah_entries = len(peserta)

    if jumlah_entries == 0:

        winners_text = "No winner."

    else:

        jumlah_final = min(
            jumlah_pemenang,
            jumlah_entries
        )

        winners = random.sample(
            peserta,
            jumlah_final
        )

        winners_text = "\n".join(
            winner.mention
            for winner in winners
        )

    ended_timestamp = int(time.time())

    ended_embed = discord.Embed(
        description=(
            "# 🎉 Giveaway\n\n"
            f"## {hadiah}\n\n"
            "This giveaway has ended.\n\n"
            f"**Host:** {ctx.author.mention}\n"
            f"**Winners:** {jumlah_pemenang}\n"
            f"**Entries:** {jumlah_entries}\n"
            f"**Giveaway ID:** `{giveaway_id}`\n"
            f"**Requirement:** {requirement_text}\n"
            f"**Ended:** <t:{ended_timestamp}:R>\n\n"
            "## Winners\n"
            f"{winners_text}"
        ),
        color=discord.Color.dark_grey()   
    )

    for item in view.children:
        item.disabled = True

    await giveaway_message.edit(
        embed=ended_embed,
        view=view
    )

    if jumlah_entries > 0:

        await ctx.send(
            f"🎉 **Giveaway {hadiah} selesai!**\n\n"
            f"🏆 Winner:\n{winners_text}"
        )

    else:

        await ctx.send(
            f"Giveaway **{hadiah}** selesai, "
            "sedih ngafs gada yg ikut."
        )




@giveaway.error
async def giveaway_error(ctx, error):

    if isinstance(
        error,
        commands.MissingPermissions
    ):

        await ctx.send(
            "❌ Mampus gabisa bikin "
            "**Manage Messages** untuk membuat giveaway."
        )

    else:

        print(
            f"[GIVEAWAY ERROR] "
            f"{type(error).__name__}: {error}"
        )

@bot.hybrid_command(
    name="servers",
    description="Melihat server yang dimasuki bot"
)
async def servers(ctx):
    daftar = "\n".join(
        f"{guild.name} | `{guild.id}`"
        for guild in bot.guilds
    )

    await ctx.send(
        f"Bot ada di {len(bot.guilds)} server:\n{daftar}"
    )
    
async def check_image_spam(message: discord.Message) -> bool:
    if message.guild is None:
        return False
    
    if message.author.bot:
        return False

    images = [
        attachment
        for attachment in message.attachments
        if attachment.content_type
        and attachment.content_type.startswith("image/")
    ]

    if not images:
        return False
    
    key = (
        message.guild.id,
        message.author.id
    )

    now = time.time()

    timetamps = image_spam_tracker[key]

    while (
        timetamps
        and now - timetamps[0] > IMAGE_SPAM_WINDOW_SECONDS
    ):
        timetamps.popleft()
    
    for _ in images:
        timetamps.append(now)

    if len(timetamps) <= IMAGE_SPAM_LIMIT:
        return False
    
    timeout_minutes = random.randint(
        IMAGE_TIMEOUT_MIN_MINUTES,
        IMAGE_TIMEOUT_MAX_MINUTES
    )

    try:
        await message.author.timeout(
            timedelta(minutes=timeout_minutes),
            reason="Image spam"
        )

        await message.channel.send(
            f"🔇 {message.author.mention} timeout"
            f"**{timeout_minutes} menit ** spam gambar"
        )

        timetamps.clear()

        return True
    
    except discord.Forbidden:
        await message.channel.send(
            f"{message.author.mention} jan spam woi,"
            "gw gapunya permission buat timeout"
        )

        timetamps.clear()
        return False 

# Jalankan bot
if TOKEN is None:
    raise RuntimeError(
        "DISCORD_TOKEN tidak ditemukan. Pastikan file .env ada dan berisi DISCORD_TOKEN=token_kamu"
    )
bot.run(TOKEN)