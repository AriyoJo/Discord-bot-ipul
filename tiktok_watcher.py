import json
import re

import aiohttp

# TikTok tidak menyediakan webhook/API publik untuk notifikasi seperti ini,
# jadi modul ini membaca halaman publik TikTok (scraping) untuk mendeteksi
# perubahan. Ini TIDAK RESMI dan bisa berhenti bekerja sewaktu-waktu kalau
# TikTok mengubah struktur halaman mereka.

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_UNIVERSAL_DATA_RE = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.DOTALL,
)


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                print(f"[TikTok] {url} balas status {resp.status}")
                return None
            return await resp.text()
    except Exception as e:
        print(f"[TikTok] Gagal mengambil {url}: {e}")
        return None


def _extract_universal_data(html: str) -> dict | None:
    match = _UNIVERSAL_DATA_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


async def get_latest_video(session: aiohttp.ClientSession, username: str) -> dict | None:
    """
    Ambil video/postingan terbaru dari profil TikTok publik.
    Return dict {"id", "desc", "url", "create_time"} atau None kalau gagal/tidak ada video.
    """
    html = await _fetch_html(session, f"https://www.tiktok.com/@{username}")
    if html is None:
        return None

    data = _extract_universal_data(html)
    if data is None:
        return None

    try:
        default_scope = data.get("__DEFAULT_SCOPE__", {})
        user_detail = default_scope.get("webapp.user-detail", {})
        item_list = user_detail.get("itemList") or []

        if not item_list:
            return None

        latest = item_list[0]
        video_id = latest["id"]
        return {
            "id": video_id,
            "desc": latest.get("desc", "") or "(tanpa caption)",
            "url": f"https://www.tiktok.com/@{username}/video/{video_id}",
            "create_time": int(latest.get("createTime", 0)),
        }
    except (KeyError, IndexError, TypeError) as e:
        print(f"[TikTok] Gagal parsing video terbaru (struktur halaman mungkin berubah): {e}")
        return None


async def is_live(session: aiohttp.ClientSession, username: str) -> bool:
    """Cek apakah user TikTok sedang live streaming sekarang."""
    html = await _fetch_html(session, f"https://www.tiktok.com/@{username}/live")
    if html is None:
        return False

    data = _extract_universal_data(html)
    if data is None:
        return False

    try:
        default_scope = data.get("__DEFAULT_SCOPE__", {})
        live_scope = (
            default_scope.get("webapp.live-detail")
            or default_scope.get("webapp.live")
            or {}
        )
        room_info = live_scope.get("liveRoomUserInfo", {}) or live_scope.get("roomInfo", {})
        status = room_info.get("status")
        if status is None:
            status = room_info.get("liveRoom", {}).get("status")
        # Status 2 = sedang live. Status lain (mis. 4) = tidak live.
        return status == 2
    except (KeyError, TypeError):
        return False
