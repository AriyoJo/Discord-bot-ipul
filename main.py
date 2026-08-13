import os
import time
import random
from collections import defaultdict
from datetime import timedelta
import discord
from discord.ext import commands
from dotenv import load_dotenv

import database as db

# Muat token dari file .env (jangan pernah taruh token langsung di kode!)
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# ====== KONFIGURASI ======
XP_MIN = 15              # XP minimum per pesan
XP_MAX = 25               # XP maksimum per pesan
XP_COOLDOWN_SECONDS = 60  # Jeda minimum antar pesan yang menghasilkan XP

# ====== KONFIGURASI ANTI-SPAM ======
SPAM_WARNING_COUNT = 3        # Pesan sama ke-berapa untuk mulai diberi peringatan
SPAM_MUTE_COUNT = 5           # Pesan sama ke-berapa untuk langsung di-mute (timeout)
SPAM_TIME_WINDOW_SECONDS = 20 # Jeda maksimum antar pesan supaya masih dianggap satu rentetan spam
SPAM_MUTE_DURATION_MINUTES = 10  # Lama mute (timeout) dalam menit

# Role reward per level. Key = level, Value = nama role (harus persis sama dengan nama role di server)
# Member akan otomatis mendapat role ini begitu mencapai level tsb (dan tetap menyimpan role level sebelumnya).
LEVEL_ROLES = {
    10: 1527384406917124316,
    20: 1533494275420066022,
    50: 1537386450146951218,
}

# Mengatur hak akses (intents)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # supaya bisa ambil nama member di leaderboard

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


# Menyimpan status spam per user (key = user_id), berlaku LINTAS SEMUA CHANNEL di server.
# Struktur: { user_id: {"content": str, "count": int, "last_ts": float, "warned": bool} }
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

    # Pesan beda dari sebelumnya, atau jeda terlalu lama -> mulai hitungan baru
    if content != state["content"] or (now - state["last_ts"]) > SPAM_TIME_WINDOW_SECONDS:
        state["content"] = content
        state["count"] = 1
        state["warned"] = False
        state["last_ts"] = now
        return False

    # Pesan sama, masih dalam rentang waktu -> lanjutkan hitungan (lintas channel manapun)
    state["count"] += 1
    state["last_ts"] = now

    if state["count"] >= SPAM_MUTE_COUNT:
        # Reset supaya tidak langsung mute lagi berkali-kali begitu timeout berakhir/dicabut
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
            f"beneran gw mute yak."
        )

    return False

@bot.event
async def on_ready():
    print(f"Bot berhasil login sebagai {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    # Jangan proses XP untuk pesan dari bot atau di luar server (DM)
    if message.author.bot or message.guild is None:
        await bot.process_commands(message)
        return

    kena_mute = await check_spam(message)
    if kena_mute:
        return  # jangan proses XP atau command lain untuk pesan spam terakhir ini

    user = db.get_user(message.guild.id, message.author.id)
    now = int(time.time())

    if now - user["last_message_ts"] >= XP_COOLDOWN_SECONDS:
        xp_gain = random.randint(XP_MIN, XP_MAX)
        result = db.add_xp(message.guild.id, message.author.id, xp_gain, now)

        if result["leveled_up"]:
            embed = discord.Embed(
                description=f"🎉 Selamat {message.author.mention}, kamu naik ke **Level {result['new_level']}**!",
                color=discord.Color.green(),
            )
            await message.channel.send(embed=embed)

            role_baru = await give_level_roles(message.author, result["new_level"])
            if role_baru:
                await message.channel.send(
                    f"🎁 {message.author.mention} mendapatkan role: **{', '.join(role_baru)}**"
                )

    # Penting: tetap proses command (!ping, !dadu, dll) setelah hitung XP
    await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    await ctx.send("Nape?")


@bot.command()
async def dadu(ctx):
    angka = random.randint(1, 6)
    await ctx.send(f"🎲 Kamu mendapatkan angka: **{angka}**")


@bot.command()
async def rank(ctx, member: discord.Member = None):
    """Cek level dan XP diri sendiri atau member lain. Contoh: !rank @nama"""
    target = member or ctx.author
    user = db.get_user(ctx.guild.id, target.id)
    xp_needed = db.xp_needed_for_level(user["level"])
    position = db.get_rank_position(ctx.guild.id, user["level"], user["xp"])

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
    rows = db.get_leaderboard(ctx.guild.id, jumlah)

    if not rows:
        await ctx.send("Belum ada data XP di server ini.")
        return

    medali = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(rows):
        label = medali[i] if i < 3 else f"**{i + 1}.**"
        member = ctx.guild.get_member(int(row["user_id"]))
        nama = member.display_name if member else f"Pengguna ({row['user_id']})"
        lines.append(f"{label} {nama} — Level {row['level']} ({row['xp']} XP)")

    embed = discord.Embed(
        title=f"🏆 Papan Peringkat — {ctx.guild.name}",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    await ctx.send(embed=embed)


ADMIN_ROLE_NAME = 1411476274224042115  # ganti dengan nama role kamu (harus persis sama, case-sensitive)


@bot.command()
@commands.has_role(ADMIN_ROLE_NAME)
async def setlevel(ctx, member: discord.Member, level: int):
    """[Admin] Atur level member secara manual. Contoh: !setlevel @nama 5"""
    db.set_level(ctx.guild.id, member.id, level)
    await ctx.send(f"✅ Level {member.mention} telah diatur ke **{level}**.")

    role_baru = await give_level_roles(member, level)
    if role_baru:
        await ctx.send(f"🎁 {member.mention} mendapatkan role: **{', '.join(role_baru)}**")


@setlevel.error
async def setlevel_error(ctx, error):
    if isinstance(error, (commands.MissingRole, commands.MissingAnyRole, commands.MissingPermissions)):
        await ctx.send(f"Kamu perlu role **{ADMIN_ROLE_NAME}** untuk menggunakan command ini.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member tidak ditemukan.")


@bot.command()
@commands.has_role(ADMIN_ROLE_NAME)
async def addxp(ctx, member: discord.Member, jumlah: int):
    """[Admin] Tambah XP member secara manual. Contoh: !addxp @nama 50 (bisa negatif untuk mengurangi)"""
    result = db.add_xp(ctx.guild.id, member.id, jumlah, int(time.time()))

    await ctx.send(f"✅ Menambahkan **{jumlah} XP** ke {member.mention}.")

    if result["leveled_up"]:
        embed = discord.Embed(
            description=f"🎉 Selamat {member.mention}, kamu naik ke **Level {result['new_level']}**!",
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

        role_baru = await give_level_roles(member, result["new_level"])
        if role_baru:
            await ctx.send(f"🎁 {member.mention} mendapatkan role: **{', '.join(role_baru)}**")


@addxp.error
async def addxp_error(ctx, error):
    if isinstance(error, (commands.MissingRole, commands.MissingAnyRole, commands.MissingPermissions)):
        await ctx.send(f"Kamu perlu role **{ADMIN_ROLE_NAME}** untuk menggunakan command ini.")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("Member tidak ditemukan.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Jumlah XP harus berupa angka. Contoh: `!addxp @nama 50`")


# Jalankan bot
if TOKEN is None:
    raise RuntimeError(
        "DISCORD_TOKEN tidak ditemukan. Pastikan file .env ada dan berisi DISCORD_TOKEN=token_kamu"
    )

bot.run(TOKEN)