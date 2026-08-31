# Bot Discord Leveling (Python)

Bot Discord dengan sistem leveling: XP naik saat chat, level up otomatis, cek rank, dan leaderboard.

## ⚠️ Sebelum mulai: amankan token bot kamu
Kalau token bot kamu pernah tertulis langsung di kode `.py` dan sudah pernah dibagikan/di-screenshot,
**reset token itu sekarang** di https://discord.com/developers/applications → aplikasi kamu → tab **Bot** → **Reset Token**.
Token lama otomatis tidak berlaku lagi setelah direset. Token yang baru nanti taruh di file `.env`, BUKAN di kode.

## 1. Install Python
Pastikan Python 3.10+ sudah terinstall. Cek dengan:
```bash
python --version
```
Kalau belum ada, download di https://www.python.org/downloads/ (saat instalasi di Windows, centang "Add Python to PATH").

## 2. Buat virtual environment (disarankan)
Di folder proyek, jalankan:
```bash
python -m venv venv
```
Aktifkan:
- Windows (PowerShell): `venv\Scripts\Activate.ps1`
- Windows (cmd): `venv\Scripts\activate.bat`
- Mac/Linux: `source venv/bin/activate`

## 3. Install dependencies
```bash
pip install -r requirements.txt
```

## 4. Konfigurasi token
```bash
copy .env.example .env      # Windows
# atau: cp .env.example .env   (Mac/Linux)
```
Buka file `.env`, isi dengan token bot kamu yang baru:
```
DISCORD_TOKEN=token_bot_kamu_disini
```

## 5. Aktifkan Message Content Intent
Di Discord Developer Portal → aplikasi kamu → tab **Bot** → aktifkan **MESSAGE CONTENT INTENT** dan **SERVER MEMBERS INTENT**.
Tanpa ini, bot tidak bisa membaca isi pesan untuk menghitung XP, dan tidak bisa menampilkan nama member di leaderboard.

## 6. Jalankan bot
```bash
python main.py
```

## Command yang tersedia
- `!ping` — tes bot masih hidup
- `!dadu` — lempar dadu 1-6
- `!rank [@member]` — cek level & XP diri sendiri atau member lain
- `!leaderboard [jumlah]` — papan peringkat (default 10, maks 25)
- `!setlevel @member <level>` — admin bisa atur level manual

## Kustomisasi
Di bagian atas `main.py`:
- `XP_MIN` / `XP_MAX` — rentang XP acak per pesan
- `XP_COOLDOWN_SECONDS` — jeda minimum antar pesan yang menghasilkan XP

Rumus kebutuhan XP per level ada di `database.py` fungsi `xp_needed_for_level()`.

## Struktur File
```
discord-leveling-bot-python/
├── main.py              # Bot utama (event listener, semua command)
├── database.py          # Logika database SQLite (XP, level, leaderboard)
├── requirements.txt
├── .env.example
├── .env                 # kamu buat sendiri, isi token asli (JANGAN dibagikan)
└── leveling.db           # dibuat otomatis saat bot pertama kali jalan
```
