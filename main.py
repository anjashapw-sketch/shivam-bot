import asyncio
import logging
import json
import os
import time
import re
import random
import string
import zipfile
import io
import pymongo
import uuid
import struct
import base64
import hashlib
import ipaddress
from urllib.parse import urlparse
import tempfile
import shutil
import sqlite3
import html
from datetime import datetime, timedelta, timezone

try:
    import socks
except ImportError:
    socks = None

# Auto-load environment variables from .env if present
def load_env_file(filepath=".env"):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

load_env_file()

from telegram import Update, InlineKeyboardButton as _OriginalInlineKeyboardButton, InlineKeyboardMarkup
try:
    from telegram.constants import KeyboardButtonStyle
except ImportError:
    KeyboardButtonStyle = None
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, SendReactionRequest, GetBotCallbackAnswerRequest, GetMessagesViewsRequest, CheckChatInviteRequest, SendVoteRequest, GetFullChatRequest
from telethon.tl.functions.phone import JoinGroupCallRequest
from telethon.tl.types import ReactionEmoji, ReactionCustomEmoji, DataJSON, PeerChannel, Channel, InputGroupCall, GroupCallDiscarded, InputPeerSelf
from telethon.errors import (
    SessionPasswordNeededError, FloodWaitError, UserAlreadyParticipantError, GroupcallSsrcDuplicateMuchError,
    AuthKeyUnregisteredError, AuthKeyDuplicatedError, UserDeactivatedError, UserDeactivatedBanError
)
from telethon.sessions import StringSession, SQLiteSession

# ==============================================================================
# ⚙️ BOT CONFIGURATION (ALL SETTINGS IN ONE PLACE - EDIT EASILY HERE)
# ==============================================================================

# 1. Telegram Bot Token (from @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8823588825:AAFpQAiKK4KUpElvEM_QEmCzlR_fhAbRvsQ")

# 2. Telegram Client API Credentials (from https://my.telegram.org)
API_ID = int(os.getenv("API_ID", "38029370"))
API_HASH = os.getenv("API_HASH", "375ae9e5e1e90b17ac528abb4ff90295")

# 3. Bot Owner & Administrator Telegram User IDs
OWNER_ID = int(os.getenv("OWNER_ID", "5260253836"))
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "1996270156").split(",") if x.strip().isdigit()]
for _aid in [1996270156]:
    if _aid not in ADMIN_IDS:
        ADMIN_IDS.append(_aid)

# 4. Admin Log Channel ID (Fallback default; also editable live via /setlog or Admin Panel)
#    Example: "-1001234567890" or "@mychannel" (leave "" if not set yet)
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID", os.getenv("LOG_CHANNEL", "")).strip()

# 5. MongoDB Database Connection
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://shivamkkumar28000_db_user:wMrt0QTowww98G0U@cluster0.gagpla9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "telegram_voting_bot")

# 6. Global Proxy for Telethon User Accounts (optional, socks5/socks4/http)
#    Example: "socks5://user:pass@1.2.3.4:1080" or "" for direct connection
TELEGRAM_PROXY_STR = os.getenv("TELEGRAM_PROXY", "")

# 7. Action Delay & Performance Timing (in seconds)
DEFAULT_DELAY = float(os.getenv("DEFAULT_DELAY", "0.5"))
CACHE_TIME = int(os.getenv("CACHE_TIME", "900"))

# 8. Premium Custom Emoji IDs (Fallback mapping for custom animated reactions)
PREMIUM_EMOJIS = {
    "heart_fire": "5042225965518816316",
    "lightning": "5042334757040423886",
    "location": "5039775669496579510",
    "flower": "6073117703965511893",
    "check": "6147460667281511517",
    "crown": "6235252066554484059",
    "kiss": "6116282026506065674",
    "skull": "6089128873893563936",
    "xmas": "6267071898702583835",
    "monkey": "6273627839862411998",
    "gift": "5893175870096414393",
    "angel": "5893411041030707544",
    "devil": "5893079628469246474",
}

# 9. Standard Reaction Emojis
NORMAL_EMOJIS = [
    "🔥", "❤️", "👍", "😍", "🎉", "💯", "👏", "🥳", "😁", "🤩",
    "😎", "🙌", "💪", "✨", "🌟", "💖", "💘", "💝", "💕", "💞",
    "💓", "💗", "💯", "🎊", "🎈", "🎁", "🏆", "🥇", "🥈", "🥉",
    "🎯", "🚀", "⭐", "🌈", "☀️", "🍀", "🌹", "🌸", "💐", "🎵"
]

AVAILABLE_REACTIONS = NORMAL_EMOJIS + ["😱", "🤬", "😢", "💩", "🙏"]
# ==============================================================================

# ========== TELEGRAM BOT API 9.4+ COLORED BUTTON STYLING ==========
def determine_button_style(label: str, callback_data: str = "") -> str:
    """
    Intelligently determines Telegram Bot API 9.4+ button style ('primary', 'success', 'danger')
    based on the button function, action, and text:
    - primary (blue): navigation, features, admin tools, options
    - success (green): additions, positive actions, confirmations, approvals, runs
    - danger (red): cancellations, removals, bans, revoking, leaving, destructive actions
    """
    l = (label or "").lower()
    c = (callback_data or "").lower()

    # 1. Check unban first so it doesn't match 'ban'
    if "unban" in c or "unban" in l:
        return "success"

    # 2. DANGER (RED) - Cancellations, removals, bans, revoking, leaving, destructive actions
    danger_cbs = [
        "cancel", "remove", "ban", "revoke", "leave",
        "expired", "delete", "no_direct", "clear", "stop"
    ]
    danger_labels = [
        "cancel", "remove", "delete", "ban", "revoke", "leave",
        "expired", "❌", "🗑️", "⚠️", "🚪", "no"
    ]
    if any(k in c for k in danger_cbs) or any(k in l for k in danger_labels):
        return "danger"

    # 3. SUCCESS (GREEN) - Additions, positive actions, confirmations, approvals, runs, live
    success_cbs = [
        "add", "grant", "give", "export", "import", "yes",
        "live", "run", "ready", "confirm", "reacted", "upload"
    ]
    success_labels = [
        "add", "upload", "grant", "unban", "give", "export",
        "import", "yes", "confirm", "live", "ready", "run",
        "➕", "✅", "🚀", "📦", "📥", "📤", "try again"
    ]
    if any(k in c for k in success_cbs) or any(k in l for k in success_labels):
        return "success"

    # 4. PRIMARY (BLUE) - Navigation, main actions, stats, settings, campaigns
    return "primary"

import inspect

class InlineKeyboardButton(_OriginalInlineKeyboardButton):
    """
    Extended InlineKeyboardButton that automatically applies Telegram Bot API 9.4+
    color styling (primary/blue, success/green, danger/red) as per the button function,
    compatible across python-telegram-bot 20.x, 21.x, and 22.x.
    """
    def __init__(self, text, callback_data=None, *args, style=None, **kwargs):
        if style is None and callback_data:
            style = determine_button_style(text, callback_data)
        sig = inspect.signature(_OriginalInlineKeyboardButton.__init__)
        if "style" in sig.parameters:
            kwargs["style"] = style
        super().__init__(text, callback_data=callback_data, *args, **kwargs)
        object.__setattr__(self, "_style", style)

    def to_dict(self, *args, **kwargs):
        d = super().to_dict(*args, **kwargs)
        st = getattr(self, "_style", None)
        if st:
            d["style"] = st
        return d

    def __iter__(self):
        return iter(self.to_dict().items())

def btn_to_dict(btn):
    """Safely converts any button representation (dict, InlineKeyboardButton, etc.) to a dict for inline keyboards."""
    if isinstance(btn, dict):
        return btn
    if hasattr(btn, 'to_dict'):
        try:
            return btn.to_dict()
        except Exception:
            pass
    try:
        return dict(btn)
    except Exception:
        text = getattr(btn, 'text', str(btn))
        cb = getattr(btn, 'callback_data', None)
        d = {"text": text}
        if cb is not None:
            d["callback_data"] = cb
        style = getattr(btn, 'style', None)
        if style:
            d["style"] = style
        return d

def styled_button(label: str, callback_data: str, style: str = None) -> dict:
    """Helper to create button dictionaries for inline keyboard with Bot API 9.4+ color styles."""
    chosen_style = style or determine_button_style(label, callback_data)
    return {"text": label, "callback_data": callback_data, "style": chosen_style}

# ========== PROXY SUPPORT ==========
def parse_proxy_string(proxy_str):
    """Parse proxy URL (socks5://, socks4://, http://) into Telethon proxy dict."""
    if not proxy_str:
        return None
    try:
        parsed = urlparse(proxy_str)
        scheme = parsed.scheme.lower()
        import socks
        if scheme in ('socks5', 'socks5h'):
            proxy_type = socks.SOCKS5
        elif scheme in ('socks4', 'socks4a'):
            proxy_type = socks.SOCKS4
        elif scheme in ('http', 'https'):
            proxy_type = socks.HTTP
        else:
            return None
        return {
            'proxy_type': proxy_type,
            'addr': parsed.hostname,
            'port': parsed.port,
            'username': parsed.username,
            'password': parsed.password,
            'rdns': True
        }
    except Exception:
        return None

GLOBAL_PROXY = parse_proxy_string(TELEGRAM_PROXY_STR)

# ========== PYROGRAM TO TELETHON SESSION CONVERTER ==========
TELETHON_DC_IPS = {
    1: '149.154.175.53',
    2: '149.154.167.51',
    3: '149.154.175.100',
    4: '149.154.167.92',
    5: '91.108.56.130'
}

def pyrogram_to_telethon_session(pyro_string: str) -> str:
    """Converts a Pyrogram string session (v1 or v2) to a valid Telethon StringSession."""
    if not pyro_string or not isinstance(pyro_string, str):
        return None
    try:
        pyro_string = pyro_string.strip()
        if not re.match(r'^[A-Za-z0-9_-]+={0,3}$', pyro_string):
            return None
        pad = len(pyro_string) % 4
        if pad:
            pyro_string += '=' * (4 - pad)
        data = base64.urlsafe_b64decode(pyro_string)
        if len(data) < 258:
            return None
        dc_id = data[0]
        # Pyrogram v2: data[1] is test_mode, data[2:258] is 256-byte auth key
        auth_key = data[2:258]
        if dc_id not in TELETHON_DC_IPS:
            dc_id = 2
        ip_str = TELETHON_DC_IPS[dc_id]
        ip_bytes = ipaddress.IPv4Address(ip_str).packed
        packed = struct.pack('>B4sH256s', dc_id, ip_bytes, 443, auth_key)
        return '1' + base64.urlsafe_b64encode(packed).decode('ascii')
    except Exception:
        return None

def parse_hex_key_to_session_string(text: str) -> str:
    """Converts a Telegram Hex Key (e.g. dc_id=5 0000007... or 5:0000007...) to Telethon StringSession."""
    if not text or not isinstance(text, str):
        return None
    try:
        clean = text.strip()
        dc_id = 2
        dc_match = re.search(r'dc(?:_id)?\s*[:=]?\s*(\d+)', clean, re.I)
        if dc_match:
            dc_id = int(dc_match.group(1))
            clean_without_dc = re.sub(r'dc(?:_id)?\s*[:=]?\s*\d+', '', clean, flags=re.I)
        else:
            prefix_match = re.match(r'^(\d+)\s*[:\-_]\s*([0-9a-fA-F\s]{512,})', clean)
            if prefix_match:
                dc_id = int(prefix_match.group(1))
                clean_without_dc = clean[prefix_match.start(2):]
            else:
                clean_without_dc = clean

        if dc_id not in TELETHON_DC_IPS:
            dc_id = 2

        hex_match = re.search(r'([0-9a-fA-F]{512})', clean_without_dc)
        if not hex_match:
            only_hex = re.sub(r'[^0-9a-fA-F]', '', clean_without_dc)
            if len(only_hex) == 512:
                hex_str = only_hex
            else:
                return None
        else:
            hex_str = hex_match.group(1)

        key_bytes = bytes.fromhex(hex_str)
        if len(key_bytes) != 256:
            return None

        ip_str = TELETHON_DC_IPS[dc_id]
        ip_bytes = ipaddress.IPv4Address(ip_str).packed
        packed = struct.pack('>B4sH256s', dc_id, ip_bytes, 443, key_bytes)
        return '1' + base64.urlsafe_b64encode(packed).decode('ascii')
    except Exception:
        return None

def parse_json_to_session_string(text: str) -> str:
    """Extracts session string or auth_key from a .json session file content."""
    if not text or not isinstance(text, str):
        return None
    clean = text.strip()
    if not (clean.startswith('{') and clean.endswith('}')):
        return None
    try:
        data = json.loads(clean)
        if not isinstance(data, dict):
            return None
        candidates = [data]
        if isinstance(data.get('data'), dict):
            candidates.append(data['data'])
        if isinstance(data.get('session_data'), dict):
            candidates.append(data['session_data'])

        for d in candidates:
            for k in ['session_string', 'session', 'string_session', 'telethon_string', 'telethon_session', 'telethon', 'pyrogram_session', 'pyrogram_string', 'pyrogram', 'string']:
                val = d.get(k)
                if isinstance(val, str) and len(val.strip()) > 30:
                    val_s = val.strip()
                    try:
                        if StringSession(val_s).auth_key:
                            return val_s
                    except Exception:
                        pass
                    pyro = pyrogram_to_telethon_session(val_s)
                    if pyro:
                        return pyro
                    hex_k = parse_hex_key_to_session_string(val_s)
                    if hex_k:
                        return hex_k

            auth_key = d.get('auth_key') or d.get('key')
            dc_id = d.get('dc_id', 2)
            if auth_key:
                if isinstance(auth_key, list) and len(auth_key) == 256:
                    return parse_hex_key_to_session_string(f"dc_id={dc_id} {bytes(auth_key).hex()}")
                elif isinstance(auth_key, str):
                    return parse_hex_key_to_session_string(f"dc_id={dc_id} {auth_key}")
    except Exception:
        pass
    return None

# ========== LOGGING CONFIGURATION ==========
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DIR = "/root/vote" if os.path.exists("/root/vote") else os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(LOG_DIR, "bot.log")
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler()
    ]
)
logging.getLogger('telethon').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('pymongo').setLevel(logging.WARNING)

# ========== RUNTIME STATE & CLIENT CACHE ==========
LIVE_CACHE = {}
CLIENT_POOL = {}
ACTIVE_CLIENTS = {}
SCHEDULED_TASKS = {}
GLOBAL_BOT = None
ACCOUNT_COOLDOWNS = {}  # phone -> unix timestamp until which account rests
RESOLVE_CACHE = {}      # link -> (peer, msg_id, expire_time)

# Realistic mobile device profiles for official Android and iOS client spoofing
# Prevents Telegram from flagging accounts as datacenter / Linux / Telethon bots
DEVICE_PROFILES = [
    {"device_model": "Samsung Galaxy S23 Ultra", "system_version": "Android 14 (SDK 34)", "app_version": "10.14.5", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Google Pixel 8 Pro", "system_version": "Android 14 (SDK 34)", "app_version": "10.14.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Xiaomi 13 Pro", "system_version": "Android 14 (SDK 34)", "app_version": "10.13.2", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "OnePlus 11 5G", "system_version": "Android 14 (SDK 34)", "app_version": "10.13.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Samsung Galaxy S22+", "system_version": "Android 13 (SDK 33)", "app_version": "10.12.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Redmi Note 12 Pro", "system_version": "Android 13 (SDK 33)", "app_version": "10.11.1", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Google Pixel 7a", "system_version": "Android 13 (SDK 33)", "app_version": "10.10.1", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Vivo X90 Pro", "system_version": "Android 13 (SDK 33)", "app_version": "10.10.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iPhone 14 Pro", "system_version": "iOS 16.6.1", "app_version": "10.8.2", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iPhone 15 Pro Max", "system_version": "iOS 17.4.1", "app_version": "10.14.0", "lang_code": "en", "system_lang_code": "en-US"},
]

def get_device_params_for_phone(phone=None, account=None):
    """Deterministically maps a phone/account to a consistent realistic mobile device profile."""
    if account and isinstance(account, dict):
        if account.get("device_model") and account.get("app_version"):
            return {
                "device_model": account.get("device_model"),
                "system_version": account.get("system_version") or "Android 14 (SDK 34)",
                "app_version": account.get("app_version"),
                "lang_code": account.get("lang_code") or "en",
                "system_lang_code": account.get("system_lang_code") or "en-US"
            }
        phone = phone or account.get("phone")
    key = str(phone or "default_device_seed").strip().lstrip('+')
    idx = int(hashlib.md5(key.encode()).hexdigest(), 16) % len(DEVICE_PROFILES)
    profile = DEVICE_PROFILES[idx].copy()
    if account and isinstance(account, dict):
        account["device_model"] = profile["device_model"]
        account["system_version"] = profile["system_version"]
        account["app_version"] = profile["app_version"]
    return profile

def create_telegram_client(session, phone=None, account=None, proxy=None):
    """Creates a TelegramClient with genuine mobile device fingerprinting to prevent bans."""
    params = get_device_params_for_phone(phone, account)
    use_proxy = proxy if proxy is not None else GLOBAL_PROXY
    cl = TelegramClient(
        session,
        API_ID,
        API_HASH,
        proxy=use_proxy,
        device_model=params["device_model"],
        system_version=params["system_version"],
        app_version=params["app_version"],
        lang_code=params["lang_code"],
        system_lang_code=params["system_lang_code"]
    )
    if phone:
        cl._phone = str(phone).strip().lstrip('+')
    elif account and account.get('phone'):
        cl._phone = str(account.get('phone')).strip().lstrip('+')
    return cl

def is_account_on_cooldown(phone: str) -> bool:
    """Checks if an account is currently paused due to FloodWait or PeerFlood."""
    if not phone:
        return False
    p = str(phone).strip().lstrip('+')
    exp = ACCOUNT_COOLDOWNS.get(p)
    if exp is None:
        return False
    if time.time() < exp:
        return True
    ACCOUNT_COOLDOWNS.pop(p, None)
    return False

def set_account_cooldown(phone: str, seconds: float):
    """Sets a protective pause duration on an account to avoid Telegram bans."""
    if phone:
        p = str(phone).strip().lstrip('+')
        safe_dur = max(float(seconds), 3.0)
        ACCOUNT_COOLDOWNS[p] = time.time() + safe_dur
        logging.info(f"⏳ Cooldown set on account {p} for {safe_dur:.1f}s")

FROZEN_ACCOUNTS = {
    'user_1996270156_1791377923_3_31e0',
    'user_1996270156_1791390428_1_281f',
    'user_1996270156_1791390428_2_8d85',
    'user_1996270156_1791377957_6_71d7',
    'user_1996270156_1791390425_4_da25',
    'user_1996270156_1791390428_4_6e67',
    'user_1996270156_1791390432_4_80e7',
    'user_1996270156_1791377923_2_48e4',
    'user_1996270156_1791390429_5_bce7',
    'user_1996270156_1791377952_2_52db',
    '1BVtsOIUBuyJidcT2wGqZ4GGSaIBOnfnntpLGfVyzi2qXdCFDGe75X4MlNFT0RnCGFKSqvw1hymcEHYLTVgj3godPczHAKfgACvSQIoFehkrJHnMA7mQLhn_ZuoXkBDjoVgJZuVdsJvPDAe16Dy8N0qp3U-lklhNbIgtjs-AoG0KmpvHzxXtl36Jigd75ifuAIqOA5mCa4bJHZ8c4VeVpWoZVaz4f3RMPPLgghHjS4xXLwH8h2qqBnX26-ODbcvCVfVPLGjO-m8gJ-HzOIeM87PWRIgSV8tH2CZUvpPqmqdU4tGlqYmefDg7O-lih0kYHpyfXE-salMauqHVXO1NW1-FlwL9rPQU=',
    '1BVtsOIUBu4oXbLUwtubEHjexkK73GY81GZKITsY6aQNkarc81ECsAVYJBrbMkLXTRUjocEYDIT6mmfVtw6jYe15aqUOR2IXRHYY7OkNXd0NqahK0ODOk92ekX5A9MhbWHyx_79UODDHhEKtXVbXENRP8K8y70hYhGPqNGVS7DUPrOU8Ui5_byucQ5MLYmSTlh4Xxf9VjP5GevPSDYS4Wr20EjVH0fn5Vev0UO5CbfvqDzIXbJo_9KqNJRW15noGR-Qj_BvKSgjGbC72BBrt22CBNC-C3lDJzVl8RugFojRN8YWMDEq4n9LLWhnjTaD_GLodP9W0mmRJtIS5Queqpb44uEq-ZfIo=',
    '1BVtsOIUBuxJ6GyvD8SMbAv8Oudxr-jqlnyyBr6SwS8c7lRPDpnL8ZeMUw8n40Vh788DuI-wnP3DkuehuWxADpzKSrAayl1YvIJ1WntpMsBVfvAwNzPwD7m9cS27GsVQjQMbUDmrG4QStQTALDrT6S7pFd6f980MS1ftqm20k8HV0hXKNk_WCzLC0bnVpSLYl2zIa0I_magK7hFn4B9boNm2RcpxY-O2z7XVoJnC3hcLCydqvbYDRBWmJL1oEcRFh38c8XT6Nkk7_J707iGNQPal-g7vdExKZo6rDwTAMGfLAidTDfaiTsxqxx4lM354D-UR8d2ano3P7iKirjE7jZzlwZFnti9o=',
    '1BVtsOIUBu5ctumSTDLzHAgn8uH9tDu7v6a_xPsRTeSKqzE-IWPmDDEuVdghwIXIV2qLdBLz1kKp7X12oe1G0_ZOaAaCjypYqfqNi_Pi50TbRs4qP-p_70HmBbEVvItAQju8ZiQNTMvYwQn7aq85OyFU3UlxVKDlYmcvDVG5a59RWo4hjmmkQ0uLNjDt6TrixpNKVYry0iJHYbtw4XMDt1o2pmzWBIjAUZowcgzpZqD4YE1kaG8EgJ56ovODO-MubfJ43KQA9TGbuaI6410snKT6FS6W9kwVbj1jLe4bi4fjeJ1-_RHigW02PAxuhdCBTo-FTHQuo-3cC05nR9ppDqpHNrUN-pTI=',
    '1BVtsOIUBu3WlcAKzej7pHG8KrpQodzrRQwNYlg-aaRg8d7uMHhuFJsfIjfbO1LTfzeDBm_Av4XV34tff46rAmRt5OacPqWUanZlZyjrK6mvFjygN2WsIrjPDgmrv1aLql2sjDFpdcfbxnJmpVNgYlWOI7WQuvphTZVV4PUliAJvNdEAMlXKjzI6TEhH6H59fJIE6Q0n4JcNyO-vOgq8zihkgMS1W4h8CgL2bhRE350-gfviF9bA4s16wudMB6oCFd_kDHd7YLbzanFdY5RHp4gtj1ytK7ChbmsKqLfrlTsPkxdERBTSRtyYg3zn_F34y185Sp2nBVHYsX205ixJFtRQP-nydoFM=',
    '1BVtsOIUBu7bqvuurw38_v8W2m590iehAfGhIXVIZD3Vg5QNIg5efiEx9C11pSvBtLRLpLI__MBxMNdG4tsdsbW59gQoVHPP-MJO1MGXZts3tgHU9Gg1LlFrlpgLinUk8Ex5mS6vBeN9MIfnQUpZu3KZwwUjIQj-fiF9xXxNu9lzx6bt22zJ9kpmH2Cx4Bxd4KPnLpAQo1AsCCsTVE2j33CmU59RSYuGsXnY3ol2wMn0xO39EMd9NF5AKUw64KkcOC5fBcLZRc116nSXrezVXEW30q2WrvzbaD1XuxuW-eQFtxvP-l0zC_Q7K2519svltH10FrW9BZ11iJC3DDwLQu0AxnWVYB88=',
    '1BVtsOIUBu5z77SAPMtVCnTX0hqPklyZUymL4MOzWYlBltz6a33ZJN27QvFrDhCLrebbym20EcDeX0MJ8T3jXPanz5N4GSXWVEOnfaFbSuf9RmU7xX88f2mHG9mu5E2rq2vsTggSWI4DH95a0a5UEBAZ1NL3gnkSyYf1eJe6LNd88gF0RtW6zkfS-bWmiGQoeJmXeL1Kh6H357qBS0n68T3fQrhGndjXSlgrxXjk924kzJ7q-tSJ6OPxo-SQih_ZLZlYOXUUf-tEruADEvxwQPLv8m4IuTjJaXoegFOKK4_3x8aRfZA0POtcqyfcQ597m0edLNmblKutBT6pJ1TYQLveCVt2F-tk=',
    '1BVtsOIUBu1XA-SkdOhS1qaLrdz-rzWN_ReaoBjAoPEM2tjdNkcIC1Ssad4vawnvrzYfltoYywerXNMo8sDK19WvgPNU0LpNxl0IESokLv8luXEHlY6h1CIdqdzRDA4tYBTBjyW--EmdAvMfC2ZZil3zojrChc1dfmSNphoE3pUgMN2s7Z9ELpSvKjp5DpYAlO6xxzcE1Z0uZ6kfwIbAjcQCmg0N4nvOTpW7kBCQcZiR3gBepoWPKevIzYrBvye0sEdh1PDSDDXWjkXNDQYX9wudXOZBUvQPyNXjkpYWFMVaoWKC4NsYNgTRC9QHtA1bMdFTiXDKS-S2ZZlNUlxpw5zTTS2XHS5w=',
    '1BVtsOIUBu5B0kbPOiyXu0_4iX-mIk2OtdWoLj__XuorYOp6XRE0IyTqdfZ_2wClllxbQwWAGar4DC4hIM-dkQ5k-Em4tTHgmkqIi5GiI0vfYtkLoM_TjkDErgDZd50I_inuAZVlnIJXz3AJuJqJQpaRSF8ZVFELCaYf76kK1DE-qSXIXvvJLZrGK9kB4EiV7RMRHlKbHLPmWzSLzqG4OXTTvmwtt7OD-8G5x1gS4x8PnyqoaqfXADPHN2JBccF1PMgcQM-IToz2SBaOpIukbZ5vWb9UX6VbPoWzBksxgVOMhKSCLGzuWIfttLuK3AYl705fZtdQkHmasqxQdE6Us4W2cswLZ3i4=',
    '1BVtsOIUBu7HNHau4Wr1LOyjsbvxHJ2cT_DW2CX1TfXfLOq5DnyiAhThaeO6Nv08hIWoY3MGNPiTo95Ad9RK8xjLeFNVPP56MskU8flzgTSdYaYJEJM2z1lQcgWPpq_dnkDeH176Mme8O1zIZIRNU_DCOqXuFj5a0WvJ-V9ue2BrJ_L2-ibjWKNeM5EHfs6kFdlnwR0NdEOM1zC79pKHIQIptmTSYOjIfewP5mG568X0NEnUsSLXoIWYgJu4S5vkht_M1TCXMo5apm8Yms0y1YVVbR13SI1_vQ5PEOnoU2Z9qGSwxLtiOj5c9y1vEwUECJKgt48KSZIgVyDoPVkO_y7f5lHAIl80='
}

def is_account_frozen(account_or_phone) -> bool:
    """Checks if an account was flagged as frozen/restricted by Telegram."""
    if not account_or_phone:
        return False
    if isinstance(account_or_phone, dict):
        p = str(account_or_phone.get('phone') or '').strip().lstrip('+')
        raw = str(account_or_phone.get('phone') or '').strip()
        sess_str = str(account_or_phone.get('session_string') or '').strip()
        sess = str(account_or_phone.get('session') or '').strip()
        return (
            p in FROZEN_ACCOUNTS or raw in FROZEN_ACCOUNTS or
            sess_str in FROZEN_ACCOUNTS or sess in FROZEN_ACCOUNTS or
            any(fn in sess for fn in FROZEN_ACCOUNTS if len(fn) > 10 and not fn.startswith('1BV'))
        )
    p = str(account_or_phone).strip().lstrip('+')
    raw = str(account_or_phone).strip()
    return p in FROZEN_ACCOUNTS or raw in FROZEN_ACCOUNTS

def mark_account_frozen(phone_or_acc):
    """Marks an account as frozen by Telegram so it is safely excluded from campaigns."""
    if not phone_or_acc:
        return
    phone = phone_or_acc.get('phone') if isinstance(phone_or_acc, dict) else phone_or_acc
    sess_str = phone_or_acc.get('session_string') if isinstance(phone_or_acc, dict) else None
    if sess_str:
        FROZEN_ACCOUNTS.add(str(sess_str).strip())
    if phone:
        p = str(phone).strip().lstrip('+')
        raw = str(phone).strip()
        FROZEN_ACCOUNTS.add(p)
        FROZEN_ACCOUNTS.add(raw)
        now = time.time()
        LIVE_CACHE[p] = (False, now)
        LIVE_CACHE[raw] = (False, now)
        ACTIVE_CLIENTS.pop(p, None)
        ACTIVE_CLIENTS.pop(raw, None)
        logging.warning(f"❄️ Account marked as FROZEN by Telegram: {phone}")

# ========== DATABASE LAYER: MONGODB ONLY ==========
MONGO_CLIENT = None
MONGO_DB = None

def init_db():
    """Initialize MongoDB connection and create required collection indexes."""
    global MONGO_CLIENT, MONGO_DB
    try:
        MONGO_CLIENT = pymongo.MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
            maxPoolSize=50,
            retryWrites=True
        )
        MONGO_CLIENT.admin.command('ping')
        MONGO_DB = MONGO_CLIENT[MONGO_DB_NAME]

        # Create indexes for optimal querying across all collections
        MONGO_DB.users.create_index("user_id", unique=True)
        MONGO_DB.campaigns.create_index([("user_id", 1), ("timestamp", -1)])
        MONGO_DB.campaigns.create_index("id")
        MONGO_DB.scheduled.create_index([("user_id", 1), ("status", 1)])
        MONGO_DB.scheduled.create_index("id")
        MONGO_DB.bot_settings.create_index("key", unique=True)

        print(f"🍃 [MongoDB] Connected successfully to '{MONGO_DB_NAME}' ({MONGO_URI})")
        logging.info(f"MongoDB connected to {MONGO_DB_NAME}")
        return True
    except Exception as e:
        print("=" * 60)
        print(f"⚠️ [MongoDB] Connection Failed to: {MONGO_URI}")
        print(f"   Error: {e}")
        print("   All data is stored in MongoDB. Please set MONGO_URI:")
        print("   e.g. export MONGO_URI=\"mongodb+srv://user:pass@cluster.mongodb.net/\"")
        print("=" * 60)
        logging.error(f"MongoDB connection failed: {e}")
        return False

def is_maintenance_mode() -> bool:
    """Check if bot maintenance mode is enabled in MongoDB."""
    if MONGO_DB is None:
        return False
    try:
        doc = MONGO_DB.bot_settings.find_one({"key": "maintenance_mode"})
        return bool(doc and str(doc.get("value")) in ("1", "true", "True"))
    except Exception as e:
        logging.error(f"is_maintenance_mode error: {e}")
        return False

def set_maintenance_mode(enabled: bool):
    """Enable or disable maintenance mode in MongoDB."""
    if MONGO_DB is None:
        return
    val = '1' if enabled else '0'
    try:
        MONGO_DB.bot_settings.update_one(
            {"key": "maintenance_mode"},
            {"$set": {"key": "maintenance_mode", "value": val}},
            upsert=True
        )
    except Exception as e:
        logging.error(f"set_maintenance_mode error: {e}")

# ========== ADMIN LOG CHANNEL (MONGODB & ENV) ==========

def get_log_channel_id() -> str:
    """Get configured admin log channel ID from MongoDB or environment variable."""
    if MONGO_DB is not None:
        try:
            doc = MONGO_DB.bot_settings.find_one({"key": "log_channel_id"})
            if doc and doc.get("value"):
                return str(doc.get("value")).strip()
        except Exception as e:
            logging.error(f"get_log_channel_id error: {e}")
    return os.getenv("LOG_CHANNEL_ID", os.getenv("LOG_CHANNEL", "")).strip()

def set_log_channel_id(channel_id: str):
    """Set or update configured admin log channel ID in MongoDB."""
    clean_id = str(channel_id).strip()
    if MONGO_DB is not None:
        try:
            MONGO_DB.bot_settings.update_one(
                {"key": "log_channel_id"},
                {"$set": {"key": "log_channel_id", "value": clean_id}},
                upsert=True
            )
        except Exception as e:
            logging.error(f"set_log_channel_id error: {e}")

async def send_admin_log(text: str, bot=None):
    """Send a formatted notification message to the configured admin log channel."""
    channel_id = get_log_channel_id()
    if not channel_id:
        return False

    target_bot = bot or GLOBAL_BOT
    if not target_bot:
        return False

    target_chat = channel_id
    if target_chat.startswith("-") and target_chat[1:].isdigit():
        target_chat = int(target_chat)
    elif target_chat.isdigit():
        target_chat = int(target_chat)

    try:
        await target_bot.send_message(
            chat_id=target_chat,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return True
    except Exception as e:
        try:
            clean_text = re.sub(r'<[^>]+>', '', text)
            await target_bot.send_message(
                chat_id=target_chat,
                text=clean_text,
                disable_web_page_preview=True
            )
            return True
        except Exception as e2:
            logging.error(f"Failed to send admin log to {channel_id}: {e2}")
            return False

async def send_startup_notifications(bot=None):
    """Sends rich startup notification directly to Owner, all Admins, and the Admin Log Channel."""
    target_bot = bot or GLOBAL_BOT
    if not target_bot:
        return

    admin_list = list(dict.fromkeys([OWNER_ID] + list(ADMIN_IDS)))
    owner_accounts = load_owner_accounts()
    active_accounts = len(owner_accounts)
    db_label = f"MongoDB ({MONGO_DB_NAME})"
    log_chan = get_log_channel_id()
    log_chan_display = log_chan if log_chan else "Not configured (use /setlog)"
    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    msg = (
        "🚀 <b>BOT STARTED &amp; ONLINE!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>Status:</b> Active &amp; Polling (@ShubhVoteBot)\n"
        f"🍃 <b>Database:</b> {html.escape(db_label)}\n"
        f"📱 <b>Available Accounts:</b> <b>{active_accounts}</b> Live\n"
        f"👑 <b>Owner ID:</b> <code>{OWNER_ID}</code>\n"
        f"👥 <b>Admin IDs:</b> <code>{', '.join(str(a) for a in ADMIN_IDS)}</code>\n"
        f"📢 <b>Log Channel:</b> <code>{html.escape(log_chan_display)}</code>\n"
        f"⏰ <b>Startup Time:</b> <code>{start_time}</code>\n\n"
        "✨ <b>System Readiness:</b>\n"
        "• 🎙️ Voice Chat (VC) Join: <b>Ready</b> ✅\n"
        "• 🗳️ Native Poll &amp; Button Voting: <b>Ready</b> ✅\n"
        "• 🔥 Reactions &amp; Premium Emojis: <b>Ready</b> ✅\n"
        "• 👁️ Public &amp; Private Channel Views: <b>Ready</b> ✅\n"
        "• 🚪 Channel Join &amp; Auto-Leave: <b>Ready</b> ✅\n"
        "• 💬 Bulk DM &amp; Group Broadcast: <b>Ready</b> ✅\n"
        "• ☁️ Cloud Auto-Restore (Multi-VPS): <b>Active</b> ✅\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Send /start to open the Control Panel.</i>"
    )

    # 1. Send direct message to Owner & all Admins
    for aid in admin_list:
        try:
            await target_bot.send_message(
                chat_id=aid,
                text=msg,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e:
            logging.debug(f"Could not send startup notice to admin {aid}: {e}")

    # 2. Send to Admin Log Channel
    if log_chan:
        await send_admin_log(msg, bot=target_bot)

def format_user_mention(user_id, first_name="", username=""):
    name = (first_name or "").strip() or f"User {user_id}"
    uname_str = f" (@{username})" if username and username.strip() not in ('None', 'none', '') else ""
    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a> (<code>{user_id}</code>{uname_str})'

async def log_campaign_to_admin_channel(user_id, action, target, accounts_used, success_count, failed_count, errors=None, extra_info=None, bot=None):
    """Send detailed campaign execution logs to the admin log channel."""
    user_info = get_user(user_id) or {}
    first_name = user_info.get("first_name", "")
    username = user_info.get("username", "")
    user_mention = format_user_mention(user_id, first_name, username)

    total = accounts_used or (success_count + failed_count)
    rate = int((success_count * 100) / total) if total > 0 else 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    extra_line = f"\nℹ️ <b>Details:</b> {html.escape(str(extra_info))}" if extra_info else ""

    err_line = ""
    if errors:
        if isinstance(errors, list):
            err_line = "\n❌ <b>Errors:</b>\n" + "\n".join([f"• <code>{html.escape(str(e)[:100])}</code>" for e in errors[:5]])
        else:
            err_line = f"\n❌ <b>Error:</b> <code>{html.escape(str(errors)[:200])}</code>"

    msg = (
        f"📢 <b>CAMPAIGN EXECUTED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Initiator:</b> {user_mention}\n"
        f"🎯 <b>Action:</b> <code>{html.escape(str(action))}</code>\n"
        f"🔗 <b>Target:</b> <code>{html.escape(str(target))}</code>\n"
        f"👥 <b>Accounts Used:</b> <code>{total}</code>\n"
        f"✅ <b>Successful:</b> <code>{success_count}</code>\n"
        f"❌ <b>Failed:</b> <code>{failed_count}</code>\n"
        f"📊 <b>Success Rate:</b> <code>{rate}%</code>"
        f"{extra_line}"
        f"{err_line}\n"
        f"⏰ <b>Timestamp:</b> <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    asyncio.create_task(send_admin_log(msg, bot=bot))

async def log_account_addition_to_admin_channel(user_id, account, is_refresh=False, bot=None):
    """Send detailed account addition/refresh log to the admin log channel."""
    user_info = get_user(user_id) or {}
    first_name = user_info.get("first_name", "")
    username = user_info.get("username", "")
    user_mention = format_user_mention(user_id, first_name, username)

    acc_phone = account.get("phone", "N/A")
    acc_name = account.get("first_name", "N/A")
    acc_uname = account.get("username")
    acc_uname_str = f"@{acc_uname}" if acc_uname and acc_uname not in ("None", "none", "No username", "") else "None"
    acc_tg_id = account.get("user_id", "N/A")
    acc_type = str(account.get("type", "session")).replace("_", " ").title()
    total_accs = len(load_accounts(user_id))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    header = "♻️ <b>ACCOUNT REFRESHED / UPDATED</b>" if is_refresh else "🆕 <b>NEW ACCOUNT ADDED</b>"

    msg = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Added By:</b> {user_mention}\n"
        f"📱 <b>Account Phone:</b> <code>{acc_phone}</code>\n"
        f"🆔 <b>Telegram ID:</b> <code>{acc_tg_id}</code>\n"
        f"📛 <b>Name:</b> {html.escape(str(acc_name))}\n"
        f"🏷️ <b>Username:</b> {html.escape(acc_uname_str)}\n"
        f"📦 <b>Format:</b> <code>{acc_type}</code>\n"
        f"🟢 <b>Status:</b> Authorized & Live ✅\n"
        f"📊 <b>Total User Accounts:</b> <code>{total_accs}</code>\n"
        f"⏰ <b>Timestamp:</b> <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    asyncio.create_task(send_admin_log(msg, bot=bot))

async def log_bulk_accounts_to_admin_channel(user_id, total_found, added_count, refreshed_count, failed_count, kind="Bulk Sessions", bot=None):
    """Send detailed bulk account addition log to the admin log channel."""
    user_info = get_user(user_id) or {}
    first_name = user_info.get("first_name", "")
    username = user_info.get("username", "")
    user_mention = format_user_mention(user_id, first_name, username)
    total_accs = len(load_accounts(user_id))
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    msg = (
        f"📦 <b>BULK ACCOUNTS ADDED</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Added By:</b> {user_mention}\n"
        f"📥 <b>Source / File:</b> <code>{html.escape(kind)}</code>\n"
        f"📄 <b>Total Found:</b> <code>{total_found}</code>\n"
        f"✅ <b>Newly Added:</b> <code>{added_count}</code>\n"
        f"♻️ <b>Refreshed / Updated:</b> <code>{refreshed_count}</code>\n"
        f"❌ <b>Failed / Invalid:</b> <code>{failed_count}</code>\n"
        f"📊 <b>Total User Accounts:</b> <code>{total_accs}</code>\n"
        f"⏰ <b>Timestamp:</b> <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    asyncio.create_task(send_admin_log(msg, bot=bot))

# ========== USER OPERATIONS (MONGODB) ==========

def get_user(user_id):
    """Return user dict from MongoDB users collection."""
    if MONGO_DB is None:
        return None
    try:
        doc = MONGO_DB.users.find_one({"user_id": user_id})
        if doc:
            doc = dict(doc)
            doc.pop("_id", None)
            doc.setdefault("accounts", [])
            doc.setdefault("settings", {"delay": DEFAULT_DELAY})
            return doc
        return None
    except Exception as e:
        logging.error(f"get_user error: {e}")
        return None

def create_user_if_not_exists(user_id, username="", first_name=""):
    """Create a user document in MongoDB users collection if not exists, or update profile info."""
    if MONGO_DB is None:
        return
    now_str = str(datetime.now())
    try:
        clean_u = str(username).strip().lstrip("@") if username else ""
        if clean_u.lower() in ("none", "null", "no username", "owner", f"admin_{user_id}".lower()):
            clean_u = ""
        clean_fn = str(first_name).strip() if first_name else ""
        if clean_fn.lower() in ("none", "null", "owner", "admin"):
            clean_fn = ""

        update_set = {}
        if clean_u:
            update_set["username"] = clean_u
        if clean_fn:
            update_set["first_name"] = clean_fn

        on_insert = {
            "user_id": user_id,
            "joined_date": now_str,
            "is_banned": 0,
            "access_expiry": None,
            "shared_id_limit": 0,
            "is_admin": 1 if (user_id == OWNER_ID or user_id in ADMIN_IDS) else 0,
            "accounts": [],
            "settings": {"delay": DEFAULT_DELAY}
        }
        if not clean_u:
            on_insert["username"] = ""
        if not clean_fn:
            on_insert["first_name"] = ""

        update_doc = {"$setOnInsert": on_insert}
        if update_set:
            update_doc["$set"] = update_set

        MONGO_DB.users.update_one(
            {"user_id": user_id},
            update_doc,
            upsert=True
        )
    except Exception as e:
        logging.error(f"create_user_if_not_exists error: {e}")

def get_all_users():
    """Retrieve all users from MongoDB users collection."""
    if MONGO_DB is None:
        return []
    try:
        cursor = MONGO_DB.users.find().sort("joined_date", -1)
        users = []
        for doc in cursor:
            users.append((
                doc.get("user_id"),
                doc.get("username", ""),
                doc.get("first_name", ""),
                doc.get("joined_date", ""),
                doc.get("is_banned", 0),
                doc.get("access_expiry"),
                doc.get("shared_id_limit", 0),
                doc.get("is_admin", 0)
            ))
        return users
    except Exception as e:
        logging.error(f"get_all_users error: {e}")
        return []

def ban_user(user_id):
    """Ban user in MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.users.update_one({"user_id": user_id}, {"$set": {"is_banned": 1}})
    except Exception as e:
        logging.error(f"ban_user error: {e}")

def unban_user(user_id):
    """Unban user in MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.users.update_one({"user_id": user_id}, {"$set": {"is_banned": 0}})
    except Exception as e:
        logging.error(f"unban_user error: {e}")

def delete_user(user_id):
    """Delete a user document from MongoDB."""
    if MONGO_DB is None or user_id == OWNER_ID:
        return False
    try:
        MONGO_DB.users.delete_one({"user_id": user_id})
        return True
    except Exception as e:
        logging.error(f"delete_user error: {e}")
        return False

def is_banned(user_id):
    """Check if user is banned."""
    user = get_user(user_id)
    return bool(user and user.get("is_banned", 0) == 1)

def grant_admin(user_id):
    """Grant admin privileges to user in MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.users.update_one({"user_id": user_id}, {"$set": {"is_admin": 1}})
    except Exception as e:
        logging.error(f"grant_admin error: {e}")

def revoke_admin(user_id):
    """Revoke admin privileges from user in MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.users.update_one({"user_id": user_id}, {"$set": {"is_admin": 0}})
    except Exception as e:
        logging.error(f"revoke_admin error: {e}")

def is_admin_user(user_id):
    """Check if user has admin privileges or is Owner."""
    if user_id == OWNER_ID or user_id in ADMIN_IDS:
        return True
    user = get_user(user_id)
    return bool(user and user.get("is_admin", 0) == 1)

def is_owner(user_id):
    """Check if user is bot Owner or Admin."""
    return user_id == OWNER_ID or user_id in ADMIN_IDS

# ========== ACCESS & SUBSCRIPTION (MONGODB) ==========

def set_user_access(user_id, days):
    """Set access expiry for a user in MongoDB."""
    if MONGO_DB is None:
        return
    expiry = datetime.now() + timedelta(days=days)
    try:
        MONGO_DB.users.update_one(
            {"user_id": user_id},
            {"$set": {"access_expiry": expiry.isoformat()}},
            upsert=True
        )
    except Exception as e:
        logging.error(f"set_user_access error: {e}")

def give_access(user_id, days, shared_id_limit):
    """Give access with shared limit in MongoDB."""
    if MONGO_DB is None:
        return
    expiry = datetime.now() + timedelta(days=days)
    expiry_str = expiry.isoformat()
    try:
        MONGO_DB.users.update_one(
            {"user_id": user_id},
            {
                "$set": {"access_expiry": expiry_str, "shared_id_limit": shared_id_limit},
                "$setOnInsert": {
                    "user_id": user_id,
                    "username": "",
                    "first_name": "",
                    "joined_date": str(datetime.now()),
                    "is_banned": 0,
                    "is_admin": 0,
                    "accounts": [],
                    "settings": {"delay": DEFAULT_DELAY}
                }
            },
            upsert=True
        )
    except Exception as e:
        logging.error(f"give_access error: {e}")

def remove_user_access(user_id):
    """Remove access expiry for a user in MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.users.update_one(
            {"user_id": user_id},
            {"$set": {"access_expiry": None, "shared_id_limit": 0}}
        )
    except Exception as e:
        logging.error(f"remove_user_access error: {e}")

def has_access(user_id):
    """Check if user has active access."""
    if is_owner(user_id):
        return True, "Owner"
    user = get_user(user_id)
    if not user:
        return False, None
    if user.get("is_admin", 0) == 1:
        return True, "Admin"
    expiry_str = user.get("access_expiry")
    if not expiry_str:
        return False, None
    try:
        expiry = datetime.fromisoformat(expiry_str)
        if expiry > datetime.now():
            return True, expiry.strftime("%Y-%m-%d")
    except Exception:
        pass
    return False, None

def set_user_shared_limit(user_id, limit):
    """Set shared account limit in MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.users.update_one(
            {"user_id": user_id},
            {"$set": {"shared_id_limit": limit}},
            upsert=True
        )
    except Exception as e:
        logging.error(f"set_user_shared_limit error: {e}")

def get_user_shared_limit(user_id):
    """Get shared account limit from MongoDB."""
    user = get_user(user_id)
    if user:
        return user.get("shared_id_limit", 0)
    return 0

# ========== ACCOUNTS OPERATIONS (MONGODB) ==========

def load_accounts(user_id):
    """Load accounts from user document in MongoDB, deduplicated by session string and phone."""
    user = get_user(user_id)
    if not user:
        return []
    raw = user.get("accounts", [])
    seen_strings = set()
    seen_phones = set()
    deduped = []
    for acc in raw:
        s = str(acc.get("session_string") or "").strip()
        p = str(acc.get("phone") or "").strip().lstrip("+")
        if s and s in seen_strings:
            continue
        if p and p.isdigit() and p in seen_phones:
            continue
        if s:
            seen_strings.add(s)
        if p and p.isdigit():
            seen_phones.add(p)
        deduped.append(acc)
    return deduped

def save_accounts(user_id, accounts):
    """Save accounts to user document in MongoDB. Strictly ensures 1 account is never duplicated."""
    if MONGO_DB is None:
        return
    seen_strings = set()
    seen_phones = set()
    accounts_to_save = []
    for acc in accounts:
        acc_copy = acc.copy()
        acc_copy.pop('client', None)
        s_str = str(acc_copy.get('session_string') or '').strip()
        phone_raw = str(acc_copy.get('phone') or '').strip().lstrip('+')
        if s_str:
            if s_str in seen_strings:
                continue
            seen_strings.add(s_str)
        if phone_raw and phone_raw.isdigit():
            if phone_raw in seen_phones:
                continue
            seen_phones.add(phone_raw)
        accounts_to_save.append(acc_copy)
    try:
        MONGO_DB.users.update_one(
            {"user_id": user_id},
            {"$set": {"accounts": accounts_to_save}},
            upsert=True
        )
    except Exception as e:
        logging.error(f"save_accounts error: {e}")

def load_all_bot_accounts():
    """
    Loads ALL unique accounts directly from MongoDB cloud storage only.
    Strictly deduplicates by session_string (cryptographic auth key), phone number, and Telegram user_id.
    Does NOT include local disk files (preventing duplicates).
    Ensures 1 account is NEVER duplicated.
    """
    combined = []
    seen_session_strings = set()
    seen_phones = set()
    seen_tele_uids = set()

    if MONGO_DB is None:
        return []

    try:
        all_user_docs = list(MONGO_DB.users.find({}, {"user_id": 1, "accounts": 1}))

        # Collect all account objects across all user documents
        all_accounts = []
        for u in all_user_docs:
            for acc in u.get("accounts", []):
                all_accounts.append(acc)

        # Prioritize accounts that have real phone numbers and real user IDs
        def acc_quality_key(a):
            p = str(a.get("phone") or "")
            uid = a.get("user_id")
            has_real_phone = bool(p and not p.startswith("user_") and p.strip().lstrip("+").isdigit())
            has_uid = bool(uid and str(uid).isdigit())
            return (1 if has_real_phone else 0, 1 if has_uid else 0)

        all_accounts.sort(key=acc_quality_key, reverse=True)

        for acc in all_accounts:
            sess_str = str(acc.get("session_string") or "").strip()
            if not sess_str:
                continue

            phone_raw = str(acc.get("phone") or "").strip().lstrip("+")
            tele_uid = str(acc.get("user_id") or "").strip()

            # Deduplication:
            # 1. By session_string (the true cryptographic identity)
            if sess_str in seen_session_strings:
                continue

            # 2. By real phone number if it is a real numeric phone
            if phone_raw and phone_raw.isdigit() and phone_raw in seen_phones:
                continue

            # 3. By Telegram user_id if known
            if tele_uid and tele_uid != "None" and tele_uid.isdigit() and tele_uid in seen_tele_uids:
                continue

            # Record as seen
            seen_session_strings.add(sess_str)
            if phone_raw and phone_raw.isdigit():
                seen_phones.add(phone_raw)
            if tele_uid and tele_uid != "None" and tele_uid.isdigit():
                seen_tele_uids.add(tele_uid)

            combined.append(acc)

    except Exception as e:
        logging.error(f"load_all_bot_accounts error: {e}")

    return combined

def load_owner_accounts():
    """Load all accounts across the entire bot for Owner and Administrators."""
    return load_all_bot_accounts()

def get_accessible_accounts(user_id):
    """
    Get accessible accounts for a user:
    - Owner and Admins have access to ALL accounts in the bot (entire pool of 110+ accounts).
    - Regular users get their own personal accounts PLUS a configured quota of random accounts from the bot pool.
    """
    # 1. Owner and Admins get ALL accounts in the bot
    if is_owner(user_id) or is_admin_user(user_id):
        return load_all_bot_accounts()

    # 2. Regular user check for active access
    has_acc, _ = has_access(user_id)
    if not has_acc:
        return []

    # 3. Personal accounts added by this individual user
    personal = load_accounts(user_id)
    shared_limit = get_user_shared_limit(user_id)

    if shared_limit <= 0:
        return personal

    all_pool = load_all_bot_accounts()
    personal_keys = {
        str(a.get('phone') or a.get('session') or a.get('user_id') or '').strip().lstrip('+')
        for a in personal
    }
    personal_strings = {
        str(a.get('session_string') or '').strip()
        for a in personal if a.get('session_string')
    }
    available_shared = [
        a for a in all_pool
        if str(a.get('session_string') or '').strip() not in personal_strings
        and str(a.get('phone') or a.get('session') or a.get('user_id') or '').strip().lstrip('+') not in personal_keys
    ]

    if not available_shared:
        return personal

    # Consistent random selection per user from available pool
    rng = random.Random(user_id)
    if len(available_shared) <= shared_limit:
        shared_to_use = available_shared
    else:
        shared_to_use = rng.sample(available_shared, shared_limit)

    return personal + shared_to_use

# ========== USER SETTINGS (MONGODB) ==========

def load_settings(user_id):
    """Load user settings dictionary from MongoDB."""
    user = get_user(user_id)
    if user:
        return user.get("settings", {"delay": DEFAULT_DELAY})
    return {"delay": DEFAULT_DELAY}

def save_settings(user_id, settings):
    """Save user settings dictionary to MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.users.update_one(
            {"user_id": user_id},
            {"$set": {"settings": settings}},
            upsert=True
        )
    except Exception as e:
        logging.error(f"save_settings error: {e}")

# ========== CAMPAIGNS OPERATIONS (MONGODB) ==========

def load_campaigns(user_id):
    """Load recent campaigns from MongoDB campaigns collection."""
    if MONGO_DB is None:
        return []
    try:
        cursor = MONGO_DB.campaigns.find({"user_id": user_id}).sort("timestamp", -1).limit(50)
        campaigns = []
        for doc in cursor:
            doc = dict(doc)
            doc.pop("_id", None)
            campaigns.append(doc)
        return campaigns
    except Exception as e:
        logging.error(f"load_campaigns error: {e}")
        return []

def save_campaign(user_id, campaign):
    """Save executed campaign to MongoDB campaigns collection."""
    if MONGO_DB is None:
        return
    try:
        last = MONGO_DB.campaigns.find_one(sort=[("id", -1)])
        next_id = (last.get("id", 0) + 1) if last else 1
        doc = {
            "id": next_id,
            "user_id": user_id,
            "action": campaign.get('action'),
            "target": campaign.get('target'),
            "result": campaign.get('result'),
            "status": campaign.get('status'),
            "timestamp": campaign.get('timestamp', datetime.now().isoformat()),
            "accounts_used": campaign.get('accounts_used', 0),
            "success_count": campaign.get('success_count', 0),
            "failed_count": campaign.get('failed_count', 0)
        }
        MONGO_DB.campaigns.insert_one(doc)
    except Exception as e:
        logging.error(f"save_campaign error: {e}")

# ========== SCHEDULED TASKS (MONGODB) ==========

def load_scheduled(user_id):
    """Load pending scheduled campaigns from MongoDB scheduled collection."""
    if MONGO_DB is None:
        return []
    try:
        cursor = MONGO_DB.scheduled.find({"user_id": user_id, "status": "pending"})
        return [
            (d.get("id"), d.get("action"), d.get("target"), d.get("scheduled_time"), d.get("account_count"), d.get("spam_message"))
            for d in cursor
        ]
    except Exception as e:
        logging.error(f"load_scheduled error: {e}")
        return []

def save_scheduled(user_id, action, target, scheduled_time, account_count, spam_message=""):
    """Schedule a task in MongoDB scheduled collection."""
    if MONGO_DB is None:
        return
    try:
        last = MONGO_DB.scheduled.find_one(sort=[("id", -1)])
        next_id = (last.get("id", 0) + 1) if last else 1
        doc = {
            "id": next_id,
            "user_id": user_id,
            "action": action,
            "target": target,
            "scheduled_time": scheduled_time,
            "account_count": account_count,
            "spam_message": spam_message,
            "status": "pending"
        }
        MONGO_DB.scheduled.insert_one(doc)
    except Exception as e:
        logging.error(f"save_scheduled error: {e}")

def delete_scheduled(schedule_id):
    """Delete a scheduled task from MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.scheduled.delete_one({"id": schedule_id})
    except Exception as e:
        logging.error(f"delete_scheduled error: {e}")

def update_scheduled_status(schedule_id, status):
    """Update scheduled task status in MongoDB."""
    if MONGO_DB is None:
        return
    try:
        MONGO_DB.scheduled.update_one({"id": schedule_id}, {"$set": {"status": status}})
    except Exception as e:
        logging.error(f"update_scheduled_status error: {e}")

def get_pending_schedules():
    """Retrieve all pending schedules ready for execution from MongoDB."""
    if MONGO_DB is None:
        return []
    now_local_iso = datetime.now().isoformat()
    now_local_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    now_utc_iso = datetime.now(timezone.utc).isoformat()
    try:
        cursor = MONGO_DB.scheduled.find({
            "status": "pending",
            "$or": [
                {"scheduled_time": {"$lte": now_local_iso}},
                {"scheduled_time": {"$lte": now_local_str}},
                {"scheduled_time": {"$lte": now_utc_str}},
                {"scheduled_time": {"$lte": now_utc_iso}}
            ]
        })
        return [
            (d.get("id"), d.get("user_id"), d.get("action"), d.get("target"), d.get("scheduled_time"), d.get("account_count"), d.get("spam_message"))
            for d in cursor
        ]
    except Exception as e:
        logging.error(f"get_pending_schedules error: {e}")
        return []

# ========== ACCOUNT LIVENESS & BATCH OPERATIONS ==========
async def check_account_status_full(account, force_check=False):
    """
    Evaluates account liveness with strict distinction between:
    - 'live': confirmed connected and authorized
    - 'expired': confirmed unauthorized, revoked, or banned
    - 'error': temporary timeout or network drop (NOT expired!)
    """
    if not account or not isinstance(account, dict):
        return 'expired', 'Invalid account structure'

    phone = account.get('phone')
    sess_str = account.get('session_string')
    sess_path = account.get('session')
    user_id_tg = account.get('user_id')

    # Normalized key for caching and tracking
    raw_key = str(phone or user_id_tg or sess_path or '')
    clean_key = raw_key.strip().lstrip('+')
    if not clean_key and sess_str:
        clean_key = hashlib.md5(sess_str.encode()).hexdigest()[:12]

    if not clean_key:
        return 'expired', 'No phone or session identifier'

    # Check frozen flag
    if is_account_frozen(account) or is_account_frozen(clean_key):
        return 'expired', 'Frozen by Telegram'

    # Check FloodWait cooldown
    if is_account_on_cooldown(clean_key) or (phone and is_account_on_cooldown(phone)):
        return 'live', 'Account in protective cooldown (alive)'

    now = time.time()
    # Check cache if not forcing fresh check
    if not force_check and clean_key in LIVE_CACHE:
        val, ts, is_def = LIVE_CACHE[clean_key] if len(LIVE_CACHE[clean_key]) == 3 else (LIVE_CACHE[clean_key][0], LIVE_CACHE[clean_key][1], True)
        if now - ts < CACHE_TIME:
            return ('live' if val else 'expired'), 'From cache'

    # Check active client in memory
    if clean_key in ACTIVE_CLIENTS:
        client = ACTIVE_CLIENTS[clean_key]
        try:
            if client.is_connected():
                auth = await asyncio.wait_for(client.is_user_authorized(), timeout=4)
                if auth:
                    LIVE_CACHE[clean_key] = (True, now, True)
                    return 'live', 'Active client authorized'
                else:
                    LIVE_CACHE[clean_key] = (False, now, True)
                    ACTIVE_CLIENTS.pop(clean_key, None)
                    return 'expired', 'Active client not authorized'
        except (AuthKeyUnregisteredError, AuthKeyDuplicatedError, UserDeactivatedError, UserDeactivatedBanError):
            LIVE_CACHE[clean_key] = (False, now, True)
            ACTIVE_CLIENTS.pop(clean_key, None)
            return 'expired', 'Auth key revoked'
        except Exception:
            # Temporary network issue with existing socket, proceed to reconnect
            pass

    # Ensure telethon session string exists
    if not sess_str and sess_path:
        sess_file = f"{sess_path}.session" if not sess_path.endswith('.session') else sess_path
        if os.path.exists(sess_file):
            try:
                sess_str = telethon_sqlite_to_string_session(sess_file)
                if sess_str:
                    account['session_string'] = sess_str
            except Exception:
                pass

    if not sess_str:
        return 'expired', 'Missing session string'

    valid_str = ensure_telethon_session_string(sess_str)
    if not valid_str:
        return 'expired', 'Corrupt session string format'

    client = None
    try:
        client = create_telegram_client(StringSession(valid_str), phone=phone, account=account)
        await asyncio.wait_for(client.connect(), timeout=7)
        auth = await asyncio.wait_for(client.is_user_authorized(), timeout=4)
        if auth:
            LIVE_CACHE[clean_key] = (True, now, True)
            if clean_key:
                client._phone = clean_key
                ACTIVE_CLIENTS[clean_key] = client
            return 'live', 'Authorized'
        else:
            # Telegram explicitly says NOT authorized
            LIVE_CACHE[clean_key] = (False, now, True)
            ACTIVE_CLIENTS.pop(clean_key, None)
            try:
                await client.disconnect()
            except Exception:
                pass
            return 'expired', 'Unauthorized by Telegram'
    except FloodWaitError as e:
        set_account_cooldown(clean_key, e.seconds)
        LIVE_CACHE[clean_key] = (True, now, True)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        return 'live', f'FloodWait {e.seconds}s'
    except (SessionPasswordNeededError, AuthKeyUnregisteredError, AuthKeyDuplicatedError, UserDeactivatedError, UserDeactivatedBanError):
        LIVE_CACHE[clean_key] = (False, now, True)
        ACTIVE_CLIENTS.pop(clean_key, None)
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        return 'expired', 'Auth key revoked or banned'
    except (asyncio.TimeoutError, ConnectionError, OSError) as e:
        # Temporary network drop or DC throttle: DO NOT CACHE AS EXPIRED!
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        return 'error', f'Network timeout ({type(e).__name__})'
    except Exception as e:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
        err_str = str(e).lower()
        if "flood" in err_str:
            set_account_cooldown(clean_key, 60)
            LIVE_CACHE[clean_key] = (True, now, True)
            return 'live', 'Flood cooldown'
        if "frozen" in err_str:
            mark_account_frozen(clean_key)
            return 'expired', 'Frozen'
        if any(k in err_str for k in ("deactivated", "banned", "revoked", "unregistered", "auth_key", "duplicate")):
            LIVE_CACHE[clean_key] = (False, now, True)
            ACTIVE_CLIENTS.pop(clean_key, None)
            return 'expired', 'Revoked/Banned'
        # Unknown network/runtime exception: DO NOT MARK AS EXPIRED!
        return 'error', str(e)[:50]

async def is_account_live(account):
    """Checks if an account is live. Returns True if live or experiencing temporary network error, False ONLY if definitively expired."""
    status, _ = await check_account_status_full(account)
    return status != 'expired'

async def get_live_accounts_batch(accounts, max_concurrency=8):
    """Checks accounts concurrently with bounded concurrency and pacing to prevent DC throttling."""
    if not accounts:
        return []
    sem = asyncio.Semaphore(max_concurrency)
    async def _chk(acc):
        async with sem:
            try:
                status, _ = await check_account_status_full(acc)
                return acc if status != 'expired' else None
            except Exception:
                # If unexpected check error, preserve account as live
                return acc
            finally:
                await asyncio.sleep(0.02)
    results = await asyncio.gather(*(_chk(a) for a in accounts), return_exceptions=True)
    return [r for r in results if r and not isinstance(r, Exception)]

async def get_expired_accounts_batch(accounts, max_concurrency=8):
    """Returns only accounts that are CONFIRMED expired/revoked/banned on Telegram."""
    if not accounts:
        return []
    sem = asyncio.Semaphore(max_concurrency)
    async def _chk(acc):
        async with sem:
            try:
                status, _ = await check_account_status_full(acc)
                return acc if status == 'expired' else None
            except Exception:
                return None
            finally:
                await asyncio.sleep(0.02)
    results = await asyncio.gather(*(_chk(a) for a in accounts), return_exceptions=True)
    return [r for r in results if r and not isinstance(r, Exception)]

async def get_client_for_account(account):
    """Retrieves or creates a TelegramClient with genuine mobile device fingerprinting."""
    phone = account.get('phone')
    session_string = account.get('session_string')
    session_path = account.get('session')

    # If session_string is missing, extract it from session_path SQLite file
    if not session_string and session_path:
        session_file = f"{session_path}.session" if not session_path.endswith('.session') else session_path
        if os.path.exists(session_file):
            try:
                session_string = telethon_sqlite_to_string_session(session_file)
                if session_string:
                    account['session_string'] = session_string
                    if MONGO_DB is not None and account.get('user_id'):
                        try:
                            accs = load_accounts(account.get('user_id'))
                            for a in accs:
                                if a.get('phone') == phone:
                                    a['session_string'] = session_string
                            save_accounts(account.get('user_id'), accs)
                        except Exception:
                            pass
            except Exception:
                pass

    if session_string:
        valid_sess = ensure_telethon_session_string(session_string)
        if valid_sess:
            session_string = valid_sess

    # Fast path: active connected client in memory
    p_key = str(phone or account.get('user_id') or account.get('session') or '').strip().lstrip('+')
    if p_key and p_key in ACTIVE_CLIENTS:
        client = ACTIVE_CLIENTS[p_key]
        try:
            if client.is_connected():
                client._phone = p_key
                return client
            else:
                await asyncio.wait_for(client.connect(), timeout=7)
                client._phone = p_key
                return client
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass
            ACTIVE_CLIENTS.pop(p_key, None)

    if session_string:
        client = None
        try:
            client = create_telegram_client(StringSession(session_string), phone=phone, account=account)
            await asyncio.wait_for(client.connect(), timeout=7)
            if await asyncio.wait_for(client.is_user_authorized(), timeout=4):
                if p_key:
                    client._phone = p_key
                    ACTIVE_CLIENTS[p_key] = client
                return client
            else:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        except FloodWaitError as e:
            if phone or p_key:
                set_account_cooldown(phone or p_key, e.seconds)
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        except Exception:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    if session_path:
        client = None
        try:
            session_file = f"{session_path}.session" if not session_path.endswith('.session') else session_path
            if os.path.exists(session_file):
                s_str = telethon_sqlite_to_string_session(session_file)
                if s_str:
                    client = create_telegram_client(StringSession(s_str), phone=phone, account=account)
                else:
                    client = create_telegram_client(session_path, phone=phone, account=account)
                await asyncio.wait_for(client.connect(), timeout=7)
                if await asyncio.wait_for(client.is_user_authorized(), timeout=4):
                    if p_key:
                        client._phone = p_key
                        ACTIVE_CLIENTS[p_key] = client
                    return client
                else:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
        except FloodWaitError as e:
            if phone or p_key:
                set_account_cooldown(phone or p_key, e.seconds)
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass
        except Exception:
            if client:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    return None


# ========== PREMIUM REACTION DETECTION ==========
async def detect_premium_reaction(client, link):
    """Fetch reactions on the given post and return first custom emoji ID or None."""
    try:
        peer, msg_id = await resolve_peer_and_msg(client, link)
        if not peer or not msg_id:
            return None

        # Fetch message (do NOT use 'reactions' parameter)
        msg = await client.get_messages(peer, ids=msg_id)
        if not msg or not hasattr(msg, 'reactions') or not msg.reactions:
            return None

        for reaction in msg.reactions.results:
            if isinstance(reaction.reaction, ReactionCustomEmoji):
                return str(reaction.reaction.document_id)
        return None
    except Exception as e:
        logging.error(f"Error detecting premium reaction: {e}")
        return None

# ========== PRIVATE CHANNEL VIEW ==========
async def private_channel_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    WAITING_FOR[user_id] = 'private_view_link'

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg_text = """🔒 PRIVATE CHANNEL VIEW

Send private channel invite link or message link:
• https://t.me/joinchat/xxxxx (invite link)
• https://t.me/c/123456789/123 (message link)

Bot will auto-join and send views from ALL your accounts!"""

    if update.callback_query:
        await update.callback_query.edit_message_text(msg_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg_text, reply_markup=reply_markup)

async def handle_private_view(update: Update, context: ContextTypes.DEFAULT_TYPE, link: str):
    user_id = update.effective_user.id
    accs = get_accessible_accounts(user_id)

    if not accs:
        await update.message.reply_text("❌ No accessible accounts!")
        WAITING_FOR.pop(user_id, None)
        return

    invite_hash = None
    channel_id = None
    msg_id = None

    try:
        if 't.me/joinchat/' in link or 't.me/+' in link:
            if 't.me/joinchat/' in link:
                invite_hash = link.split('t.me/joinchat/')[-1].split('/')[0].split('?')[0]
            else:
                invite_hash = link.split('t.me/+')[-1].split('/')[0].split('?')[0]
        elif 't.me/c/' in link:
            parts = link.split('t.me/c/')[1].split('/')
            channel_id = int(parts[0])
            msg_id = int(parts[1].split('?')[0])
        else:
            await update.message.reply_text("❌ Invalid private channel link!")
            WAITING_FOR.pop(user_id, None)
            return

    except Exception as e:
        await update.message.reply_text(f"❌ Error parsing link: {str(e)[:100]}")
        WAITING_FOR.pop(user_id, None)
        return

    WAITING_FOR.pop(user_id, None)

    status_msg = await update.message.reply_text(
        f"🔒 PROCESSING PRIVATE CHANNEL VIEW\n\n"
        f"📊 Total Accounts: {len(accs)}\n"
        f"⏳ Joining channel and sending views..."
    )

    results = {
        'joined': 0,
        'already_joined': 0,
        'views_sent': 0,
        'failed': 0
    }

    for i, acc in enumerate(accs):
        try:
            client = await get_client_for_account(acc)

            if not client:
                results['failed'] += 1
                continue

            entity = None

            if invite_hash:
                try:
                    updates = await client(ImportChatInviteRequest(invite_hash))
                    if updates.chats:
                        entity = updates.chats[0]
                        results['joined'] += 1
                    await asyncio.sleep(1)
                except UserAlreadyParticipantError:
                    results['already_joined'] += 1
                    try:
                        invited = await client(CheckChatInviteRequest(invite_hash))
                        if hasattr(invited, 'chat') and invited.chat:
                            entity = invited.chat
                    except Exception:
                        results['failed'] += 1
                        continue
                except Exception as e:
                    results['failed'] += 1
                    continue
            elif channel_id:
                try:
                    entity = await client.get_entity(PeerChannel(channel_id))
                    results['already_joined'] += 1
                except Exception:
                    results['failed'] += 1
                    continue

            if not entity:
                results['failed'] += 1
                continue

            if hasattr(entity, 'id'):
                target_channel_id = entity.id
            else:
                target_channel_id = channel_id

            try:
                if msg_id:
                    view_result = await client(GetMessagesViewsRequest(
                        peer=PeerChannel(target_channel_id),
                        id=[msg_id],
                        increment=True
                    ))
                    results['views_sent'] += 1
                else:
                    messages = await client.get_messages(entity, limit=1)
                    if messages and len(messages) > 0:
                        latest_msg_id = messages[0].id
                        view_result = await client(GetMessagesViewsRequest(
                            peer=PeerChannel(target_channel_id),
                            id=[latest_msg_id],
                            increment=True
                        ))
                        results['views_sent'] += 1
                    else:
                        results['failed'] += 1

            except Exception as e:
                try:
                    if msg_id:
                        message = await client.get_messages(entity, ids=msg_id)
                    else:
                        message = await client.get_messages(entity, limit=1)
                        if message:
                            msg_id = message[0].id

                    if message:
                        await client.send_read_acknowledge(entity, max_id=msg_id)
                        results['views_sent'] += 1
                    else:
                        results['failed'] += 1
                except Exception:
                    results['failed'] += 1

        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 10))
            results['failed'] += 1
        except Exception as e:
            results['failed'] += 1

        if (i + 1) % 3 == 0 or (i + 1) == len(accs):
            try:
                await status_msg.edit_text(
                    f"🔒 PROGRESS: {i+1}/{len(accs)}\n\n"
                    f"✅ Joined: {results['joined']}\n"
                    f"⚠️ Already joined: {results['already_joined']}\n"
                    f"👁️ Views sent: {results['views_sent']}\n"
                    f"❌ Failed: {results['failed']}"
                )
            except Exception:
                pass

        delay = load_settings(user_id).get('delay', DEFAULT_DELAY)
        await asyncio.sleep(delay)

    success_rate = int(results['views_sent'] / len(accs) * 100) if results['views_sent'] > 0 else 0

    await status_msg.edit_text(
        f"✅ PRIVATE CHANNEL VIEW COMPLETED!\n\n"
        f"📊 FINAL RESULTS:\n"
        f"✅ Joined channel: {results['joined']}\n"
        f"⚠️ Already members: {results['already_joined']}\n"
        f"👁️ Views sent: {results['views_sent']}\n"
        f"❌ Failed: {results['failed']}\n"
        f"📈 Success rate: {success_rate}%\n\n"
        f"💡 Note: Views may take 1-2 minutes to update on Telegram"
    )

    priv_camp_data = {
        'action': 'Private Channel View',
        'target': link,
        'result': f"Joined {results['joined']} / Views {results['views_sent']} / Failed {results['failed']}",
        'status': 'completed',
        'timestamp': str(datetime.now()),
        'accounts_used': len(accs),
        'success_count': results['views_sent'],
        'failed_count': results['failed']
    }
    save_campaign(user_id, priv_camp_data)
    await log_campaign_to_admin_channel(
        user_id=user_id,
        action='Private Channel View',
        target=link,
        accounts_used=len(accs),
        success_count=results['views_sent'],
        failed_count=results['failed'],
        extra_info=f"Joined: {results['joined']}, Already members: {results['already_joined']}",
        bot=context.bot
    )

# ========== VC JOIN FUNCTION ==========
async def join_voice_chat_func(client, link):
    """Join voice chat with mic off and compliant WebRTC SSRC signaling payload."""
    try:
        import random, string, json
        from telethon.tl.functions.channels import GetFullChannelRequest, JoinChannelRequest
        from telethon.tl.functions.messages import GetFullChatRequest, ImportChatInviteRequest, CheckChatInviteRequest
        from telethon.tl.functions.phone import JoinGroupCallRequest
        from telethon.tl.types import Channel, InputGroupCall, DataJSON
        from telethon.errors import UserAlreadyParticipantError

        link = link.strip().replace('https://', '').replace('http://', '')
        chat_entity = None

        # 1. Handle private invite links (t.me/+hash or t.me/joinchat/hash)
        if 't.me/+' in link or 'joinchat' in link:
            if 't.me/+' in link:
                hash_part = link.split('t.me/+')[-1].split('/')[0].split('?')[0]
            else:
                hash_part = link.split('joinchat/')[-1].split('/')[0].split('?')[0]
            try:
                updates = await client(ImportChatInviteRequest(hash_part))
                if getattr(updates, 'chats', None):
                    chat_entity = updates.chats[0]
            except UserAlreadyParticipantError:
                try:
                    invited = await client(CheckChatInviteRequest(hash_part))
                    if getattr(invited, 'chat', None):
                        chat_entity = invited.chat
                except Exception:
                    pass
            except Exception as e:
                return False, f"Invite error: {str(e)[:30]}"

        # 2. Handle private channel/group links (t.me/c/123456/...)
        elif 't.me/c/' in link:
            parts = link.split('t.me/c/')[1].split('/')
            if parts:
                channel_id = int(parts[0])
                for candidate in [int(f"-100{channel_id}"), channel_id]:
                    try:
                        chat_entity = await client.get_entity(candidate)
                        break
                    except Exception:
                        pass

        # 3. Handle standard public username (t.me/username, @username, etc.)
        else:
            clean = link.replace('t.me/', '').lstrip('@').split('/')[0].split('?')[0]
            if not clean:
                return False, "Invalid voice chat link"
            try:
                chat_entity = await client.get_entity(clean)
            except Exception as e:
                return False, f"Chat not found: {str(e)[:30]}"

        if not chat_entity:
            return False, "Could not resolve chat entity"

        # Ensure account is in the channel/group before joining VC
        try:
            await client(JoinChannelRequest(chat_entity))
        except (UserAlreadyParticipantError, Exception):
            pass

        # Fetch full chat to locate active voice call
        try:
            if isinstance(chat_entity, Channel):
                full_chat = await client(GetFullChannelRequest(channel=chat_entity))
            else:
                try:
                    full_chat = await client(GetFullChannelRequest(channel=chat_entity))
                except Exception:
                    full_chat = await client(GetFullChatRequest(chat_id=chat_entity.id))
        except Exception as e:
            return False, f"Error getting chat details: {str(e)[:30]}"

        full_chat_obj = getattr(full_chat, 'full_chat', None)
        group_call = getattr(full_chat_obj, 'call', None) if full_chat_obj else None
        if not group_call or isinstance(group_call, GroupCallDiscarded):
            return False, "No active voice chat in this channel/group"

        if isinstance(group_call, InputGroupCall):
            call_input = group_call
        elif hasattr(group_call, 'id') and hasattr(group_call, 'access_hash'):
            call_input = InputGroupCall(id=group_call.id, access_hash=group_call.access_hash)
        else:
            return False, "No active voice chat in this channel/group"

        try:
            join_as_peer = InputPeerSelf()
        except Exception:
            try:
                join_as_peer = await client.get_input_entity('me')
            except Exception:
                me = await client.get_me()
                join_as_peer = await client.get_input_entity(me)

        # Attempt joining with dynamic WebRTC parameters & retry on SSRC collision
        last_err = ""
        for attempt in range(4):
            ssrc = random.randint(100000000, 999999999)
            ufrag = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
            pwd = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
            rand_bytes = random.randbytes(32)
            fp = ':'.join(f'{b:02X}' for b in rand_bytes)
            webrtc_payload = json.dumps({
                "ssrc": ssrc,
                "ufrag": ufrag,
                "pwd": pwd,
                "fingerprints": [
                    {
                        "hash": "sha-256",
                        "fingerprint": fp,
                        "setup": "passive"
                    }
                ]
            })

            try:
                result = await client(JoinGroupCallRequest(
                    call=call_input,
                    join_as=join_as_peer,
                    params=DataJSON(data=webrtc_payload),
                    muted=True,
                    video_stopped=True
                ))
                return True, "Joined voice chat (muted)"
            except GroupcallSsrcDuplicateMuchError:
                await asyncio.sleep(0.3)
                continue
            except Exception as e:
                last_err = str(e)
                err_lower = last_err.lower()
                if "already participant" in err_lower or "already in call" in err_lower:
                    return True, "Already in voice chat"
                if "retry joining" in err_lower or "ssrc" in err_lower or "groupcall_ssrc_duplicate" in err_lower:
                    await asyncio.sleep(0.3)
                    continue
                return False, f"Failed to join: {last_err[:40]}"

        return False, f"Failed to join after retries: {last_err[:40]}"

    except Exception as e:
        return False, f"VC Error: {str(e)[:40]}"

# ========== RESOLVE PEER AND MESSAGE ==========
async def resolve_peer_and_msg(client, link):
    """Safely resolve peer and message id for both public and private Telegram links with caching."""
    link = link.strip().replace('https://', '').replace('http://', '')
    if 't.me/c/' in link:
        parts = link.split('t.me/c/')[1].split('/')
        if len(parts) >= 2:
            try:
                channel_id = int(parts[0])
                msg_id = int(parts[1].split('?')[0])
                peer = None
                for candidate in [int(f"-100{channel_id}"), channel_id]:
                    try:
                        peer = await client.get_input_entity(candidate)
                        break
                    except Exception:
                        try:
                            peer = await client.get_entity(candidate)
                            break
                        except Exception:
                            pass
                if not peer:
                    try:
                        async for dialog in client.iter_dialogs(limit=30):
                            if getattr(dialog.entity, 'id', None) == channel_id:
                                peer = await client.get_input_entity(dialog.entity)
                                break
                    except Exception:
                        pass
                if not peer:
                    peer = PeerChannel(channel_id)
                return peer, msg_id
            except Exception:
                return None, None
    elif 't.me/' in link or '/' in link:
        clean = link.replace('t.me/', '').lstrip('@')
        parts = clean.split('/')
        if len(parts) >= 2 and parts[1].split('?')[0].isdigit():
            try:
                username = parts[0]
                msg_id = int(parts[1].split('?')[0])
                try:
                    peer = await client.get_input_entity(username)
                except Exception:
                    peer = await client.get_entity(username)
                return peer, msg_id
            except Exception:
                return None, None
    return None, None

# ========== SEND REACTION ==========
async def send_reaction_func(client, link, emoji):
    phone = getattr(client, '_phone', None)
    try:
        peer, msg_id = await resolve_peer_and_msg(client, link)
        if not peer or not msg_id:
            return False, "Invalid link or entity"

        await client(SendReactionRequest(peer=peer, msg_id=msg_id, reaction=[ReactionEmoji(emoticon=emoji)]))
        return True, f"Reacted with {emoji}"
    except FloodWaitError as e:
        if phone:
            set_account_cooldown(phone, e.seconds)
        return False, f"Flood wait {e.seconds}s"
    except Exception as e:
        err_str = str(e).lower()
        if "flood" in err_str:
            if phone:
                set_account_cooldown(phone, 60)
            return False, "Flood wait"
        if "frozen" in err_str:
            if phone:
                mark_account_frozen(phone)
            return False, "Account Frozen by Telegram"
        return False, str(e)[:40]

# ========== SEND PREMIUM REACTION ==========
async def send_premium_reaction_func(client, link, custom_emoji_id):
    phone = getattr(client, '_phone', None)
    try:
        peer, msg_id = await resolve_peer_and_msg(client, link)
        if not peer or not msg_id:
            return False, "Invalid link or entity"

        await client(SendReactionRequest(peer=peer, msg_id=msg_id, reaction=[ReactionCustomEmoji(document_id=int(custom_emoji_id))]))
        return True, "Reacted with premium emoji"
    except FloodWaitError as e:
        if phone:
            set_account_cooldown(phone, e.seconds)
        return False, f"Flood wait {e.seconds}s"
    except Exception as e:
        err_str = str(e).lower()
        if "flood" in err_str:
            if phone:
                set_account_cooldown(phone, 60)
            return False, "Flood wait"
        if "frozen" in err_str:
            if phone:
                mark_account_frozen(phone)
            return False, "Account Frozen by Telegram"
        return False, str(e)[:40]

# ========== DIFFERENT REACTIONS ==========
async def add_different_reactions(client, link):
    phone = getattr(client, '_phone', None)
    try:
        peer, msg_id = await resolve_peer_and_msg(client, link)
        if not peer or not msg_id:
            return False, "Invalid link or entity"

        random_reaction = random.choice(AVAILABLE_REACTIONS)
        await client(SendReactionRequest(peer=peer, msg_id=msg_id, reaction=[ReactionEmoji(emoticon=random_reaction)]))
        return True, f"Reacted with {random_reaction}"
    except FloodWaitError as e:
        if phone:
            set_account_cooldown(phone, e.seconds)
        return False, f"Flood wait {e.seconds}s"
    except Exception as e:
        err_str = str(e).lower()
        if "flood" in err_str:
            if phone:
                set_account_cooldown(phone, 60)
            return False, "Flood wait"
        if "frozen" in err_str:
            if phone:
                mark_account_frozen(phone)
            return False, "Account Frozen by Telegram"
        return False, str(e)[:40]

async def vote_poll_func(client, link, option_index=0):
    phone = getattr(client, '_phone', None)
    try:
        peer, msg_id = await resolve_peer_and_msg(client, link)
        if not peer or not msg_id:
            return False, "Invalid link or entity"

        msg = None
        try:
            msg = await client.get_messages(peer, ids=msg_id)
        except Exception as e:
            err_str = str(e).lower()
            if "channelprivate" in err_str or "chat_invalid" in err_str or "need to join" in err_str:
                try:
                    await client(JoinChannelRequest(peer))
                    msg = await client.get_messages(peer, ids=msg_id)
                except Exception as je:
                    if "frozen" in str(je).lower():
                        if phone:
                            mark_account_frozen(phone)
                        return False, "Account Frozen by Telegram"
                    return False, f"Channel access error: {str(je)[:30]}"
            else:
                if "frozen" in err_str:
                    if phone:
                        mark_account_frozen(phone)
                    return False, "Account Frozen by Telegram"
                return False, f"Fetch error: {str(e)[:30]}"

        if not msg:
            return False, "Message not found"

        input_peer = getattr(msg, 'input_chat', None) or peer
        opt_idx = int(option_index) if str(option_index).isdigit() else 0

        # 1. Native Telegram poll support
        if getattr(msg, 'poll', None) and getattr(msg.poll, 'poll', None):
            if getattr(msg.poll.poll, 'closed', False):
                return False, "Poll is closed"
            answers = getattr(msg.poll.poll, 'answers', [])
            if answers:
                idx = min(max(0, opt_idx), len(answers) - 1)
                chosen_option = answers[idx].option
                try:
                    await client(SendVoteRequest(peer=input_peer, msg_id=msg_id, options=[chosen_option]))
                    return True, f"Voted in poll (option {idx + 1})"
                except FloodWaitError as e:
                    if phone:
                        set_account_cooldown(phone, e.seconds)
                    return False, f"Flood wait {e.seconds}s"
                except Exception as e:
                    err_str = str(e).lower()
                    if "already" in err_str or "revote" in err_str:
                        return True, f"Voted in poll (option {idx + 1})"
                    if "frozen" in err_str:
                        if phone:
                            mark_account_frozen(phone)
                        return False, "Account Frozen by Telegram"
                    return False, f"Poll error: {str(e)[:30]}"

        # 2. Try Telethon high-level msg.buttons and msg.click() (handles all button layouts)
        if getattr(msg, 'buttons', None):
            try:
                callback_buttons = [btn for row in msg.buttons for btn in row if getattr(btn, 'data', None) is not None]
                target_buttons = callback_buttons if callback_buttons else [btn for row in msg.buttons for btn in row]
                if target_buttons:
                    idx = min(max(0, opt_idx), len(target_buttons) - 1)
                    btn = target_buttons[idx]
                    await btn.click()
                    return True, f"Voted via button {idx + 1}"
            except FloodWaitError as e:
                if phone:
                    set_account_cooldown(phone, e.seconds)
                return False, f"Flood wait {e.seconds}s"
            except Exception as e:
                err_str = str(e).lower()
                if "already" in err_str or "chosen" in err_str:
                    return True, f"Voted via button {opt_idx + 1}"
                if "frozen" in err_str:
                    if phone:
                        mark_account_frozen(phone)
                    return False, "Account Frozen by Telegram"

        # 3. Low-level Inline callback button support
        if msg.reply_markup and hasattr(msg.reply_markup, 'rows'):
            all_buttons = []
            for row in msg.reply_markup.rows:
                for button in getattr(row, 'buttons', []):
                    b_data = getattr(button, 'data', None)
                    if not b_data and hasattr(button, 'type'):
                        b_data = getattr(button.type, 'data', None)
                    if b_data:
                        all_buttons.append((button, b_data))
            if all_buttons:
                idx = min(max(0, opt_idx), len(all_buttons) - 1)
                button_obj, button_data = all_buttons[idx]
                try:
                    await client(GetBotCallbackAnswerRequest(peer=input_peer, msg_id=msg_id, data=button_data))
                    return True, f"Voted via button {idx + 1}"
                except FloodWaitError as e:
                    if phone:
                        set_account_cooldown(phone, e.seconds)
                    return False, f"Flood wait {e.seconds}s"
                except Exception as e:
                    err_str = str(e).lower()
                    if "already" in err_str or "chosen" in err_str:
                        return True, f"Voted via button {idx + 1}"
                    if "frozen" in err_str:
                        if phone:
                            mark_account_frozen(phone)
                        return False, "Account Frozen by Telegram"
                    return False, f"Button error: {str(e)[:30]}"

        return False, "No poll or vote buttons found"
    except FloodWaitError as e:
        if phone:
            set_account_cooldown(phone, e.seconds)
        return False, f"Flood wait {e.seconds}s"
    except Exception as e:
        err_str = str(e).lower()
        if "frozen" in err_str:
            if phone:
                mark_account_frozen(phone)
            return False, "Account Frozen by Telegram"
        return False, str(e)[:40]

# ========== JOIN CHANNEL ==========
async def join_channel_func(client, link):
    phone = getattr(client, '_phone', None)
    try:
        from telethon.errors import UserAlreadyParticipantError, InviteRequestSentError
        link = link.strip().replace('https://', '').replace('http://', '')
        if 't.me/+' in link or 'joinchat' in link:
            if 't.me/+' in link:
                hash_part = link.split('t.me/+')[-1].split('/')[0].split('?')[0]
            else:
                hash_part = link.split('joinchat/')[-1].split('/')[0].split('?')[0]
            try:
                await client(ImportChatInviteRequest(hash_part))
                return True, "Joined via invite"
            except UserAlreadyParticipantError:
                return True, "Already joined"
            except InviteRequestSentError:
                return True, "Join request submitted"
        username = link.replace('t.me/', '').lstrip('@').split('/')[0].split('?')[0]
        await client(JoinChannelRequest(username))
        return True, "Joined channel"
    except UserAlreadyParticipantError:
        return True, "Already joined"
    except FloodWaitError as e:
        if phone:
            set_account_cooldown(phone, e.seconds)
        return False, f"Flood wait {e.seconds}s"
    except Exception as e:
        err_str = str(e).lower()
        if "already participant" in err_str:
            return True, "Already joined"
        if "request has been sent" in err_str:
            return True, "Join request submitted"
        if "flood" in err_str:
            if phone:
                set_account_cooldown(phone, 60)
            return False, "Flood wait"
        if "frozen" in err_str:
            if phone:
                mark_account_frozen(phone)
            return False, "Account Frozen by Telegram"
        return False, str(e)[:50]

# ========== LEAVE SPECIFIC CHANNEL ==========
async def leave_specific_channel_func(client, channel_input):
    try:
        channel_input = channel_input.strip().replace('https://', '').replace('http://', '')

        if 't.me/c/' in channel_input:
            parts = channel_input.split('t.me/c/')[1].split('/')
            channel_id = int(parts[0])
            entity = None
            for candidate in [int(f"-100{channel_id}"), channel_id]:
                try:
                    entity = await client.get_input_entity(candidate)
                    break
                except Exception:
                    try:
                        entity = await client.get_entity(candidate)
                        break
                    except Exception:
                        pass
            if not entity:
                try:
                    async for dialog in client.iter_dialogs(limit=50):
                        if getattr(dialog.entity, 'id', None) == channel_id:
                            entity = await client.get_input_entity(dialog.entity)
                            break
                except Exception:
                    pass
            if not entity:
                entity = PeerChannel(channel_id)
        else:
            channel_input = channel_input.replace('t.me/', '').replace('@', '').split('/')[0]
            entity = await client.get_entity(channel_input)

        await client(LeaveChannelRequest(entity))
        return True, "Left channel"
    except Exception as e:
        return False, str(e)[:50]

# ========== LEAVE ALL CHANNELS ==========
async def leave_all_channels_func(client):
    left_count = 0
    try:
        dialogs = await client.get_dialogs(limit=200)
        for dialog in dialogs:
            if dialog.is_channel or dialog.is_group:
                try:
                    entity = dialog.entity
                    # Safety protections: do not leave channels the account created or administers
                    if getattr(entity, 'creator', False) or getattr(entity, 'admin_rights', None):
                        continue
                    if getattr(entity, 'id', 0) in [777000, 42777]:
                        continue
                    await client(LeaveChannelRequest(entity))
                    left_count += 1
                    await asyncio.sleep(0.3)
                except Exception:
                    pass
        return left_count
    except Exception:
        return left_count

# ========== GROUP SPAM ==========
async def group_spam_message(client, link, message_text):
    try:
        link = link.strip().replace('https://', '').replace('http://', '')
        chat_entity = None

        if 't.me/+' in link or 'joinchat' in link:
            if 't.me/+' in link:
                hash_part = link.split('t.me/+')[-1].split('/')[0].split('?')[0]
            else:
                hash_part = link.split('joinchat/')[-1].split('/')[0].split('?')[0]
            try:
                updates = await client(ImportChatInviteRequest(hash_part))
                if updates.chats:
                    chat_entity = updates.chats[0]
            except UserAlreadyParticipantError:
                try:
                    invited = await client(CheckChatInviteRequest(hash_part))
                    if hasattr(invited, 'chat') and invited.chat:
                        chat_entity = invited.chat
                except Exception:
                    pass
            except Exception:
                pass

        if not chat_entity:
            username = link.replace('t.me/', '').lstrip('@').split('/')[0].split('?')[0]
            chat_entity = await client.get_entity(username)

        if message_text:
            await client.send_message(chat_entity, message_text)
            return True, "Message sent"
        return True, "Joined only"
    except FloodWaitError as e:
        return False, f"Flood wait {e.seconds}s"
    except Exception as e:
        return False, str(e)[:50]

# ========== LEAVE CHANNEL MENU ==========
async def leave_channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🚪 Leave Specific Channel", callback_data="leave_specific_channel")],
        [InlineKeyboardButton("🗑️ Leave ALL Channels", callback_data="leave_all_channels")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "🚪 LEAVE CHANNEL OPTIONS\n\nChoose an option:",
            reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            "🚪 LEAVE CHANNEL OPTIONS\n\nChoose an option:",
            reply_markup=reply_markup)

async def leave_specific_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    WAITING_FOR[user_id] = 'leave_specific_link'

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg_text = """🚪 LEAVE SPECIFIC CHANNEL

Send channel link/username:
• @username
• t.me/username
• t.me/c/channel_id

Example: @technicalguruji"""

    if update.callback_query:
        await update.callback_query.edit_message_text(msg_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg_text, reply_markup=reply_markup)

async def handle_leave_specific(update: Update, context: ContextTypes.DEFAULT_TYPE, link: str):
    user_id = update.effective_user.id
    accs = get_accessible_accounts(user_id)

    if not accs:
        await update.message.reply_text("❌ No accessible accounts!")
        WAITING_FOR.pop(user_id, None)
        return

    WAITING_FOR.pop(user_id, None)

    status_msg = await update.message.reply_text(f"🚪 Leaving channel from {len(accs)} accounts...")
    results = {'left': 0, 'not_member': 0, 'failed': 0}

    for i, acc in enumerate(accs):
        try:
            client = await get_client_for_account(acc)
            if not client:
                results['failed'] += 1
                continue

            success, msg = await leave_specific_channel_func(client, link)
            if success:
                results['left'] += 1
            else:
                if "not member" in msg.lower():
                    results['not_member'] += 1
                else:
                    results['failed'] += 1

        except Exception as e:
            results['failed'] += 1

        if (i + 1) % 5 == 0 or (i + 1) == len(accs):
            await status_msg.edit_text(
                f"🚪 PROGRESS: {i+1}/{len(accs)}\n✅ Left: {results['left']}\n⚠️ Not member: {results['not_member']}\n❌ Failed: {results['failed']}")

        delay = load_settings(user_id).get('delay', DEFAULT_DELAY)
        await asyncio.sleep(delay)

    await status_msg.edit_text(f"✅ LEAVE CHANNEL COMPLETED!\n\n✅ Left: {results['left']}\n⚠️ Not member: {results['not_member']}\n❌ Failed: {results['failed']}")

    leave_sp_camp = {
        'action': 'Leave Specific Channel',
        'target': link,
        'result': f"Left {results['left']} / Not member {results['not_member']} / Failed {results['failed']}",
        'status': 'completed',
        'timestamp': str(datetime.now()),
        'accounts_used': len(accs),
        'success_count': results['left'],
        'failed_count': results['failed']
    }
    save_campaign(user_id, leave_sp_camp)
    await log_campaign_to_admin_channel(
        user_id=user_id,
        action='Leave Specific Channel',
        target=link,
        accounts_used=len(accs),
        success_count=results['left'],
        failed_count=results['failed'],
        extra_info=f"Not member: {results['not_member']}",
        bot=context.bot
    )

async def leave_all_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    accs = get_accessible_accounts(user_id)

    if not accs:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ No accessible accounts!")
        else:
            await update.message.reply_text("❌ No accessible accounts!")
        return

    keyboard = [
        [InlineKeyboardButton("⚠️ YES, LEAVE ALL", callback_data="confirm_leave_all")],
        [InlineKeyboardButton("❌ Cancel", callback_data="main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"⚠️ LEAVE ALL CHANNELS\n\n📊 Accounts: {len(accs)}\n⚠️ This will leave ALL channels/groups!\n\nContinue?",
            reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            f"⚠️ LEAVE ALL CHANNELS\n\n📊 Accounts: {len(accs)}\n⚠️ This will leave ALL channels/groups!\n\nContinue?",
            reply_markup=reply_markup)

async def confirm_leave_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    accs = get_accessible_accounts(user_id)

    status_msg = await query.edit_message_text(f"⏳ Leaving channels from {len(accs)} accounts...")

    results = {'accounts_done': 0, 'total_left': 0, 'failed': 0}

    for i, acc in enumerate(accs):
        try:
            client = await get_client_for_account(acc)
            if not client:
                results['failed'] += 1
                continue

            left = await leave_all_channels_func(client)
            results['accounts_done'] += 1
            results['total_left'] += left

        except Exception as e:
            results['failed'] += 1

        if (i + 1) % 3 == 0 or (i + 1) == len(accs):
            await status_msg.edit_text(f"⏳ PROGRESS: {i+1}/{len(accs)}\n✅ Accounts done: {results['accounts_done']}\n📤 Total left: {results['total_left']}\n❌ Failed: {results['failed']}")

        delay = load_settings(user_id).get('delay', DEFAULT_DELAY)
        await asyncio.sleep(delay)

    await status_msg.edit_text(f"✅ LEAVE ALL COMPLETED!\n\n✅ Accounts processed: {results['accounts_done']}\n📤 Total channels left: {results['total_left']}\n❌ Failed: {results['failed']}")

    leave_all_camp = {
        'action': 'Leave All Channels',
        'target': 'All Dialogs',
        'result': f"Processed {results['accounts_done']} accounts / Left {results['total_left']} channels / Failed {results['failed']}",
        'status': 'completed',
        'timestamp': str(datetime.now()),
        'accounts_used': len(accs),
        'success_count': results['total_left'],
        'failed_count': results['failed']
    }
    save_campaign(user_id, leave_all_camp)
    await log_campaign_to_admin_channel(
        user_id=user_id,
        action='Leave All Channels',
        target='All Account Dialogs',
        accounts_used=len(accs),
        success_count=results['total_left'],
        failed_count=results['failed'],
        extra_info=f"Accounts processed: {results['accounts_done']}",
        bot=query.message.get_bot() if hasattr(query, 'message') and query.message else None
    )

# ========== SCHEDULED CHECKER ==========
async def check_scheduled_campaigns():
    while True:
        try:
            schedules = get_pending_schedules()
            for schedule in schedules:
                schedule_id, user_id, action, target, scheduled_time, account_count, spam_message = schedule
                accounts = get_accessible_accounts(user_id)
                live_accounts = await get_live_accounts_batch(accounts)
                if live_accounts:
                    accounts_to_use = live_accounts[:account_count]
                    await run_scheduled_campaign(user_id, action, target, accounts_to_use, spam_message)
                    update_scheduled_status(schedule_id, 'completed')
                else:
                    logging.warning(f"Scheduled task {schedule_id} could not run: No live accounts available.")
                    update_scheduled_status(schedule_id, 'failed_no_accounts')
            await asyncio.sleep(30)
        except Exception as e:
            logging.error(f"Error in check_scheduled_campaigns: {e}")
            await asyncio.sleep(30)

async def run_scheduled_campaign(user_id, action, target, accounts_to_use, spam_message):
    results = {'success': 0, 'failed': 0}
    # Prioritize accounts not on cooldown
    non_cooldown = [a for a in accounts_to_use if not is_account_on_cooldown(a.get('phone'))]
    cooldown_accs = [a for a in accounts_to_use if is_account_on_cooldown(a.get('phone'))]
    sorted_accs = non_cooldown + cooldown_accs

    for acc in sorted_accs:
        phone = acc.get('phone')
        if is_account_on_cooldown(phone):
            results['failed'] += 1
            continue

        try:
            client = await get_client_for_account(acc)
            if not client:
                results['failed'] += 1
                continue

            if action == 'join':
                success, msg = await join_channel_func(client, target)
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            elif action == 'react':
                react_emoji = spam_message if spam_message else '🔥'
                success, msg = await send_reaction_func(client, target, react_emoji)
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            elif action == 'different_react':
                success, msg = await add_different_reactions(client, target)
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            elif action == 'view':
                try:
                    peer, msg_id = await resolve_peer_and_msg(client, target)
                    if peer and msg_id:
                        await client(GetMessagesViewsRequest(
                            peer=peer,
                            id=[msg_id],
                            increment=True
                        ))
                        results['success'] += 1
                    else:
                        results['failed'] += 1
                except Exception:
                    results['failed'] += 1
            elif action == 'vote':
                opt_idx = int(spam_message) if spam_message and str(spam_message).strip().isdigit() else 0
                success, msg = await vote_poll_func(client, target, option_index=opt_idx)
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            elif action == 'vc':
                success, msg = await join_voice_chat_func(client, target)
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            elif action == 'group_spam':
                success, msg = await group_spam_message(client, target, spam_message)
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
            elif action == 'dm':
                msg_to_send = spam_message if spam_message else "Hello!"
                if target.isdigit():
                    entity = await client.get_entity(int(target))
                else:
                    entity = await client.get_entity(target)
                await client.send_message(entity, msg_to_send)
                results['success'] += 1
        except FloodWaitError as e:
            if phone:
                set_account_cooldown(phone, e.seconds)
            results['failed'] += 1
        except Exception as e:
            results['failed'] += 1
        delay = load_settings(user_id).get('delay', DEFAULT_DELAY)
        await asyncio.sleep(delay + random.uniform(0.05, 0.15))

    campaign_data = {
        'action': action,
        'target': target,
        'result': f"Success {results['success']} / Failed {results['failed']}",
        'status': 'completed',
        'timestamp': str(datetime.now()),
        'accounts_used': len(accounts_to_use),
        'success_count': results['success'],
        'failed_count': results['failed']
    }
    save_campaign(user_id, campaign_data)
    await log_campaign_to_admin_channel(
        user_id=user_id,
        action=f"⏰ Scheduled: {action}",
        target=target,
        accounts_used=len(accounts_to_use),
        success_count=results['success'],
        failed_count=results['failed'],
        extra_info=f"Spam Message: {spam_message[:50]}..." if spam_message else None,
        bot=GLOBAL_BOT
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    if not error:
        return
    error_str = str(error)
    if "terminated by other getUpdates request" in error_str or "Conflict" in type(error).__name__:
        logging.warning("⚠️ Conflict detected (another instance polled). Terminating for clean auto-restart...")
        os._exit(1)
    harmless = ["Message is not modified", "Query is too old", "query id is invalid", "GeneratorExit", "Task was destroyed", "coroutine ignored"]
    for h in harmless:
        if h in error_str:
            return
    logging.error(f"Bot runtime error: {error}", exc_info=context.error)
    if update and update.callback_query:
        try:
            await update.callback_query.answer("⚠️ An error occurred. Please try again.", show_alert=True)
        except Exception:
            pass

# ========== BOT RUNTIME STATE ==========
PENDING_OTP = {}
PENDING_2FA = {}
WAITING_FOR = {}
PENDING_CAMPAIGN = {}
SELECTED_EMOJIS = {}
SELECTED_PREMIUM = {}
SELECTED_ACCOUNT_COUNT = {}
ACCESS_DATA = {}
PENDING_SPAM_MSG = {}
PENDING_SCHEDULE = {}

# ========== DATABASE EXPORT / IMPORT (MONGODB) ==========
async def cmd_export_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin can export DB!")
        return

    if MONGO_DB is None:
        await update.message.reply_text("❌ MongoDB is not connected!")
        return

    try:
        status = await update.message.reply_text("📦 Preparing MongoDB database export...")
        import tempfile, json

        users = []
        for doc in MONGO_DB.users.find():
            d = dict(doc)
            d.pop("_id", None)
            users.append(d)

        campaigns = []
        for doc in MONGO_DB.campaigns.find():
            d = dict(doc)
            d.pop("_id", None)
            campaigns.append(d)

        scheduled = []
        for doc in MONGO_DB.scheduled.find():
            d = dict(doc)
            d.pop("_id", None)
            scheduled.append(d)

        bot_settings = {}
        for doc in MONGO_DB.bot_settings.find():
            bot_settings[doc.get("key", "")] = doc.get("value")

        data = {
            "source": "MongoDB",
            "database": MONGO_DB_NAME,
            "export_date": datetime.now().isoformat(),
            "users": users,
            "campaigns": campaigns,
            "scheduled": scheduled,
            "bot_settings": bot_settings
        }
        tmp_path = os.path.join(tempfile.gettempdir(), 'automation_bot_export.json')
        with open(tmp_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        with open(tmp_path, 'rb') as f:
            target_chat_id = update.effective_chat.id if getattr(update, 'effective_chat', None) else (update.message.chat_id if getattr(update, 'message', None) else update.effective_user.id)
            await context.bot.send_document(
                chat_id=target_chat_id,
                document=f,
                filename='automation_bot_export.json',
                caption=(
                    f"🍃 MONGODB DATABASE EXPORT\n\n"
                    f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"👥 Users: {len(users)}\n"
                    f"📊 Campaigns: {len(campaigns)}\n"
                    f"⏰ Scheduled: {len(scheduled)}\n"
                    f"📦 File: automation_bot_export.json\n\n"
                    "To restore: use /import_db and send this file."
                )
            )
        await status.edit_text("✅ MongoDB database exported successfully!")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception as e:
        await status.edit_text(f"❌ Export failed: {str(e)[:100]}")

async def cmd_import_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin can import DB!")
        return

    if MONGO_DB is None:
        await update.message.reply_text("❌ MongoDB is not connected!")
        return

    WAITING_FOR[user_id] = "import_db_file"
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📥 IMPORT DATABASE (MongoDB)\n\n"
        "⚠️ WARNING: This will REPLACE all MongoDB records with the backup file!\n\n"
        "Send the automation_bot_export.json file now:\n"
        "(Use /export_db first to back up current data)",
        reply_markup=reply_markup
    )

# ========== SESSIONS EXPORT & IMPORT WITH OWNERSHIP (MONGODB) ==========

def string_session_to_sqlite_file(session_string: str, output_filepath_no_ext: str) -> str:
    """Generates a genuine Telethon SQLite .session file from a Telethon StringSession."""
    str_sess = StringSession(session_string)
    sql_sess = SQLiteSession(output_filepath_no_ext)
    sql_sess.set_dc(str_sess.dc_id, str_sess.server_address, str_sess.port)
    sql_sess.auth_key = str_sess.auth_key
    sql_sess.save()
    sql_sess.close()
    return f"{output_filepath_no_ext}.session"

def extract_session_string(data_or_path, filename: str = "") -> tuple:
    """
    Universally extracts (telethon_session_string, detected_type) from:
    1. Telethon SQLite .session
    2. Pyrogram / Hydrogram / Kurigram SQLite .session
    3. Telethon StringSession (text)
    4. Pyrogram StringSession v1 or v2 (text)
    Returns (telethon_session_string, detected_type) or (None, None).
    """
    if isinstance(data_or_path, (bytes, bytearray)):
        raw_bytes = bytes(data_or_path)
    elif isinstance(data_or_path, str) and os.path.exists(data_or_path):
        try:
            with open(data_or_path, 'rb') as f:
                raw_bytes = f.read()
        except Exception:
            return None, None
    elif isinstance(data_or_path, str):
        v = ensure_telethon_session_string(data_or_path)
        return (v, "string_session") if v else (None, None)
    else:
        return None, None

    if not raw_bytes or len(raw_bytes) < 10:
        return None, None

    # Check 1: Is it an SQLite database?
    if raw_bytes.startswith(b'SQLite format 3\x00'):
        temp_file = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.session') as f:
                f.write(raw_bytes)
                temp_file = f.name

            conn = sqlite3.connect(temp_file)
            cur = conn.cursor()

            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
            if cur.fetchone():
                cur.execute("PRAGMA table_info(sessions)")
                cols = [c[1] for c in cur.fetchall()]
                if 'auth_key' in cols:
                    has_server = 'server_address' in cols
                    has_port = 'port' in cols
                    query = 'SELECT dc_id, auth_key'
                    if has_server: query += ', server_address'
                    if has_port: query += ', port'
                    query += ' FROM sessions LIMIT 1'

                    cur.execute(query)
                    row = cur.fetchone()
                    if row:
                        raw_dc = row[0]
                        auth_key = bytes(row[1]) if row[1] is not None else b''
                        server_address = None
                        port = 443
                        idx = 2
                        if has_server:
                            server_address = row[idx]
                            idx += 1
                        if has_port:
                            port = row[idx]

                        if auth_key and len(auth_key) == 256:
                            try:
                                dc_id = int(raw_dc) if (raw_dc and 1 <= int(raw_dc) <= 5) else 2
                            except Exception:
                                dc_id = 2
                            try:
                                port = int(port) if port else 443
                                if not (1 <= port <= 65535):
                                    port = 443
                            except Exception:
                                port = 443
                            try:
                                if not server_address or not str(server_address).replace('.', '').isdigit():
                                    server_address = TELETHON_DC_IPS.get(dc_id, '149.154.167.51')
                                ip_bytes = ipaddress.IPv4Address(server_address).packed
                            except Exception:
                                ip_bytes = ipaddress.IPv4Address(TELETHON_DC_IPS.get(dc_id, '149.154.167.51')).packed
                            packed = struct.pack('>B4sH256s', dc_id, ip_bytes, port, auth_key)
                            telethon_str = '1' + base64.urlsafe_b64encode(packed).decode('ascii')

                            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='peers'")
                            is_pyro = bool(cur.fetchone())
                            conn.close()
                            return telethon_str, ("pyrogram_session" if is_pyro else "telethon_session")
            conn.close()
        except Exception as e:
            logging.error(f"extract_session_string sqlite error: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try: os.remove(temp_file)
                except Exception: pass

    # Check 2: Try JSON session format
    try:
        text_content = raw_bytes.decode('utf-8', errors='ignore').strip()
        if text_content.startswith('{') and text_content.endswith('}'):
            j_str = parse_json_to_session_string(text_content)
            if j_str:
                val = ensure_telethon_session_string(j_str)
                if val:
                    return val, "json_session"
        # Check 3: Check hex key or lines of string sessions
        lines = [l.strip() for l in text_content.splitlines() if len(l.strip()) > 20]
        for line in lines:
            hex_val = parse_hex_key_to_session_string(line)
            if hex_val:
                return hex_val, "hex_key"
            val = ensure_telethon_session_string(line)
            if val:
                return val, "string_session"
    except Exception:
        pass

    return None, None

def telethon_sqlite_to_string_session(session_filepath: str) -> str:
    """Extracts a Telethon StringSession universally from an SQLite .session file (Telethon or Pyrogram) offline."""
    sess_str, _ = extract_session_string(session_filepath)
    if sess_str:
        return sess_str
    basepath = session_filepath[:-8] if session_filepath.endswith('.session') else session_filepath
    try:
        sql = SQLiteSession(basepath)
        try:
            if sql.auth_key and sql.dc_id and sql.server_address:
                str_sess = StringSession()
                str_sess.set_dc(sql.dc_id, sql.server_address, sql.port)
                str_sess.auth_key = sql.auth_key
                return str_sess.save()
        finally:
            sql.close()
    except Exception:
        pass
    return None

def ensure_telethon_session_string(session_str: str) -> str:
    """Validates and ensures session string is in Telethon format (converting from Pyrogram, JSON, or Hex Key if needed)."""
    if not session_str or not isinstance(session_str, str):
        return None
    session_str = session_str.strip()
    try:
        s = StringSession(session_str)
        if s.auth_key:
            return session_str
    except Exception:
        pass
    if session_str.startswith('{') and session_str.endswith('}'):
        json_converted = parse_json_to_session_string(session_str)
        if json_converted:
            try:
                s = StringSession(json_converted)
                if s.auth_key:
                    return json_converted
            except Exception:
                pass
    hex_converted = parse_hex_key_to_session_string(session_str)
    if hex_converted:
        try:
            s = StringSession(hex_converted)
            if s.auth_key:
                return hex_converted
        except Exception:
            pass
    converted = pyrogram_to_telethon_session(session_str)
    if converted:
        try:
            s = StringSession(converted)
            if s.auth_key:
                return converted
        except Exception:
            pass
    return None

def create_sessions_export_archive():
    """
    Fetches all accounts across all users from MongoDB,
    generates genuine Telethon SQLite .session files from their session strings,
    creates accounts_ownership.json mapping each file to its owner,
    and returns (zip_filepath, total_accounts, total_owners, temp_dir).
    """
    if MONGO_DB is None:
        raise RuntimeError("MongoDB is not connected")

    temp_dir = tempfile.mkdtemp(prefix="tg_export_")
    sessions_folder = os.path.join(temp_dir, "sessions")
    os.makedirs(sessions_folder, exist_ok=True)

    accounts_manifest = []
    total_accounts = 0
    owners_seen = set()
    used_filenames = set()

    for user_doc in MONGO_DB.users.find():
        owner_id = user_doc.get("user_id")
        owner_username = user_doc.get("username", "")
        owner_first_name = user_doc.get("first_name", "")
        accounts = user_doc.get("accounts", [])

        if not accounts:
            continue

        for acc in accounts:
            sess_str = acc.get("session_string")
            if not sess_str:
                sess_path = acc.get("session")
                if sess_path:
                    if os.path.exists(f"{sess_path}.session"):
                        sess_str = telethon_sqlite_to_string_session(f"{sess_path}.session")
                    elif os.path.exists(f"{sess_path}.session_string"):
                        try:
                            with open(f"{sess_path}.session_string", "r") as f:
                                sess_str = f.read().strip()
                        except Exception:
                            pass

            valid_str = ensure_telethon_session_string(sess_str)
            if not valid_str:
                continue

            phone = str(acc.get("phone") or f"user_{acc.get('user_id', total_accounts + 1)}")
            clean_phone = "".join(c for c in phone if c.isalnum() or c in "+_-")
            if not clean_phone:
                clean_phone = f"account_{total_accounts + 1}"

            candidate_base = clean_phone
            idx = 1
            while candidate_base in used_filenames:
                candidate_base = f"{clean_phone}_{idx}"
                idx += 1
            used_filenames.add(candidate_base)

            session_file_name = f"{candidate_base}.session"
            session_out_base = os.path.join(sessions_folder, candidate_base)

            # Generate real SQLite .session file directly from mongo session string
            string_session_to_sqlite_file(valid_str, session_out_base)

            # Also save .session_string token
            with open(f"{session_out_base}.session_string", "w") as f:
                f.write(valid_str)

            accounts_manifest.append({
                "session_file": session_file_name,
                "string_file": f"{candidate_base}.session_string",
                "owner_user_id": owner_id,
                "owner_username": owner_username,
                "owner_first_name": owner_first_name,
                "phone": acc.get("phone", phone),
                "account_user_id": acc.get("user_id"),
                "account_username": acc.get("username", ""),
                "first_name": acc.get("first_name", ""),
                "added_date": acc.get("added_date", ""),
                "type": acc.get("type", "session_file"),
                "session_string": valid_str
            })

            total_accounts += 1
            owners_seen.add(owner_id)

    if total_accounts == 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None, 0, 0, None

    manifest_data = {
        "version": 1,
        "app": "Telegram Voting Automation Bot",
        "export_date": datetime.now().isoformat(),
        "total_accounts": total_accounts,
        "total_owners": len(owners_seen),
        "accounts": accounts_manifest
    }
    manifest_path = os.path.join(temp_dir, "accounts_ownership.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    readme_path = os.path.join(temp_dir, "README.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(
            f"=======================================================\n"
            f"TELEGRAM SESSIONS & OWNERSHIP EXPORT\n"
            f"=======================================================\n"
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Total Accounts: {total_accounts}\n"
            f"Total Account Owners: {len(owners_seen)}\n\n"
            f"ARCHIVE CONTENTS:\n"
            f"1. *.session: Genuine SQLite Telethon session files generated\n"
            f"   directly from MongoDB session strings.\n"
            f"2. *.session_string: Telethon StringSession tokens.\n"
            f"3. accounts_ownership.json: Ownership manifest mapping each\n"
            f"   session file to the specific user who added it.\n\n"
            f"HOW TO IMPORT / RESTORE:\n"
            f"1. Open Admin Panel -> Click '📥 Import Sessions (.zip)'\n"
            f"   (or send /import_sessions in chat)\n"
            f"2. Upload this ZIP archive.\n"
            f"3. The bot will automatically unpack the sessions and restore\n"
            f"   each account to its original owner in MongoDB!\n"
            f"=======================================================\n"
        )

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(temp_dir, f"telegram_sessions_export_{timestamp_str}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(manifest_path, "accounts_ownership.json")
        zipf.write(readme_path, "README.txt")
        for item in os.listdir(sessions_folder):
            item_path = os.path.join(sessions_folder, item)
            if os.path.isfile(item_path):
                zipf.write(item_path, f"sessions/{item}")
                zipf.write(item_path, item)

    return zip_path, total_accounts, len(owners_seen), temp_dir

async def do_export_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executes the export of all account session files generated from MongoDB."""
    if update.callback_query:
        user_id = update.callback_query.from_user.id
        chat_id = update.callback_query.message.chat_id
    else:
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id if getattr(update, 'effective_chat', None) else (update.message.chat_id if getattr(update, 'message', None) else user_id)

    if not is_owner(user_id) and not is_admin_user(user_id):
        msg = "❌ Only Owner/Admin can export sessions!"
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg)
        return

    if MONGO_DB is None:
        msg = "❌ MongoDB is not connected!"
        if update.callback_query:
            await update.callback_query.answer(msg, show_alert=True)
        else:
            await update.message.reply_text(msg)
        return

    status = await context.bot.send_message(
        chat_id=chat_id,
        text="📦 Generating genuine .session files from MongoDB session strings across all users..."
    )

    temp_dir = None
    try:
        zip_path, total_accs, total_owners, temp_dir = create_sessions_export_archive()
        if not zip_path or total_accs == 0:
            await status.edit_text("⚠️ No accounts with valid sessions found in MongoDB database!")
            return

        zip_filename = os.path.basename(zip_path)
        with open(zip_path, "rb") as f:
            await context.bot.send_document(
                chat_id=chat_id,
                document=f,
                filename=zip_filename,
                caption=(
                    f"📦 TELEGRAM SESSIONS EXPORT (.ZIP)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"📱 Total Accounts: {total_accs}\n"
                    f"👥 Account Owners: {total_owners} user(s)\n"
                    f"📁 Format: Telethon SQLite .session files\n"
                    f"🏷️ Ownership: accounts_ownership.json included\n\n"
                    f"✨ Each account's .session file was generated directly from its MongoDB session string.\n"
                    f"To restore with ownership: click '📥 Import Sessions (.zip)' in Admin Panel or use /import_sessions."
                )
            )
        await status.edit_text("✅ All account session files generated from MongoDB and exported successfully!")
    except Exception as e:
        await status.edit_text(f"❌ Export failed: {str(e)[:150]}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

async def cmd_export_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /export_sessions for Owner."""
    await do_export_sessions(update, context)

async def cmd_import_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /import_sessions for Owner."""
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin can import sessions!")
        return

    if MONGO_DB is None:
        await update.message.reply_text("❌ MongoDB is not connected!")
        return

    WAITING_FOR[user_id] = "import_sessions_zip"
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📥 IMPORT SESSIONS (.ZIP)\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "Upload the sessions ZIP file (generated via Export Sessions or any .session ZIP).\n\n"
        "✨ Ownership Preservation:\n"
        "• If accounts_ownership.json is inside, every account will be restored to its original owner.\n"
        "• If no ownership manifest is found, accounts are added to your account.\n\n"
        "Send the .zip file now:",
        reply_markup=reply_markup
    )

async def process_import_sessions_zip(update: Update, context: ContextTypes.DEFAULT_TYPE, doc):
    """
    Imports a ZIP archive containing exported sessions and ownership manifest,
    restoring each account back to its original owner in MongoDB.
    """
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin can import sessions!")
        WAITING_FOR.pop(user_id, None)
        return

    if MONGO_DB is None:
        await update.message.reply_text("❌ MongoDB is not connected!")
        WAITING_FOR.pop(user_id, None)
        return

    status = await update.message.reply_text("⏳ Downloading & inspecting sessions ZIP archive...")
    temp_dir = tempfile.mkdtemp(prefix="tg_import_")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        zip_path = os.path.join(temp_dir, "sessions_import.zip")
        await tg_file.download_to_drive(zip_path)

        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(temp_dir)
        except Exception as e:
            await status.edit_text(f"❌ Failed to extract ZIP archive: {str(e)[:100]}")
            return

        manifest_file = None
        for root, dirs, files in os.walk(temp_dir):
            for f in files:
                if f.lower() in ["accounts_ownership.json", "manifest.json", "accounts.json"]:
                    manifest_file = os.path.join(root, f)
                    break
            if manifest_file:
                break

        os.makedirs("sessions", exist_ok=True)

        if manifest_file:
            await status.edit_text("🔍 Ownership manifest found! Restoring accounts to original owners...")
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
            except Exception as e:
                await status.edit_text(f"❌ Failed to parse manifest JSON: {str(e)[:100]}")
                return

            accounts_list = manifest_data.get("accounts", [])
            if not accounts_list:
                await status.edit_text("⚠️ Manifest found but contains no account entries!")
                return

            restored = 0
            updated = 0
            errors = 0
            owners_cache = {}

            for acc_entry in accounts_list:
                owner_uid = acc_entry.get("owner_user_id") or user_id
                try:
                    owner_uid = int(owner_uid)
                except Exception:
                    owner_uid = user_id

                create_user_if_not_exists(
                    owner_uid,
                    username=acc_entry.get("owner_username", ""),
                    first_name=acc_entry.get("owner_first_name", "")
                )

                if owner_uid not in owners_cache:
                    owners_cache[owner_uid] = load_accounts(owner_uid)

                cur_accs = owners_cache[owner_uid]

                sess_str = acc_entry.get("session_string")
                if not sess_str:
                    sess_file_name = acc_entry.get("session_file")
                    if sess_file_name:
                        found_path = None
                        for root, _, files in os.walk(temp_dir):
                            if sess_file_name in files:
                                found_path = os.path.join(root, sess_file_name)
                                break
                        if found_path:
                            sess_str = telethon_sqlite_to_string_session(found_path)

                valid_str = ensure_telethon_session_string(sess_str)
                if not valid_str:
                    errors += 1
                    continue

                phone = str(acc_entry.get("phone") or "")
                tg_id = acc_entry.get("account_user_id") or acc_entry.get("user_id")

                session_path = f"cloud_{owner_uid}_{valid_str[:12]}"
                new_acc_doc = {
                    'phone': phone or f"user_{tg_id or owner_uid}",
                    'session': session_path,
                    'session_string': valid_str,
                    'username': acc_entry.get("account_username") or acc_entry.get("username") or 'No username',
                    'user_id': tg_id,
                    'first_name': acc_entry.get("first_name", ""),
                    'added_date': acc_entry.get("added_date") or str(datetime.now()),
                    'type': acc_entry.get("type", "session_file")
                }

                exists_idx = None
                for idx, a in enumerate(cur_accs):
                    if (phone and a.get("phone") == phone) or (tg_id and a.get("user_id") == tg_id):
                        exists_idx = idx
                        break

                if exists_idx is not None:
                    cur_accs[exists_idx].update(new_acc_doc)
                    updated += 1
                else:
                    cur_accs.append(new_acc_doc)
                    restored += 1

            for o_uid, acc_list in owners_cache.items():
                save_accounts(o_uid, acc_list)

            await status.edit_text(
                f"✅ SESSIONS IMPORT COMPLETED (WITH OWNERSHIP)!\n\n"
                f"📦 Total in manifest: {len(accounts_list)}\n"
                f"📥 New Accounts Restored: {restored}\n"
                f"♻️ Existing Accounts Refreshed: {updated}\n"
                f"👥 Distinct Owners Restored: {len(owners_cache)}\n"
                f"❌ Failed: {errors}\n\n"
                f"💾 All sessions generated & saved to MongoDB."
            )
        else:
            await status.edit_text("ℹ️ No accounts_ownership.json found. Importing all sessions to Owner...")
            session_files = []
            for root, dirs, files in os.walk(temp_dir):
                for f in files:
                    if f.lower().endswith(".session") or f.lower().endswith(".session_string") or f.lower().endswith(".json") or f.lower().endswith(".txt"):
                        session_files.append(os.path.join(root, f))

            if not session_files:
                await status.edit_text("❌ No session files (.session, .json, .txt) found in ZIP archive!")
                return

            restored = 0
            updated = 0
            errors = 0
            owner_accs = load_accounts(user_id)

            for s_file in session_files:
                valid_str = None
                if s_file.lower().endswith(".session"):
                    valid_str = telethon_sqlite_to_string_session(s_file)
                else:
                    try:
                        with open(s_file, "rb") as f:
                            raw = f.read()
                        valid_str, _ = extract_session_string(raw, os.path.basename(s_file))
                    except Exception:
                        pass

                if not valid_str:
                    errors += 1
                    continue

                session_path = f"cloud_{user_id}_{valid_str[:12]}"
                bname = os.path.splitext(os.path.basename(s_file))[0]
                acc_doc = {
                    'phone': bname,
                    'session': session_path,
                    'session_string': valid_str,
                    'username': 'Imported',
                    'user_id': None,
                    'first_name': bname,
                    'added_date': str(datetime.now()),
                    'type': 'imported_session'
                }

                exists_idx = None
                for idx, a in enumerate(owner_accs):
                    if a.get("phone") == bname or a.get("session_string") == valid_str:
                        exists_idx = idx
                        break

                if exists_idx is not None:
                    owner_accs[exists_idx].update(acc_doc)
                    updated += 1
                else:
                    owner_accs.append(acc_doc)
                    restored += 1

            save_accounts(user_id, owner_accs)
            await status.edit_text(
                f"✅ SESSIONS IMPORT COMPLETED (OWNER)!\n\n"
                f"📦 Total files: {len(session_files)}\n"
                f"📥 New Accounts Added: {restored}\n"
                f"♻️ Existing Accounts Refreshed: {updated}\n"
                f"❌ Failed: {errors}\n\n"
                f"💾 All accounts added to Owner and stored in MongoDB."
            )

    except Exception as e:
        await status.edit_text(f"❌ Session import failed: {str(e)[:200]}")
    finally:
        WAITING_FOR.pop(user_id, None)
        shutil.rmtree(temp_dir, ignore_errors=True)

# ========== SESSION & ZIP FILE PROCESSING ==========
async def process_single_session_file(update: Update, context: ContextTypes.DEFAULT_TYPE, doc):
    """Processes an individual uploaded .session file, .session_string, or text file."""
    user_id = update.effective_user.id
    has_acc, _ = has_access(user_id)
    if not has_acc:
        await update.message.reply_text("❌ You don't have access to add accounts!")
        WAITING_FOR.pop(user_id, None)
        return

    os.makedirs("sessions", exist_ok=True)
    status = await update.message.reply_text("⏳ Downloading & verifying session file...")

    try:
        tg_file = None
        file_bytes = None
        for attempt in range(2):
            try:
                tg_file = await context.bot.get_file(doc.file_id, read_timeout=60, write_timeout=60, connect_timeout=30)
                file_bytes = await tg_file.download_as_bytearray(read_timeout=120, write_timeout=60, connect_timeout=30)
                break
            except Exception as dl_err:
                if attempt == 1:
                    raise dl_err
                await asyncio.sleep(1)

        if len(file_bytes) == 0:
            await status.edit_text("❌ The uploaded file is empty!")
            WAITING_FOR.pop(user_id, None)
            return

        file_name = doc.file_name or "session.session"
        session_str, session_type = extract_session_string(file_bytes, file_name)

        if not session_str:
            await status.edit_text(
                "❌ Could not recognize a valid Telegram session in this file.\n\n"
                "Supported formats:\n"
                "• Telethon `.session` files\n"
                "• Pyrogram `.session` files\n"
                "• Telethon or Pyrogram string sessions (.txt / .session_string)"
            )
            WAITING_FOR.pop(user_id, None)
            return

        # Connect and verify authorization with Telethon StringSession
        client = create_telegram_client(StringSession(session_str))
        try:
            await asyncio.wait_for(client.connect(), timeout=15)
            if not await asyncio.wait_for(client.is_user_authorized(), timeout=10):
                await client.disconnect()
                await status.edit_text("❌ Session is expired, revoked, or unauthorized on Telegram.")
                WAITING_FOR.pop(user_id, None)
                return

            me = await asyncio.wait_for(client.get_me(), timeout=10)
            phone = me.phone if me.phone else f"user_{me.id}"

            accounts = load_accounts(user_id)
            existing_idx = None
            for idx, a in enumerate(accounts):
                if (phone and a.get('phone') == phone) or (me.id and a.get('user_id') == me.id) or (a.get('session_string') == session_str):
                    existing_idx = idx
                    break

            session_path = f"cloud_{user_id}_{phone}"
            account = {
                'phone': phone,
                'session': session_path,
                'session_string': session_str,
                'username': me.username or 'No username',
                'user_id': me.id,
                'first_name': me.first_name or '',
                'added_date': str(datetime.now()),
                'type': session_type or 'session_file'
            }

            type_label = (session_type or 'session').replace('_', ' ').title()

            clean_p = str(phone).strip().lstrip('+')
            now_t = time.time()
            ACTIVE_CLIENTS[clean_p] = client
            if phone:
                ACTIVE_CLIENTS[str(phone).strip()] = client
            LIVE_CACHE[clean_p] = (True, now_t, True)
            if phone:
                LIVE_CACHE[str(phone).strip()] = (True, now_t, True)

            if existing_idx is not None:
                accounts[existing_idx].update(account)
                save_accounts(user_id, accounts)
                WAITING_FOR.pop(user_id, None)
                await log_account_addition_to_admin_channel(user_id, account, is_refresh=True, bot=context.bot)
                await status.edit_text(
                    f"♻️ Account Refreshed Successfully!\n\n"
                    f"👤 Name: {me.first_name or 'N/A'}\n"
                    f"🏷️ Username: @{me.username or 'None'}\n"
                    f"📱 Phone: {phone}\n"
                    f"🆔 Telegram ID: {me.id}\n"
                    f"📦 Format: {type_label}\n\n"
                    f"💾 Session updated in MongoDB & local storage."
                )
                return

            accounts.append(account)
            save_accounts(user_id, accounts)

            WAITING_FOR.pop(user_id, None)
            await log_account_addition_to_admin_channel(user_id, account, is_refresh=False, bot=context.bot)
            await status.edit_text(
                f"✅ Account Added Successfully!\n\n"
                f"👤 Name: {me.first_name or 'N/A'}\n"
                f"🏷️ Username: @{me.username or 'None'}\n"
                f"📱 Phone: {phone}\n"
                f"🆔 Telegram ID: {me.id}\n"
                f"📦 Format: {type_label}\n\n"
                f"💾 Stored in MongoDB & session storage."
            )
            return
        except asyncio.TimeoutError:
            try:
                await client.disconnect()
            except Exception:
                pass
            await status.edit_text("❌ Connection timed out while contacting Telegram DC.")
            WAITING_FOR.pop(user_id, None)
            return
        except Exception as e:
            try:
                await client.disconnect()
            except Exception:
                pass
            await status.edit_text(f"❌ Session authorization failed: {str(e)[:150]}")
            WAITING_FOR.pop(user_id, None)
            return
    except Exception as e:
        WAITING_FOR.pop(user_id, None)
        await status.edit_text(f"❌ Processing failed: {str(e)[:150]}")

async def process_zip_upload(update: Update, context: ContextTypes.DEFAULT_TYPE, doc):
    """Processes a ZIP archive containing single or multiple session files or strings."""
    user_id = update.effective_user.id
    has_acc, _ = has_access(user_id)
    if not has_acc:
        await update.message.reply_text("❌ You don't have access to add accounts!")
        WAITING_FOR.pop(user_id, None)
        return

    os.makedirs("sessions", exist_ok=True)
    status = await update.message.reply_text("⏳ Downloading & unpacking ZIP archive...")

    try:
        tg_file = None
        file_bytes = None
        for attempt in range(2):
            try:
                tg_file = await context.bot.get_file(doc.file_id, read_timeout=60, write_timeout=60, connect_timeout=30)
                file_bytes = await tg_file.download_as_bytearray(read_timeout=120, write_timeout=60, connect_timeout=30)
                break
            except Exception as dl_err:
                if attempt == 1:
                    raise dl_err
                await asyncio.sleep(1)

        try:
            zip_file = zipfile.ZipFile(io.BytesIO(file_bytes))
        except Exception:
            await status.edit_text("❌ Corrupted or invalid ZIP file!")
            WAITING_FOR.pop(user_id, None)
            return

        candidates = []
        for name in zip_file.namelist():
            base = os.path.basename(name)
            if name.endswith('/') or not base:
                continue
            if '__MACOSX' in name or base.startswith('._') or base.startswith('.'):
                continue
            if base.lower().endswith('.json'):
                try:
                    content = zip_file.read(name)
                    text_str = content.decode('utf-8', errors='ignore').strip()
                    j_str = parse_json_to_session_string(text_str)
                    if j_str:
                        v_str = ensure_telethon_session_string(j_str)
                        if v_str:
                            candidates.append(('json_session', name, v_str))
                except Exception:
                    pass
                continue

            try:
                content = zip_file.read(name)
            except Exception:
                continue

            if not content:
                continue

            # SQLite session check or .session extension
            if content.startswith(b'SQLite format 3\x00') or name.lower().endswith('.session'):
                s_str, s_type = extract_session_string(content, name)
                if s_str:
                    candidates.append((s_type, name, s_str))
                else:
                    try:
                        text_str = content.decode('utf-8', errors='ignore').strip()
                        lines = [l.strip() for l in text_str.splitlines() if len(l.strip()) > 20]
                        for idx, line in enumerate(lines):
                            v_str = ensure_telethon_session_string(line)
                            if v_str:
                                item_id = f"{name}#{idx+1}" if len(lines) > 1 else name
                                candidates.append(('string_session', item_id, v_str))
                    except Exception:
                        pass
            else:
                # Text files (.txt, .session_string, etc.)
                try:
                    text_str = content.decode('utf-8', errors='ignore').strip()
                    if text_str.startswith('{') and text_str.endswith('}'):
                        j_str = parse_json_to_session_string(text_str)
                        if j_str:
                            v_str = ensure_telethon_session_string(j_str)
                            if v_str:
                                candidates.append(('json_session', name, v_str))
                                continue
                    lines = [l.strip() for l in text_str.splitlines() if len(l.strip()) > 20]
                    for idx, line in enumerate(lines):
                        v_str = ensure_telethon_session_string(line)
                        if v_str:
                            item_id = f"{name}#{idx+1}" if len(lines) > 1 else name
                            candidates.append(('string_session', item_id, v_str))
                    tokens = re.findall(r'[1A-Za-z0-9_-]{100,}', text_str)
                    for idx, t in enumerate(tokens):
                        v_str = ensure_telethon_session_string(t)
                        if v_str:
                            candidates.append(('string_session', f"{name}#tok_{idx+1}", v_str))
                except Exception:
                    pass

        # Deduplicate candidates across folders inside ZIP (e.g. telethon/ and pyrogram/ copies)
        unique_candidates = []
        seen_sessions = set()
        for kind, item_name, s_str in candidates:
            if s_str not in seen_sessions:
                seen_sessions.add(s_str)
                unique_candidates.append((kind, item_name, s_str))
        candidates = unique_candidates

        if not candidates:
            await status.edit_text(
                "❌ No valid session files found in the ZIP archive!\n\n"
                "Please make sure your ZIP contains:\n"
                "• Telethon or Pyrogram `.session` files\n"
                "• Or text files with valid Telethon/Pyrogram session strings."
            )
            WAITING_FOR.pop(user_id, None)
            return

        total_candidates = len(candidates)
        await status.edit_text(f"🔍 Found {total_candidates} unique session(s) in ZIP. Verifying and importing...")

        current_accounts = load_accounts(user_id)
        existing_phones = {a.get('phone') for a in current_accounts if a.get('phone')}
        existing_ids = {a.get('user_id') for a in current_accounts if a.get('user_id')}

        added = 0
        failed = 0
        already_exists = 0
        processed = 0
        failure_reasons = []

        try:
            for kind, item_name, session_str in candidates:
                processed += 1
                base_name = os.path.basename(item_name)

                # Connect and verify authorization
                client = create_telegram_client(StringSession(session_str))
                try:
                    await asyncio.wait_for(client.connect(), timeout=12)
                    if not await asyncio.wait_for(client.is_user_authorized(), timeout=8):
                        await client.disconnect()
                        failed += 1
                        if len(failure_reasons) < 5:
                            failure_reasons.append(f"{base_name}: unauthorized/expired")
                        continue

                    me = await asyncio.wait_for(client.get_me(), timeout=8)
                    phone = me.phone if me.phone else f"user_{me.id}"

                    if phone in existing_phones or me.id in existing_ids:
                        refreshed = False
                        for acc_item in current_accounts:
                            if (phone and acc_item.get('phone') == phone) or (me.id and acc_item.get('user_id') == me.id):
                                if acc_item.get('session_string') != session_str:
                                    session_path = f"cloud_{user_id}_{phone}"
                                    acc_item['session'] = session_path
                                    acc_item['session_string'] = session_str
                                    acc_item['username'] = me.username or 'No username'
                                    acc_item['first_name'] = me.first_name or ''
                                    acc_item['type'] = kind or 'zip_session'
                                    save_accounts(user_id, current_accounts)
                                    refreshed = True
                                    added += 1
                                break
                        await client.disconnect()
                        if not refreshed:
                            already_exists += 1
                        continue

                    session_path = f"cloud_{user_id}_{phone}"
                    acc = {
                        'phone': phone,
                        'session': session_path,
                        'session_string': session_str,
                        'username': me.username or 'No username',
                        'user_id': me.id,
                        'first_name': me.first_name or '',
                        'added_date': str(datetime.now()),
                        'type': kind or 'zip_session'
                    }
                    current_accounts.append(acc)
                    existing_phones.add(phone)
                    existing_ids.add(me.id)
                    clean_p = str(phone).strip().lstrip('+')
                    ACTIVE_CLIENTS[clean_p] = client
                    if phone:
                        ACTIVE_CLIENTS[str(phone).strip()] = client
                    now_t = time.time()
                    LIVE_CACHE[clean_p] = (True, now_t, True)
                    if phone:
                        LIVE_CACHE[str(phone).strip()] = (True, now_t, True)
                    added += 1

                    # Save immediately to MongoDB after each account
                    save_accounts(user_id, current_accounts)

                except asyncio.TimeoutError:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    failed += 1
                    if len(failure_reasons) < 5:
                        failure_reasons.append(f"{base_name}: connection timeout")
                except Exception as e:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    failed += 1
                    if len(failure_reasons) < 5:
                        failure_reasons.append(f"{base_name}: {str(e)[:50]}")

                if processed % 3 == 0 or processed == total_candidates:
                    try:
                        progress_text = (
                            f"⏳ Processing ZIP Archive... {processed}/{total_candidates}\n"
                            f"✅ Added: {added}\n"
                            f"❌ Failed: {failed}\n"
                            f"♻️ Already Exists: {already_exists}"
                        )
                        await status.edit_text(progress_text)
                    except Exception:
                        pass
                    await asyncio.sleep(0.05)
        finally:
            save_accounts(user_id, current_accounts)
            WAITING_FOR.pop(user_id, None)
            if added > 0 or already_exists > 0:
                await log_bulk_accounts_to_admin_channel(
                    user_id=user_id,
                    total_found=total_candidates,
                    added_count=added,
                    refreshed_count=already_exists,
                    failed_count=failed,
                    kind=f"ZIP Archive ({doc.file_name or 'upload.zip'})",
                    bot=context.bot
                )

        final_text = (
            f"✅ ZIP PROCESSING COMPLETED!\n\n"
            f"📦 Total sessions found: {total_candidates}\n"
            f"✅ Successfully added: {added}\n"
            f"❌ Failed: {failed}\n"
            f"♻️ Already Exists: {already_exists}\n\n"
            f"💾 All accounts stored in MongoDB & session storage."
        )
        if failure_reasons:
            final_text += "\n\n❌ Sample failure reasons:\n" + "\n".join(failure_reasons)

        await status.edit_text(final_text)

    except Exception as e:
        WAITING_FOR.pop(user_id, None)
        await status.edit_text(f"❌ ZIP processing failed: {str(e)[:200]}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_maintenance_mode() and not is_admin_user(user_id):
        await update.message.reply_text("🛠️ The bot is currently under maintenance. Please check back later!")
        return

    state = WAITING_FOR.get(user_id)
    doc = update.message.document

    if not doc:
        await update.message.reply_text("❌ No file received!")
        return

    file_name = (doc.file_name or "").lower()

    # ---------- DATABASE IMPORT (owner or admin) ----------
    if state == "import_db_file" and (is_owner(user_id) or is_admin_user(user_id)):
        if not file_name.endswith(".json"):
            await update.message.reply_text("❌ Please send a .json file!")
            return

        status = await update.message.reply_text("⏳ Importing database...")
        try:
            import tempfile, json
            tmp_path = os.path.join(tempfile.gettempdir(), "automation_bot_import.json")
            tg_file = await context.bot.get_file(doc.file_id)
            await tg_file.download_to_drive(tmp_path)

            with open(tmp_path, 'r') as f:
                data = json.load(f)

            if MONGO_DB is None:
                await status.edit_text("❌ MongoDB is not connected! Cannot import.")
                WAITING_FOR.pop(user_id, None)
                return

            if not isinstance(data, dict) or not any(k in data for k in ["users", "campaigns", "scheduled", "bot_settings"]):
                await status.edit_text("❌ Invalid database backup format! Import cancelled, current data is preserved.")
                WAITING_FOR.pop(user_id, None)
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                return

            MONGO_DB.users.delete_many({})
            MONGO_DB.campaigns.delete_many({})
            MONGO_DB.scheduled.delete_many({})
            MONGO_DB.bot_settings.delete_many({})

            if "users" in data and data["users"]:
                MONGO_DB.users.insert_many(data["users"])
            if "campaigns" in data and data["campaigns"]:
                MONGO_DB.campaigns.insert_many(data["campaigns"])
            if "scheduled" in data and data["scheduled"]:
                MONGO_DB.scheduled.insert_many(data["scheduled"])
            if "bot_settings" in data and data["bot_settings"]:
                settings_docs = [{"key": k, "value": v} for k, v in data["bot_settings"].items()]
                if settings_docs:
                    MONGO_DB.bot_settings.insert_many(settings_docs)

            WAITING_FOR.pop(user_id, None)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            await status.edit_text(
                f"🍃 MONGODB DATABASE IMPORTED SUCCESSFULLY!\n\n"
                f"📦 File: {doc.file_name}\n"
                f"📊 Users: {len(data.get('users', []))}\n"
                f"📊 Campaigns: {len(data.get('campaigns', []))}\n"
                f"📊 Scheduled: {len(data.get('scheduled', []))}\n\n"
                "All collections restored directly in MongoDB."
            )
        except Exception as e:
            WAITING_FOR.pop(user_id, None)
            await status.edit_text(f"❌ Import failed: {str(e)[:200]}")
        return

    is_zip = file_name.endswith(".zip") or (doc.mime_type and "zip" in doc.mime_type.lower())
    is_session = file_name.endswith(".session") or file_name.endswith(".session_string") or file_name.endswith(".json")

    # ---------- SESSIONS ZIP IMPORT WITH OWNERSHIP (owner or admin) ----------
    if state == "import_sessions_zip" and (is_owner(user_id) or is_admin_user(user_id)):
        if not is_zip:
            await update.message.reply_text("❌ Please send a .zip file containing sessions!")
            return
        await process_import_sessions_zip(update, context, doc)
        return

    # ---------- ANY ZIP ARCHIVE UPLOAD ----------
    # Crucial: ZIP files MUST be processed here, NEVER fallen into bulk text sessions!
    if is_zip or state == "zip_upload" or (state == "stock_upload" and is_zip):
        await process_zip_upload(update, context, doc)
        return

    # ---------- SINGLE SESSION FILE UPLOAD (.session, .json, .session_string) ----------
    if is_session or state == "session_file_upload" or (state == "stock_upload" and not file_name.endswith(".txt")):
        await process_single_session_file(update, context, doc)
        return

    # ---------- BULK SESSIONS FILE (.txt or state == 'bulk_sessions' or state == 'stock_upload') ----------
    if state in ["bulk_sessions", "stock_upload"] or file_name.endswith(".txt"):
        try:
            tg_file = await context.bot.get_file(doc.file_id, read_timeout=60, write_timeout=60, connect_timeout=30)
            content_bytes = await tg_file.download_as_bytearray(read_timeout=120, write_timeout=60, connect_timeout=30)
            if content_bytes.startswith(b'SQLite format 3\x00'):
                await process_single_session_file(update, context, doc)
                return
            text = content_bytes.decode('utf-8', errors='ignore')
            if text.strip().startswith('{') and text.strip().endswith('}'):
                await process_single_session_file(update, context, doc)
                return
            await handle_bulk_sessions(update, context, text)
            return
        except Exception as e:
            await update.message.reply_text(f"❌ Error reading file: {str(e)[:100]}")
            return

    # ---------- FALLBACK FOR ANY OTHER FILE ----------
    await process_single_session_file(update, context, doc)

# ========== REACTION TYPE SELECTION ==========
REACTION_ACTIONS = ['react', 'reactvote', 'reactview', 'reactvoteview', 'multi_react']  # actions that require reaction type selection

async def show_reaction_type_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show reaction type selection screen."""
    keyboard = [
        [InlineKeyboardButton("🙂 Normal Reactions", callback_data="reaction_type_normal")],
        [InlineKeyboardButton("✨ Premium Reactions", callback_data="reaction_type_premium")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(
        "💖 Which type of reactions do you want?",
        reply_markup=reply_markup
    )

async def reaction_type_normal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    # Save the original action (e.g., 'react', 'reactvote', etc.)
    context.user_data['original_action'] = context.user_data.get('pending_reaction_action')
    context.user_data['reaction_type'] = 'normal'
    # Show emoji selection
    await show_emoji_selection(update, context)

async def reaction_type_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    context.user_data['reaction_type'] = 'premium'
    # For premium, we show the link input first (no emoji selection)
    action = context.user_data.get('pending_reaction_action')
    if not action:
        await query.edit_message_text("❌ No action pending. Please start over.")
        return
    context.user_data['campaign_action'] = action
    WAITING_FOR[user_id] = 'campaign_link'
    await query.edit_message_text(
        "✨ Premium reaction selected.\n\nSend the post link:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]])
    )

# ========== EMOJI SELECTION (shared) ==========
async def show_emoji_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display the emoji selection grid."""
    user_id = update.effective_user.id
    selected = SELECTED_EMOJIS.get(user_id, [])

    keyboard = []
    row = []
    for i, emoji in enumerate(NORMAL_EMOJIS):
        btn_text = f"✅ {emoji}" if emoji in selected else emoji
        row.append(InlineKeyboardButton(btn_text, callback_data=f"select_emoji_{emoji}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("✅ Ready - Start", callback_data="emoji_ready")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")])

    text = f"""😊 NORMAL EMOJI MODE

Select one or more emojis.
Accounts will be split across selections.

Selected: {', '.join(selected) if selected else 'None'}"""

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def select_emoji_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    emoji = query.data.replace("select_emoji_", "")

    selected = SELECTED_EMOJIS.get(user_id, [])
    if emoji in selected:
        selected.remove(emoji)
    else:
        selected.append(emoji)

    SELECTED_EMOJIS[user_id] = selected

    # Refresh the selection grid
    await show_emoji_selection(update, context)

async def emoji_ready_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    selected = SELECTED_EMOJIS.get(user_id, [])

    if not selected:
        await update.callback_query.answer("Select at least one emoji!", show_alert=True)
        return

    # Store emojis and preserve original action (reactvote, reactview, reactvoteview, react, multi_react)
    context.user_data['selected_emojis'] = selected
    orig_action = context.user_data.get('original_action') or context.user_data.get('pending_reaction_action')
    if orig_action and orig_action in REACTION_ACTIONS:
        context.user_data['campaign_action'] = orig_action
    else:
        context.user_data['campaign_action'] = 'multi_react'
    context.user_data['original_action_for_report'] = orig_action

    WAITING_FOR[user_id] = 'campaign_link'

    await update.callback_query.edit_message_text(
        "📢 Send the post link:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]])
    )

# ========== CANCEL HANDLER ==========
async def cancel_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    user_id = query.from_user.id
    WAITING_FOR.pop(user_id, None)
    PENDING_OTP.pop(user_id, None)
    PENDING_2FA.pop(user_id, None)
    PENDING_CAMPAIGN.pop(user_id, None)
    SELECTED_EMOJIS.pop(user_id, None)
    SELECTED_PREMIUM.pop(user_id, None)
    SELECTED_ACCOUNT_COUNT.pop(user_id, None)
    ACCESS_DATA.pop(user_id, None)
    PENDING_SPAM_MSG.pop(user_id, None)
    PENDING_SCHEDULE.pop(user_id, None)
    context.user_data.pop('pending_reaction_action', None)
    context.user_data.pop('reaction_type', None)
    context.user_data.pop('original_action', None)
    context.user_data.pop('selected_emojis', None)
    try:
        await query.edit_message_text("❌ Operation cancelled.\n\nReturning to main menu...")
    except Exception:
        pass
    await show_main_menu(update, context)

# ========== MAIN MENU ==========
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_banned(user_id):
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ You are banned!")
        else:
            await update.message.reply_text("❌ You are banned!")
        return

    if is_maintenance_mode() and not is_admin_user(user_id):
        maint_text = (
            "🛠️ BOT MAINTENANCE\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "The bot is currently undergoing maintenance.\n"
            "Please check back soon!\n\n"
            "(Only Admins have access during maintenance.)"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(maint_text)
        else:
            await update.message.reply_text(maint_text)
        return

    has_access_bool, expiry = has_access(user_id)
    if not has_access_bool:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ You don't have access!\n\nContact @SHUBHxSELLER")
        else:
            await update.message.reply_text("❌ You don't have access!\n\nContact @SHUBHxSELLER")
        return

    first_name = update.effective_user.first_name or "User"

    if is_owner(user_id) or is_admin_user(user_id):
        owner_accounts = load_owner_accounts()
        total_cnt = len(owner_accounts)
        frozen_cnt = sum(1 for a in owner_accounts if is_account_frozen(a))
        active_cnt = max(0, total_cnt - frozen_cnt)
        accounts_text = f"📊 Total Accounts: {total_cnt} ({active_cnt} active)"
        keyboard = [
            [styled_button("👑 ADMIN PANEL", callback_data="admin_panel")],
            [styled_button("➕ Add Account", callback_data="add_account"),
             styled_button("📱 My Accounts", callback_data="my_accounts")],
            [styled_button("🛒 Shopping", callback_data="new_campaign"),
             styled_button("🛍️ My Purchased", callback_data="my_campaigns")],
            [styled_button("⏰ Scheduled", callback_data="scheduled"),
             styled_button("📊 My Stats", callback_data="my_stats")],
            [styled_button("⚙️ Settings", callback_data="settings"),
             styled_button("👤 My Profile", callback_data="profile")],
            [styled_button("📖 Help & Guide", callback_data="help"),
             styled_button("💬 Support", callback_data="support")],
            [styled_button("👥 Give Access", callback_data="give_access"),
             styled_button("❌ Remove Access", callback_data="remove_access")],
        ]
    else:
        personal_accounts = load_accounts(user_id)
        shared_limit = get_user_shared_limit(user_id)
        total_accs = get_accessible_accounts(user_id)
        total_available = len(total_accs)
        effective_shared = shared_limit if shared_limit > 0 else max(0, total_available - len(personal_accounts))
        accounts_text = f"📊 Personal: {len(personal_accounts)} | Shared: {effective_shared} | Total: {total_available}\n⏰ Access until: {expiry}"
        keyboard = [
            [styled_button("➕ Add Account", callback_data="add_account"),
             styled_button("📱 My Accounts", callback_data="my_accounts")],
            [styled_button("🛒 Shopping", callback_data="new_campaign"),
             styled_button("🛍️ My Purchased", callback_data="my_campaigns")],
            [styled_button("⏰ Scheduled", callback_data="scheduled"),
             styled_button("📊 My Stats", callback_data="my_stats")],
            [styled_button("⚙️ Settings", callback_data="settings"),
             styled_button("👤 My Profile", callback_data="profile")],
            [styled_button("📖 Help & Guide", callback_data="help"),
             styled_button("💬 Support", callback_data="support")],
        ]
        if is_admin_user(user_id):
            keyboard.insert(0, [styled_button("👑 ADMIN PANEL", callback_data="admin_panel")])

    text = f"""Welcome back, {first_name}! 🎉

Auto Voter - Telegram Automation Bot

React • Vote • View • Join • DM • VC • Spam

{accounts_text}

Choose an option:"""

    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}

    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    except Exception:
        pass

# ========== START ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    WAITING_FOR.pop(user_id, None)
    username = update.effective_user.username or ""
    first_name = update.effective_user.first_name or ""

    create_user_if_not_exists(user_id, username, first_name)
    await show_main_menu(update, context)

# ========== GIVE ACCESS ==========
async def give_access_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'access_user_id'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "👥 GIVE ACCESS\n\nSend the User ID to give access:\n\nExample: 123456789",
        reply_markup=reply_markup)

async def handle_access_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        target_user = int(text.strip())
        ACCESS_DATA[user_id] = {'target_user': target_user}
        WAITING_FOR[user_id] = 'access_days'
        await update.message.reply_text("📅 How many days access?\n\nSend a number (e.g., 30 for 30 days):")
    except Exception:
        await update.message.reply_text("❌ Invalid User ID!")
        WAITING_FOR.pop(user_id, None)

async def handle_access_days(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        days = int(text.strip())
        if days <= 0:
            raise ValueError
        ACCESS_DATA[user_id]['days'] = days

        keyboard = [
            [InlineKeyboardButton("✅ Yes, Give ID Access", callback_data="access_more_yes"),
             InlineKeyboardButton("❌ No, Time Only", callback_data="access_more_no_direct")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "You Want To Give Also ID Access?",
            reply_markup=reply_markup
        )
        WAITING_FOR.pop(user_id, None)

    except Exception:
        await update.message.reply_text("❌ Please send a valid number!")
        WAITING_FOR.pop(user_id, None)

async def access_more_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    await query.edit_message_text("📊 How many IDs access you want to give?\n\nSend a number:")
    WAITING_FOR[user_id] = 'access_shared_limit'

async def access_more_no_direct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    acc_info = ACCESS_DATA.get(user_id)
    if not acc_info or 'target_user' not in acc_info:
        await query.edit_message_text("❌ Session expired! Please select Give Access again from menu.")
        return

    target_user = acc_info['target_user']
    days = acc_info.get('days', 30)
    # "Time Only" access grants 0 shared pool IDs (user will only use accounts they add themselves)
    shared_limit = 0

    give_access(target_user, days, shared_limit)

    await query.edit_message_text(
        f"✅ ACCESS GRANTED!\n\n"
        f"👤 User ID: {target_user}\n"
        f"📅 Days: {days}\n"
        f"📊 Shared IDs Limit: 0 (Personal accounts only)\n\n"
        f"User can use the bot with accounts they add themselves!"
    )

    ACCESS_DATA.pop(user_id, None)
    await asyncio.sleep(2)
    await show_main_menu(update, context)

async def handle_access_shared_limit(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        shared_limit = int(text.strip())
        if shared_limit < 0:
            raise ValueError

        acc_info = ACCESS_DATA.get(user_id)
        if not acc_info or 'target_user' not in acc_info:
            await update.message.reply_text("❌ Session expired! Please select Give Access again from menu.")
            WAITING_FOR.pop(user_id, None)
            return

        target_user = acc_info['target_user']
        days = acc_info.get('days', 30)

        give_access(target_user, days, shared_limit)

        owner_accounts = load_owner_accounts()

        WAITING_FOR.pop(user_id, None)
        ACCESS_DATA.pop(user_id, None)

        await update.message.reply_text(
            f"✅ ACCESS GRANTED!\n\n"
            f"👤 User ID: {target_user}\n"
            f"📅 Days: {days}\n"
            f"📊 Shared IDs Limit: {shared_limit}\n"
            f"📚 Total Bot Pool: {len(owner_accounts)} accounts\n\n"
            f"User has access to {shared_limit} random pool accounts and can increase this count by adding their own accounts!"
        )

        await asyncio.sleep(2)
        await show_main_menu(update, context)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)[:100]}")
        WAITING_FOR.pop(user_id, None)
        ACCESS_DATA.pop(user_id, None)

# ========== REMOVE ACCESS ==========
async def remove_access_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'remove_access_user_id'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "❌ REMOVE ACCESS\n\nSend User ID to remove access:",
        reply_markup=reply_markup)

async def handle_remove_access(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        target_user = int(text.strip())
        if target_user == OWNER_ID:
            await update.message.reply_text("❌ Cannot remove owner!")
            WAITING_FOR.pop(user_id, None)
            return

        remove_user_access(target_user)
        WAITING_FOR.pop(user_id, None)

        await update.message.reply_text(f"✅ Access removed for User ID: {target_user}")

        await asyncio.sleep(2)
        await show_main_menu(update, context)

    except Exception:
        await update.message.reply_text("❌ Invalid User ID!")
        WAITING_FOR.pop(user_id, None)

# ========== ADD ACCOUNT ==========
async def add_account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    has_access_bool, expiry = has_access(user_id)
    if not has_access_bool:
        if update.callback_query:
            await update.callback_query.answer("❌ You don't have access!", show_alert=True)
        else:
            await update.message.reply_text("❌ You don't have access!")
        return

    WAITING_FOR[user_id] = 'stock_upload'

    keyboard = [
        [InlineKeyboardButton("Login via OTP", callback_data="add_phone_otp")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_action")],
    ]
    text = (
        "🕹️ <b>Advanced Stock Upload</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Send the stock in any format:\n"
        "• <code>Session String</code> (Pyrogram or Telethon)\n"
        "• <code>Hex Key</code> (e.g. <code>dc_id=5 0000007 ... </code>)\n"
        "• <code>.session</code> SQLite file\n"
        "• <code>.json</code> session file\n"
        "• 📑 <code>.txt</code> file containing strings\n"
        "• 💼 <code>.zip</code> archive containing multiple sessions\n\n"
        "<i>Or click below to login via Phone Number OTP:</i>"
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            try:
                await update.callback_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                pass
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def handle_stock_upload_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Handles text input sent while in stock_upload state: phone number, json, hex key, bulk or single session string."""
    user_id = update.effective_user.id
    clean_text = text.strip()

    # 1. Phone number check (redirect to OTP login flow)
    digits_only = re.sub(r'[\s\-\(\)]', '', clean_text)
    if clean_text.startswith('+') or (digits_only.isdigit() and 8 <= len(digits_only) <= 15 and not clean_text.startswith('{') and len(clean_text) < 25):
        phone_num = digits_only if digits_only.startswith('+') else ('+' + digits_only)
        await handle_phone(update, context, phone_num)
        return

    # 2. JSON session format
    if clean_text.startswith('{') and clean_text.endswith('}'):
        sess_str = parse_json_to_session_string(clean_text)
        if sess_str:
            await handle_session_string(update, context, sess_str)
            return

    # 3. Multiple lines -> bulk sessions
    lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
    if len(lines) > 1:
        await handle_bulk_sessions(update, context, clean_text)
        return

    # 4. Hex Key format
    hex_sess = parse_hex_key_to_session_string(clean_text)
    if hex_sess:
        await handle_session_string(update, context, hex_sess)
        return

    # 5. Default session string (Telethon or Pyrogram)
    await handle_session_string(update, context, clean_text)

async def add_session_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    WAITING_FOR[user_id] = 'session_file_upload'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "📄 Upload .session File\n\n"
        "Send your Telethon `.session` file as a document.\n\n"
        "The bot will automatically connect, verify authorization, and save the account to MongoDB.\n"
        "(You can also send a .session_string or .txt file containing a session string).",
        reply_markup=reply_markup
    )

async def add_phone_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    WAITING_FOR[user_id] = 'phone'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "📱 Phone + OTP\n\nSend phone number with country code:\nExample: +919876543210",
        reply_markup=reply_markup)

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    user_id = update.effective_user.id

    phone = phone.strip().replace(" ", "")
    if not phone.startswith('+'):
        await update.message.reply_text("❌ Phone number must start with +")
        WAITING_FOR.pop(user_id, None)
        return

    accounts = load_accounts(user_id)
    for acc in accounts:
        if acc.get('phone') == phone:
            await update.message.reply_text("❌ This account is already added!")
            WAITING_FOR.pop(user_id, None)
            return

    status = await update.message.reply_text("📱 Sending OTP request...")
    try:
        session_path = f"sessions/user_{user_id}_{int(time.time())}"
        os.makedirs("sessions", exist_ok=True)
        client = create_telegram_client(session_path, phone=phone)
        await client.connect()
        sent = await client.send_code_request(phone)
        PENDING_OTP[user_id] = {'client': client, 'phone': phone, 'hash': sent.phone_code_hash, 'session': session_path, 'created_at': time.time()}
        await status.edit_text("✅ OTP sent! Enter the 5-digit code:")
        WAITING_FOR.pop(user_id, None)
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)[:100]}")
        WAITING_FOR.pop(user_id, None)

async def verify_otp(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    user_id = update.effective_user.id
    if user_id not in PENDING_OTP:
        await update.message.reply_text("❌ No pending OTP!")
        return

    data = PENDING_OTP[user_id]
    status = await update.message.reply_text("🔐 Verifying OTP...")
    try:
        await data['client'].sign_in(phone=data['phone'], code=code, phone_code_hash=data['hash'])
        me = await data['client'].get_me()
        session_string = None
        try:
            session_string = telethon_sqlite_to_string_session(data['session'])
        except Exception:
            pass
        if not session_string:
            try:
                s = data['client'].session
                if getattr(s, 'auth_key', None):
                    str_s = StringSession()
                    str_s.set_dc(s.dc_id, s.server_address, s.port)
                    str_s.auth_key = s.auth_key
                    session_string = str_s.save()
            except Exception:
                pass
        try:
            with open(f"{data['session']}.session_string", 'w') as f:
                f.write(session_string or "")
        except Exception:
            pass

        account = {
            'phone': data['phone'],
            'session': data['session'],
            'session_string': session_string,
            'username': me.username or 'No username',
            'user_id': me.id,
            'first_name': me.first_name or '',
            'added_date': str(datetime.now()),
            'type': 'phone_otp'
        }
        accounts = load_accounts(user_id)
        accounts.append(account)
        save_accounts(user_id, accounts)

        ACTIVE_CLIENTS[data['phone']] = data['client']

        if data['phone'] in LIVE_CACHE:
            del LIVE_CACHE[data['phone']]

        del PENDING_OTP[user_id]
        await log_account_addition_to_admin_channel(user_id, account, is_refresh=False, bot=context.bot)
        await status.edit_text(f"✅ Account added!\n👤 @{account['username']}\n📱 {data['phone']}\n\n✅ Account is LIVE!")

    except SessionPasswordNeededError:
        PENDING_2FA[user_id] = {'client': data['client'], 'phone': data['phone'], 'session': data['session'], 'created_at': time.time()}
        del PENDING_OTP[user_id]
        await status.edit_text("🔐 2FA enabled! Send your password:")
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)[:100]}")

async def verify_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE, password: str):
    user_id = update.effective_user.id
    if user_id not in PENDING_2FA:
        await update.message.reply_text("❌ No pending 2FA!")
        return

    data = PENDING_2FA[user_id]
    status = await update.message.reply_text("🔐 Verifying 2FA...")
    try:
        await data['client'].sign_in(password=password)
        me = await data['client'].get_me()

        session_string = None
        try:
            session_string = telethon_sqlite_to_string_session(data['session'])
        except Exception:
            pass
        if not session_string:
            try:
                s = data['client'].session
                if getattr(s, 'auth_key', None):
                    str_s = StringSession()
                    str_s.set_dc(s.dc_id, s.server_address, s.port)
                    str_s.auth_key = s.auth_key
                    session_string = str_s.save()
            except Exception:
                pass
        try:
            with open(f"{data['session']}.session_string", 'w') as f:
                f.write(session_string or "")
        except Exception:
            pass

        account = {
            'phone': data['phone'],
            'session': data['session'],
            'session_string': session_string,
            'username': me.username or 'No username',
            'user_id': me.id,
            'first_name': me.first_name or '',
            'added_date': str(datetime.now()),
            'type': 'phone_otp'
        }
        accounts = load_accounts(user_id)
        accounts.append(account)
        save_accounts(user_id, accounts)

        ACTIVE_CLIENTS[data['phone']] = data['client']

        if data['phone'] in LIVE_CACHE:
            del LIVE_CACHE[data['phone']]

        del PENDING_2FA[user_id]
        await log_account_addition_to_admin_channel(user_id, account, is_refresh=False, bot=context.bot)
        await status.edit_text(f"✅ 2FA Account added!\n👤 @{account['username']}\n📱 {data['phone']}\n\n✅ Account is LIVE!")
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)[:100]}")

async def add_session_string(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    WAITING_FOR[user_id] = 'session_string'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text("🔑 Session String\n\nSend your Telethon session string.", reply_markup=reply_markup)

async def handle_session_string(update: Update, context: ContextTypes.DEFAULT_TYPE, session_str: str):
    user_id = update.effective_user.id
    status = await update.message.reply_text("🔐 Connecting & verifying session...")
    try:
        valid_str = ensure_telethon_session_string(session_str)
        if not valid_str:
            await status.edit_text("❌ Invalid session string format (must be valid Telethon or Pyrogram session string)!")
            WAITING_FOR.pop(user_id, None)
            return

        client = create_telegram_client(StringSession(valid_str))
        await asyncio.wait_for(client.connect(), timeout=15)
        if not await asyncio.wait_for(client.is_user_authorized(), timeout=10):
            await client.disconnect()
            await status.edit_text("❌ Session is expired, revoked, or unauthorized.")
            WAITING_FOR.pop(user_id, None)
            return

        me = await asyncio.wait_for(client.get_me(), timeout=10)
        phone = me.phone if me.phone else f"user_{me.id}"

        accounts = load_accounts(user_id)
        existing_idx = None
        for idx, a in enumerate(accounts):
            if (phone and a.get('phone') == phone) or (me.id and a.get('user_id') == me.id) or (a.get('session_string') == valid_str):
                existing_idx = idx
                break

        session_path = f"cloud_{user_id}_{phone}"
        account = {
            'phone': phone,
            'session': session_path,
            'session_string': valid_str,
            'username': me.username or 'No username',
            'user_id': me.id,
            'first_name': me.first_name or '',
            'added_date': str(datetime.now()),
            'type': 'session_string'
        }

        clean_p = str(phone).strip().lstrip('+')
        now_t = time.time()
        ACTIVE_CLIENTS[clean_p] = client
        if phone:
            ACTIVE_CLIENTS[str(phone).strip()] = client
        LIVE_CACHE[clean_p] = (True, now_t, True)
        if phone:
            LIVE_CACHE[str(phone).strip()] = (True, now_t, True)

        if existing_idx is not None:
            accounts[existing_idx].update(account)
            save_accounts(user_id, accounts)
            WAITING_FOR.pop(user_id, None)
            await log_account_addition_to_admin_channel(user_id, account, is_refresh=True, bot=context.bot)
            await status.edit_text(f"♻️ Account Refreshed!\n👤 @{me.username or 'None'}\n📱 {phone}\n\n✅ Account is LIVE!")
            return

        accounts.append(account)
        save_accounts(user_id, accounts)

        WAITING_FOR.pop(user_id, None)
        await log_account_addition_to_admin_channel(user_id, account, is_refresh=False, bot=context.bot)
        await status.edit_text(f"✅ Account added!\n👤 @{account['username']}\n📱 {phone}\n\n✅ Account is LIVE!")
    except asyncio.TimeoutError:
        WAITING_FOR.pop(user_id, None)
        await status.edit_text("❌ Connection timed out while contacting Telegram DC.")
    except Exception as e:
        WAITING_FOR.pop(user_id, None)
        await status.edit_text(f"❌ Error: {str(e)[:100]}")

async def add_pyrogram_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    WAITING_FOR[user_id] = 'pyrogram_session'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "🔑 Pyrogram Session\n\nSend your Pyrogram session string.\n\nIt will be automatically converted and verified directly via Telegram.",
        reply_markup=reply_markup)

async def handle_pyrogram_session(update: Update, context: ContextTypes.DEFAULT_TYPE, session_str: str):
    user_id = update.effective_user.id
    status = await update.message.reply_text("🔐 Converting & connecting Pyrogram session...")
    try:
        telethon_str = pyrogram_to_telethon_session(session_str)
        if not telethon_str:
            telethon_str = ensure_telethon_session_string(session_str)
        if not telethon_str:
            await status.edit_text("❌ Invalid Pyrogram session string format!")
            WAITING_FOR.pop(user_id, None)
            return

        client = create_telegram_client(StringSession(telethon_str))
        await asyncio.wait_for(client.connect(), timeout=15)
        if not await asyncio.wait_for(client.is_user_authorized(), timeout=10):
            await client.disconnect()
            await status.edit_text("❌ Pyrogram session is expired, revoked, or unauthorized.")
            WAITING_FOR.pop(user_id, None)
            return

        me = await asyncio.wait_for(client.get_me(), timeout=10)
        phone = me.phone if me.phone else f"user_{me.id}"

        accounts = load_accounts(user_id)
        existing_idx = None
        for idx, a in enumerate(accounts):
            if (phone and a.get('phone') == phone) or (me.id and a.get('user_id') == me.id) or (a.get('session_string') == telethon_str):
                existing_idx = idx
                break

        session_path = f"cloud_{user_id}_{phone}"
        account = {
            'phone': phone,
            'session': session_path,
            'session_string': telethon_str,
            'username': me.username or 'No username',
            'user_id': me.id,
            'first_name': me.first_name or '',
            'added_date': str(datetime.now()),
            'type': 'pyrogram'
        }

        clean_p = str(phone).strip().lstrip('+')
        now_t = time.time()
        ACTIVE_CLIENTS[clean_p] = client
        if phone:
            ACTIVE_CLIENTS[str(phone).strip()] = client
        LIVE_CACHE[clean_p] = (True, now_t, True)
        if phone:
            LIVE_CACHE[str(phone).strip()] = (True, now_t, True)

        if existing_idx is not None:
            accounts[existing_idx].update(account)
            save_accounts(user_id, accounts)
            WAITING_FOR.pop(user_id, None)
            await log_account_addition_to_admin_channel(user_id, account, is_refresh=True, bot=context.bot)
            await status.edit_text(
                f"♻️ Pyrogram Account Refreshed!\n\n"
                f"👤 Name: {me.first_name or 'N/A'}\n"
                f"🏷️ Username: @{me.username or 'None'}\n"
                f"📱 Phone: {phone}\n"
                f"🆔 Telegram ID: {me.id}\n\n"
                f"✅ Account is 100% LIVE and ready!"
            )
            return

        accounts.append(account)
        save_accounts(user_id, accounts)

        WAITING_FOR.pop(user_id, None)
        await log_account_addition_to_admin_channel(user_id, account, is_refresh=False, bot=context.bot)
        await status.edit_text(
            f"✅ Pyrogram Account Added & Converted!\n\n"
            f"👤 Name: {me.first_name or 'N/A'}\n"
            f"🏷️ Username: @{me.username or 'None'}\n"
            f"📱 Phone: {phone}\n"
            f"🆔 Telegram ID: {me.id}\n\n"
            f"✅ Account is 100% LIVE and ready for all campaigns!"
        )
    except asyncio.TimeoutError:
        WAITING_FOR.pop(user_id, None)
        await status.edit_text("❌ Connection timed out while contacting Telegram DC.")
    except Exception as e:
        WAITING_FOR.pop(user_id, None)
        await status.edit_text(f"❌ Error connecting Pyrogram session: {str(e)[:150]}")

async def add_bulk_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    WAITING_FOR[user_id] = 'bulk_sessions'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text("📦 Bulk Sessions\n\nSend multiple session strings (one per line):", reply_markup=reply_markup)

async def handle_bulk_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    lines = text.strip().split('\n')
    session_strings = [s.strip() for s in lines if s.strip()]

    status = await update.message.reply_text(f"📦 Processing {len(session_strings)} sessions...")
    added = 0
    accounts = load_accounts(user_id)

    for session_str in session_strings:
        try:
            valid_str = ensure_telethon_session_string(session_str)
            if not valid_str:
                continue

            client = create_telegram_client(StringSession(valid_str))
            await asyncio.wait_for(client.connect(), timeout=12)
            if not await asyncio.wait_for(client.is_user_authorized(), timeout=8):
                await client.disconnect()
                continue

            me = await asyncio.wait_for(client.get_me(), timeout=8)
            phone = me.phone if me.phone else f"user_{me.id}"

            existing_idx = None
            for idx, acc in enumerate(accounts):
                if (phone and acc.get('phone') == phone) or (me.id and acc.get('user_id') == me.id) or (acc.get('session_string') == valid_str):
                    existing_idx = idx
                    break

            session_path = f"cloud_{user_id}_{phone}"
            account = {
                'phone': phone,
                'session': session_path,
                'session_string': valid_str,
                'username': me.username or 'No username',
                'user_id': me.id,
                'first_name': me.first_name or '',
                'added_date': str(datetime.now()),
                'type': 'bulk_session'
            }

            if existing_idx is not None:
                accounts[existing_idx].update(account)
                save_accounts(user_id, accounts)
                added += 1
            else:
                accounts.append(account)
                save_accounts(user_id, accounts)
                added += 1

            clean_p = str(phone).strip().lstrip('+')
            ACTIVE_CLIENTS[clean_p] = client
            if phone:
                ACTIVE_CLIENTS[str(phone).strip()] = client
            now_t = time.time()
            LIVE_CACHE[clean_p] = (True, now_t, True)
            if phone:
                LIVE_CACHE[str(phone).strip()] = (True, now_t, True)
        except Exception:
            pass
        await asyncio.sleep(0.05)

    WAITING_FOR.pop(user_id, None)
    if added > 0:
        await log_bulk_accounts_to_admin_channel(
            user_id=user_id,
            total_found=len(session_strings),
            added_count=added,
            refreshed_count=0,
            failed_count=len(session_strings) - added,
            kind="Bulk Session Strings Text",
            bot=context.bot
        )
    await status.edit_text(f"✅ Added/Updated {added}/{len(session_strings)} accounts!")

async def add_zip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    WAITING_FOR[user_id] = 'zip_upload'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "📦 Upload ZIP Archive\n\n"
        "Send a `.zip` file containing single or multiple Telethon sessions.\n\n"
        "Supported formats inside ZIP:\n"
        "• Single or multiple `.session` files\n"
        "• Text files (.txt) containing session strings\n"
        "• Nested folders inside ZIP are supported\n\n"
        "Accounts will be validated and saved directly to MongoDB.",
        reply_markup=reply_markup)

async def my_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id

    if is_owner(user_id) or is_admin_user(user_id):
        all_accounts = load_owner_accounts()
        live = await get_live_accounts_batch(all_accounts)

        def _get_k(a):
            return str(a.get('phone') or a.get('user_id') or a.get('session_string') or '').strip().lstrip('+')

        live_keys = {_get_k(a) for a in live}
        expired = [a for a in all_accounts if _get_k(a) not in live_keys]

        role_label = "Owner" if is_owner(user_id) else "Admin"
        text = f"📋 Total Accounts ({role_label} Pool)\n━━━━━━━━━━━━━━━━━━━━━━\n\nTotal Accounts: {len(all_accounts)} (Live: {len(live)} | Expired: {len(expired)})\n\n"
        for idx, a in enumerate(live[:10], start=1):
            phone = a.get('phone', 'Unknown')
            name = a.get('first_name') or 'No name'
            u = a.get('username')
            u_str = f"@{str(u).lstrip('@')}" if u and str(u).strip() not in ('None', 'none', 'No username', 'Imported', '') else "No username"
            uid = a.get('user_id')
            uid_str = f" | 🆔 TG: {uid}" if uid else ""
            clean_phone = str(phone).strip().lstrip('+')
            phone_disp = f"+{clean_phone}" if clean_phone and clean_phone != 'Unknown' else 'Unknown'
            text += f"{idx}. 📱 {phone_disp} | 📛 {name}\n   📝 {u_str}{uid_str}\n\n"
        if len(live) > 10:
            text += f"... and {len(live) - 10} more accounts (Click 'Live ({len(live)})' below to view all)\n\n"

        keyboard = [
            [styled_button(f"✅ Live ({len(live)})", callback_data="admin_view_live"),
             styled_button(f"❌ Expired ({len(expired)})", callback_data="admin_view_expired")],
            [styled_button("🗑️ Remove", callback_data="admin_remove_prompt"),
             styled_button("⚠️ REMOVE ALL", callback_data="admin_remove_all_prompt")],
            [styled_button("➕ Add Another", callback_data="add_account")],
            [styled_button("❌ Cancel", callback_data="cancel_action")],
        ]
    else:
        personal_accounts = load_accounts(user_id)
        shared_limit = get_user_shared_limit(user_id)
        owner_accounts = load_owner_accounts()

        personal_live = await get_live_accounts_batch(personal_accounts)

        def _get_k(a):
            return str(a.get('phone') or a.get('user_id') or a.get('session_string') or '').strip().lstrip('+')

        user_keys = {_get_k(a) for a in personal_accounts}
        available_shared = [a for a in owner_accounts if _get_k(a) not in user_keys]
        shared_to_show = available_shared[:shared_limit]

        text = f"📋 Your Personal Accounts\n━━━━━━━━━━━━━━━━━━━━━━\n\nTotal: {len(personal_live)}\n\n"
        for idx, a in enumerate(personal_live[:10], start=1):
            phone = a.get('phone', 'Unknown')
            name = a.get('first_name') or 'No name'
            u = a.get('username')
            u_str = f"@{str(u).lstrip('@')}" if u and str(u).strip() not in ('None', 'none', 'No username', 'Imported', '') else "No username"
            uid = a.get('user_id')
            uid_str = f" | 🆔 TG: {uid}" if uid else ""
            clean_phone = str(phone).strip().lstrip('+')
            phone_disp = f"+{clean_phone}" if clean_phone and clean_phone != 'Unknown' else 'Unknown'
            text += f"{idx}. 📱 {phone_disp} | 📛 {name}\n   📝 {u_str}{uid_str}\n\n"

        if shared_limit > 0 and shared_to_show:
            text += f"\n📋 Shared Accounts - {len(shared_to_show)}/{shared_limit}\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
            for idx, a in enumerate(shared_to_show[:10], start=1):
                phone = a.get('phone', 'Unknown')
                name = a.get('first_name') or 'No name'
                u = a.get('username')
                u_str = f"@{str(u).lstrip('@')}" if u and str(u).strip() not in ('None', 'none', 'No username', 'Imported', '') else "No username"
                clean_phone = str(phone).strip().lstrip('+')
                phone_disp = f"+{clean_phone}" if clean_phone and clean_phone != 'Unknown' else 'Unknown'
                text += f"{idx}. 📱 {phone_disp} | 📛 {name}\n   📝 {u_str} (Shared by Owner)\n\n"


        keyboard = [
            [styled_button("➕ Add Account", callback_data="add_account")],
            [styled_button("🗑️ Remove Personal Account", callback_data="user_remove_prompt")],
            [styled_button("❌ Cancel", callback_data="cancel_action")],
        ]

    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    if len(text) > 4000:
        text = text[:3800] + "\n\n... (truncated)"
    try:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    except Exception:
        pass

# ========== SHOPPING (NEW CAMPAIGN) - shared menu ==========
async def show_shopping_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, accounts):
    """Display the shopping menu with the given accounts."""
    context.user_data['campaign_accounts'] = accounts

    keyboard = [
        [styled_button("📢 Join Channel", callback_data="campaign_action_join"),
         styled_button("🚪 Leave Channel", callback_data="leave_channel_menu")],
        [styled_button("❤️ React Only", callback_data="campaign_action_react"),
         styled_button("🎲 Different Reactions", callback_data="campaign_action_different_react")],
        [styled_button("👁️ View Only", callback_data="private_channel_view"),
         styled_button("🗳️ Vote Only", callback_data="campaign_action_vote")],
        [styled_button("❤️‍🔥 React + Vote", callback_data="campaign_action_reactvote"),
         styled_button("❤️ React + View", callback_data="campaign_action_reactview")],
        [styled_button("🗳️ Vote + View", callback_data="campaign_action_voteview"),
         styled_button("❤️‍🔥🗳️👁️ All Three", callback_data="campaign_action_reactvoteview")],
        [styled_button("💬 Bulk DM", callback_data="campaign_action_dm"),
         styled_button("🎙️ Voice Chat (VC)", callback_data="campaign_action_vc")],
        [styled_button("⚡ Group Spam", callback_data="campaign_action_group_spam")],
        [styled_button("🎨 Multi-Reactions (Emoji)", callback_data="campaign_normal_emoji"),
         styled_button("✨ Premium Emoji", callback_data="campaign_premium_mode")],
        [styled_button("🔙 Main Menu", callback_data="main")],
    ]

    await update.callback_query.edit_message_text(
        f"🛍️ SHOPPING\n\n📊 Active Accounts: {len(accounts)}\n✅ Select action:",
        reply_markup={"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]})

async def new_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    accs = get_accessible_accounts(user_id)

    if not accs:
        await update.callback_query.edit_message_text(
            "❌ No accounts available!\n\nPlease add accounts first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Add Account", callback_data="add_account")]]))
        return

    live_accs = await get_live_accounts_batch(accs)

    if not live_accs:
        await update.callback_query.edit_message_text("❌ No active accounts found!")
        return

    await show_shopping_menu(update, context, live_accs)

async def campaign_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    user_id = update.callback_query.from_user.id
    accounts = context.user_data.get('campaign_accounts', [])

    if not accounts:
        accs = get_accessible_accounts(user_id)
        if accs:
            accounts = await get_live_accounts_batch(accs)
            context.user_data['campaign_accounts'] = accounts

    if not accounts:
        keyboard = [[styled_button("🔙 Main Menu", callback_data="main")]]
        reply_markup = {"inline_keyboard": [[btn_to_dict(btn) for btn in row] for row in keyboard]}
        await update.callback_query.edit_message_text("❌ No accounts available!", reply_markup=reply_markup)
        return

    # If action requires reaction type selection, show that first
    if action in REACTION_ACTIONS:
        context.user_data['pending_reaction_action'] = action
        await show_reaction_type_selection(update, context)
        return

    # For non-reaction actions, proceed as before
    context.user_data['campaign_action'] = action
    WAITING_FOR[user_id] = 'campaign_link'

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    action_msgs = {
        'join': 'Send channel link to join:\nExample: t.me/username',
        'different_react': 'Send post link for random reactions:\nExample: t.me/username/123',
        'vote': 'Send post link to vote:\nExample: t.me/username/123',
        'dm': 'Send username or ID to DM:\nExample: @username',
        'vc': 'Send voice chat link:\nExample: t.me/username',
        'group_spam': 'Send group link to spam:\nExample: t.me/groupname',
        'view': 'Send post link for view:\nExample: t.me/username/123 or t.me/c/123456789/123',
    }

    msg = action_msgs.get(action, 'Send the link:')

    await update.callback_query.edit_message_text(
        f"📢 {action.upper()}\n\nThis action will be performed on {len(accounts)} accounts\n\n{msg}",
        reply_markup=reply_markup)

# ========== PREMIUM EMOJI FLOW (Auto-Detect) ==========
async def campaign_premium_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    accounts = context.user_data.get('campaign_accounts', [])
    if not accounts:
        accs = get_accessible_accounts(user_id)
        if accs:
            accounts = await get_live_accounts_batch(accs)
            context.user_data['campaign_accounts'] = accounts
    if not accounts:
        keyboard = [[styled_button("🔙 Main Menu", callback_data="main")]]
        reply_markup = {"inline_keyboard": [[btn_to_dict(btn) for btn in row] for row in keyboard]}
        await update.callback_query.edit_message_text("❌ No accounts!", reply_markup=reply_markup)
        return

    context.user_data['campaign_action'] = 'premium_emoji'
    WAITING_FOR[user_id] = 'premium_link'

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        "✨ PREMIUM EMOJI (Auto-Detect)\n\n"
        "Send the post link where you will manually react with the premium emoji.\n\n"
        "Example: t.me/username/123 or t.me/c/123456789/123",
        reply_markup=reply_markup)

async def handle_premium_link(update: Update, context: ContextTypes.DEFAULT_TYPE, link: str):
    user_id = update.effective_user.id
    context.user_data['premium_link'] = link
    WAITING_FOR[user_id] = 'premium_wait_react'

    keyboard = [
        [InlineKeyboardButton("✅ I have reacted", callback_data="premium_reacted")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "✅ Link received!\n\n"
        "Now please open that post in Telegram and manually react with your desired premium emoji using your own account.\n\n"
        "After you have reacted, click the button below.",
        reply_markup=reply_markup)

async def premium_reacted_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    link = context.user_data.get('premium_link')
    if not link:
        await query.edit_message_text("❌ Link not found. Please start over.")
        return

    accounts = context.user_data.get('campaign_accounts', [])
    if not accounts:
        await query.edit_message_text("❌ No accounts available.")
        return

    # Pick the first live account
    client = None
    for acc in accounts:
        client = await get_client_for_account(acc)
        if client:
            break

    if not client:
        await query.edit_message_text("❌ No working account to detect reactions. Please ensure you have at least one live account.")
        return

    await query.edit_message_text("🔍 Detecting premium reaction on the post...")

    try:
        custom_emoji_id = await detect_premium_reaction(client, link)
        if custom_emoji_id:
            context.user_data['detected_premium_id'] = custom_emoji_id
            await query.edit_message_text(
                f"✅ Premium reaction detected! Emoji ID: {custom_emoji_id}\n\n"
                "Now proceeding to campaign setup.",
                reply_markup=None)
            await proceed_premium_campaign(update, context, user_id, link, custom_emoji_id)
        else:
            await query.edit_message_text(
                "❌ No premium (custom) reaction found on the post.\n\n"
                "Please make sure you have manually reacted with a premium emoji using your own account, then click 'I have reacted' again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="premium_reacted")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
                ]))
    except Exception as e:
        await query.edit_message_text(f"❌ Error detecting reaction: {str(e)[:100]}")

async def proceed_premium_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, link: str, custom_emoji_id: str):
    accounts = context.user_data.get('campaign_accounts', [])
    if not accounts:
        await update.message.reply_text("❌ No accounts!")
        return

    extra = {'premium': {'id': custom_emoji_id, 'name': 'Detected'}}
    PENDING_CAMPAIGN[user_id] = {
        'action': 'premium_emoji',
        'link': link,
        'accounts': accounts,
        'extra': extra
    }

    WAITING_FOR[user_id] = 'account_count'

    keyboard = [
        [InlineKeyboardButton(f"📊 All ({len(accounts)})", callback_data=f"use_all_{len(accounts)}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"How many accounts?\n\nYou have {len(accounts)} active account(s).\n\nSend number or tap All:",
            reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            f"How many accounts?\n\nYou have {len(accounts)} active account(s).\n\nSend number or tap All:",
            reply_markup=reply_markup)

# ========== NORMAL EMOJI MODE (shopping multi-reactions) ==========
async def campaign_normal_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Coming from Shopping, so no original_action; we'll set it later
    context.user_data['original_action'] = None
    await show_emoji_selection(update, context)

# ========== HANDLE CAMPAIGN LINK ==========
async def handle_campaign_link(update: Update, context: ContextTypes.DEFAULT_TYPE, link: str):
    user_id = update.effective_user.id
    action = context.user_data.get('campaign_action')
    accounts = context.user_data.get('campaign_accounts', [])
    reaction_type = context.user_data.get('reaction_type', 'normal')

    if not action or not accounts:
        await update.message.reply_text("❌ Please start campaign again.")
        WAITING_FOR.pop(user_id, None)
        return

    extra_data = {}
    selected_emojis = context.user_data.get('selected_emojis')
    if selected_emojis:
        extra_data['emojis'] = selected_emojis

    link_parts = link.strip().split()
    target_link = link_parts[0] if link_parts else link.strip()
    if len(link_parts) > 1 and link_parts[1].isdigit():
        opt_num = int(link_parts[1])
        extra_data['option_index'] = max(0, opt_num - 1)

    # If this is a reaction action and premium, we need to detect premium emoji first
    if action in REACTION_ACTIONS and reaction_type == 'premium':
        # Store link and ask user to react manually, then detect
        context.user_data['premium_link'] = target_link
        PENDING_CAMPAIGN[user_id] = {
            'action': action,
            'link': target_link,
            'accounts': accounts,
            'extra': extra_data,
            'reaction_type': 'premium',
            'pending_premium_detection': True
        }
        WAITING_FOR[user_id] = 'premium_detect_react'
        keyboard = [
            [InlineKeyboardButton("✅ I have reacted", callback_data="premium_reacted_for_action")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "✨ Premium reaction selected.\n\n"
            "Please open that post in Telegram and manually react with your desired premium emoji using your own account.\n\n"
            "After you have reacted, click the button below to detect the emoji.",
            reply_markup=reply_markup
        )
        return

    # Normal flow: store campaign and proceed to account count
    PENDING_CAMPAIGN[user_id] = {
        'action': action,
        'link': target_link,
        'accounts': accounts,
        'extra': extra_data,
        'reaction_type': reaction_type
    }

    if action == 'group_spam' or action == 'dm':
        WAITING_FOR[user_id] = 'spam_message'
        await update.message.reply_text("📝 Now send the message to spam/send:")
        return

    WAITING_FOR[user_id] = 'account_count'

    keyboard = [
        [InlineKeyboardButton(f"📊 All ({len(accounts)})", callback_data=f"use_all_{len(accounts)}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"How many accounts?\n\nYou have {len(accounts)} active account(s).\n\nSend number or tap All:",
        reply_markup=reply_markup)

async def premium_reacted_for_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    campaign = PENDING_CAMPAIGN.get(user_id)
    if not campaign:
        await query.edit_message_text("❌ Campaign data lost.")
        return

    link = campaign.get('link')
    accounts = campaign.get('accounts', [])
    if not link or not accounts:
        await query.edit_message_text("❌ Missing link or accounts.")
        return

    # Detect premium reaction using first live account
    client = None
    for acc in accounts:
        client = await get_client_for_account(acc)
        if client:
            break

    if not client:
        await query.edit_message_text("❌ No working account to detect reactions.")
        return

    await query.edit_message_text("🔍 Detecting premium reaction on the post...")

    try:
        custom_emoji_id = await detect_premium_reaction(client, link)
        if custom_emoji_id:
            # Store the detected ID in campaign extra
            campaign['extra']['premium'] = {'id': custom_emoji_id, 'name': 'Detected'}
            campaign['reaction_type'] = 'premium'
            PENDING_CAMPAIGN[user_id] = campaign
            WAITING_FOR[user_id] = 'account_count'
            keyboard = [
                [InlineKeyboardButton(f"📊 All ({len(accounts)})", callback_data=f"use_all_{len(accounts)}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"✅ Premium reaction detected! Emoji ID: {custom_emoji_id}\n\n"
                f"How many accounts?\n\nYou have {len(accounts)} active account(s).\n\nSend number or tap All:",
                reply_markup=reply_markup)
        else:
            await query.edit_message_text(
                "❌ No premium (custom) reaction found on the post.\n\n"
                "Please make sure you have manually reacted with a premium emoji using your own account, then click the button again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="premium_reacted_for_action")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
                ]))
    except Exception as e:
        await query.edit_message_text(f"❌ Error detecting reaction: {str(e)[:100]}")

async def handle_spam_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg: str):
    user_id = update.effective_user.id
    campaign = PENDING_CAMPAIGN.get(user_id)

    if not campaign:
        await update.message.reply_text("❌ Campaign data lost!")
        WAITING_FOR.pop(user_id, None)
        return

    PENDING_SPAM_MSG[user_id] = msg
    WAITING_FOR[user_id] = 'account_count'

    accounts = campaign.get('accounts', [])
    keyboard = [
        [InlineKeyboardButton(f"📊 All ({len(accounts)})", callback_data=f"use_all_{len(accounts)}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"How many accounts?\n\nYou have {len(accounts)} active account(s).\n\nSend number or tap All:",
        reply_markup=reply_markup)

async def use_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    count_str = query.data.replace("use_all_", "")
    count = int(count_str)

    SELECTED_ACCOUNT_COUNT[user_id] = count
    await show_campaign_summary(update, context, user_id)

async def handle_account_count(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    accounts = context.user_data.get('campaign_accounts', [])

    try:
        if text.lower() == 'all':
            count = len(accounts)
        else:
            count = int(text)

        if count < 1 or count > len(accounts):
            await update.message.reply_text(f"❌ Send number between 1 and {len(accounts)}")
            return

        SELECTED_ACCOUNT_COUNT[user_id] = count
        WAITING_FOR.pop(user_id, None)
        await show_campaign_summary(update, context, user_id)
    except ValueError:
        await update.message.reply_text("❌ Send valid number or 'all'")

async def show_campaign_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    campaign = PENDING_CAMPAIGN.get(user_id)
    if not campaign:
        await update.message.reply_text("❌ Campaign data lost!")
        return

    action = campaign['action']
    link = campaign['link']
    accounts = campaign.get('accounts', [])
    use_count = SELECTED_ACCOUNT_COUNT.get(user_id, len(accounts))
    extra = campaign.get('extra', {})
    reaction_type = campaign.get('reaction_type', 'normal')

    action_names = {
        'join': '📢 Join Channel',
        'react': '❤️ React Only',
        'different_react': '🎲 Different Reactions',
        'view': '👁️ View Only',
        'vote': '🗳️ Vote Only',
        'reactvote': '❤️‍🔥 React + Vote',
        'reactview': '❤️ React + View',
        'voteview': '🗳️ Vote + View',
        'reactvoteview': '❤️‍🔥🗳️👁️ All Three',
        'dm': '💬 Bulk DM',
        'vc': '🎙️ Voice Chat (VC)',
        'group_spam': '⚡ Group Spam',
        'multi_react': '🎨 Multiple Reactions',
        'premium_emoji': '✨ Premium Emoji'
    }

    summary = f"""📢 CAMPAIGN SUMMARY
━━━━━━━━━━━━━━━━━━━━━━

Action: {action_names.get(action, action)}
Target: {link}
Reaction Type: {reaction_type.capitalize()}

Accounts: {use_count} will run"""

    if action == 'multi_react' or (action in REACTION_ACTIONS and reaction_type == 'normal'):
        emojis = extra.get('emojis', [])
        if emojis:
            summary += f"\nEmojis: {', '.join(emojis)}"
    elif action == 'premium_emoji' or reaction_type == 'premium':
        prem = extra.get('premium', {})
        summary += f"\nPremium Emoji ID: {prem.get('id', 'Unknown')}"

    summary += "\n\nTap RUN to start"""

    keyboard = [
        [InlineKeyboardButton("🚀 Run Campaign", callback_data="run_campaign")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(summary, reply_markup=reply_markup)
    else:
        await update.message.reply_text(summary, reply_markup=reply_markup)

async def execute_account_campaign_action(acc, action, link, extra, use_premium, premium_id, spam_msg, i):
    """Executes a single campaign action with full FloodWait and session error protection."""
    phone = acc.get('phone')
    if is_account_on_cooldown(phone):
        return False, "Account on Flood cooldown"

    client = await get_client_for_account(acc)
    if not client:
        return False, "Connection failed"

    try:
        if action == 'join':
            return await join_channel_func(client, link)

        elif action == 'dm':
            target = link.strip()
            msg_to_send = spam_msg if spam_msg else "Hello!"
            if target.isdigit():
                entity = await client.get_entity(int(target))
            else:
                entity = await client.get_entity(target)
            await client.send_message(entity, msg_to_send)
            return True, "DM sent"

        elif action == 'vc':
            return await join_voice_chat_func(client, link)

        elif action == 'group_spam':
            return await group_spam_message(client, link, spam_msg)

        elif action == 'react':
            if use_premium:
                return await send_premium_reaction_func(client, link, premium_id)
            else:
                emojis = extra.get('emojis', [])
                selected_emoji = emojis[i % len(emojis)] if emojis else '🔥'
                return await send_reaction_func(client, link, selected_emoji)

        elif action == 'different_react':
            return await add_different_reactions(client, link)

        elif action == 'multi_react':
            if use_premium:
                return await send_premium_reaction_func(client, link, premium_id)
            else:
                emojis = extra.get('emojis', [])
                if not emojis:
                    return False, "No emojis"
                selected_emoji = emojis[i % len(emojis)]
                return await send_reaction_func(client, link, selected_emoji)

        elif action == 'premium_emoji':
            return await send_premium_reaction_func(client, link, premium_id)

        elif action == 'view':
            peer, msg_id = await resolve_peer_and_msg(client, link)
            if not peer or not msg_id:
                return False, "Invalid link format"
            res = await client(GetMessagesViewsRequest(peer=peer, id=[msg_id], increment=True))
            return bool(res), "View added" if res else "Failed to add view"

        elif action == 'vote':
            opt_idx = extra.get('option_index', 0) if isinstance(extra, dict) else 0
            return await vote_poll_func(client, link, option_index=opt_idx)

        else:
            peer, msg_id = await resolve_peer_and_msg(client, link)
            if not peer or not msg_id:
                return False, "Invalid link"

            if action in ['reactvote', 'reactview', 'reactvoteview']:
                if use_premium:
                    react_success, react_msg = await send_premium_reaction_func(client, link, premium_id)
                else:
                    emojis = extra.get('emojis', [])
                    selected_emoji = emojis[i % len(emojis)] if emojis else '🔥'
                    react_success, react_msg = await send_reaction_func(client, link, selected_emoji)
                if not react_success:
                    return False, react_msg

                await asyncio.sleep(0.25)  # Safe human-like micro-pause

            opt_idx = extra.get('option_index', 0) if isinstance(extra, dict) else 0

            if action == 'reactvote':
                return await vote_poll_func(client, link, option_index=opt_idx)

            elif action == 'reactview':
                try:
                    await client(GetMessagesViewsRequest(peer=peer, id=[msg_id], increment=True))
                    return True, "Reacted and viewed"
                except Exception as e:
                    return False, str(e)[:40]

            elif action == 'voteview':
                v_succ, v_msg = await vote_poll_func(client, link, option_index=opt_idx)
                if v_succ:
                    await asyncio.sleep(0.25)  # Safe micro-pause
                    try:
                        await client(GetMessagesViewsRequest(peer=peer, id=[msg_id], increment=True))
                    except Exception:
                        pass
                    return True, "Voted and viewed"
                return False, v_msg

            elif action == 'reactvoteview':
                v_succ, v_msg = await vote_poll_func(client, link, option_index=opt_idx)
                if v_succ:
                    await asyncio.sleep(0.25)  # Safe micro-pause
                    try:
                        await client(GetMessagesViewsRequest(peer=peer, id=[msg_id], increment=True))
                    except Exception:
                        pass
                    return True, "Reacted, voted and viewed"
                return False, v_msg

        return False, "Unknown action"

    except FloodWaitError as e:
        if phone:
            set_account_cooldown(phone, e.seconds)
        return False, f"Flood wait {e.seconds}s"
    except Exception as e:
        err_str = str(e).lower()
        if "flood" in err_str:
            if phone:
                set_account_cooldown(phone, 60)
            return False, "Flood wait"
        return False, str(e)[:40]

# ========== RUN CAMPAIGN ==========
async def run_campaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    campaign = PENDING_CAMPAIGN.get(user_id)
    spam_msg = PENDING_SPAM_MSG.get(user_id)

    if not campaign:
        await update.callback_query.edit_message_text("❌ Campaign data lost!")
        return

    action = campaign['action']
    link = campaign['link']
    accounts = campaign.get('accounts', [])
    use_count = SELECTED_ACCOUNT_COUNT.get(user_id, len(accounts))
    extra = campaign.get('extra', {})
    reaction_type = campaign.get('reaction_type', 'normal')

    # Strict deduplication safeguard: ensure 1 account is NEVER duplicated in a campaign
    seen_exec_keys = set()
    deduped_accounts = []
    for a in accounts:
        if is_account_frozen(a):
            continue
        s_k = str(a.get('session_string') or '').strip()
        p_k = str(a.get('phone') or '').strip().lstrip('+')
        if s_k and s_k in seen_exec_keys:
            continue
        if p_k and p_k.isdigit() and p_k in seen_exec_keys:
            continue
        if s_k:
            seen_exec_keys.add(s_k)
        if p_k and p_k.isdigit():
            seen_exec_keys.add(p_k)
        deduped_accounts.append(a)

    use_count = min(SELECTED_ACCOUNT_COUNT.get(user_id, len(deduped_accounts)), len(deduped_accounts))
    accounts_to_use = deduped_accounts[:use_count]

    if not accounts_to_use:
        await update.callback_query.edit_message_text("❌ No active accounts!")
        return

    status_msg = await update.callback_query.edit_message_text(
        f"🚀 CAMPAIGN RUNNING...\n\nAction: {action}\nAccounts: {len(accounts_to_use)}\n\nProcessing...",
        reply_markup=None
    )

    results = {'success': 0, 'failed': 0, 'errors': []}

    # Determine reaction emoji function
    use_premium = (reaction_type == 'premium' and action in REACTION_ACTIONS) or action == 'premium_emoji'
    premium_id = None
    if use_premium:
        if action == 'premium_emoji':
            premium_id = extra.get('premium', {}).get('id')
        else:
            premium_id = extra.get('premium', {}).get('id')
        if not premium_id:
            results['failed'] += len(accounts_to_use)
            await status_msg.edit_text("❌ Premium emoji ID missing. Campaign aborted.")
            return

    # Filter and prioritize accounts that are not currently under FloodWait cooldown
    non_cooldown = [a for a in accounts_to_use if not is_account_on_cooldown(a.get('phone'))]
    cooldown_accs = [a for a in accounts_to_use if is_account_on_cooldown(a.get('phone'))]
    target_accounts = (non_cooldown + cooldown_accs)[:use_count]

    concurrency = min(3, max(1, len(target_accounts)))
    queue = asyncio.Queue()
    for idx, acc in enumerate(target_accounts):
        await queue.put((idx, acc))

    last_edit = [time.time()]
    processed_count = [0]
    total_accs = len(target_accounts)
    user_delay = load_settings(user_id).get('delay', DEFAULT_DELAY)

    async def worker():
        while not queue.empty():
            try:
                i, acc = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            phone = acc.get('phone')
            if is_account_on_cooldown(phone):
                results['failed'] += 1
                results['errors'].append("Account on Flood cooldown")
                queue.task_done()
                processed_count[0] += 1
                continue

            try:
                success, msg = await execute_account_campaign_action(
                    acc, action, link, extra, use_premium, premium_id, spam_msg, i
                )
                if success:
                    results['success'] += 1
                else:
                    results['failed'] += 1
                    if msg:
                        results['errors'].append(msg)
            except FloodWaitError as e:
                set_account_cooldown(phone, e.seconds)
                results['failed'] += 1
                results['errors'].append(f"Flood wait {e.seconds}s")
            except Exception as e:
                err_str = str(e)
                if "frozen" in err_str.lower():
                    if phone:
                        mark_account_frozen(phone)
                    err_msg = "Account Frozen by Telegram"
                elif "flood" in err_str.lower():
                    err_msg = "Flood wait"
                else:
                    err_msg = err_str[:40]
                results['failed'] += 1
                results['errors'].append(err_msg)
            finally:
                queue.task_done()
                processed_count[0] += 1

            now = time.time()
            if (now - last_edit[0] >= 1.2) or (processed_count[0] == total_accs):
                last_edit[0] = now
                try:
                    await status_msg.edit_text(
                        f"🚀 CAMPAIGN RUNNING...\n\n"
                        f"Progress: {processed_count[0]}/{total_accs}\n"
                        f"✅ Success: {results['success']}\n"
                        f"❌ Failed: {results['failed']}"
                    )
                except Exception:
                    pass

            jitter = random.uniform(0.05, 0.15)
            await asyncio.sleep(user_delay + jitter)

    workers = [asyncio.create_task(worker()) for _ in range(concurrency)]
    await asyncio.gather(*workers)

    action_names = {
        'join': 'Join Channel',
        'react': 'React Only',
        'different_react': 'Different Reactions',
        'view': 'View Only',
        'vote': 'Vote Only',
        'reactvote': 'React + Vote',
        'reactview': 'React + View',
        'voteview': 'Vote + View',
        'reactvoteview': 'React+Vote+View',
        'dm': 'Bulk DM',
        'vc': 'Voice Chat',
        'group_spam': 'Group Spam',
        'multi_react': 'Multiple Reactions',
        'premium_emoji': 'Premium Emoji'
    }

    campaign_data = {
        'action': action_names.get(action, action),
        'target': link,
        'result': f"Success {results['success']} / Failed {results['failed']}",
        'status': 'completed',
        'timestamp': str(datetime.now()),
        'accounts_used': len(accounts_to_use),
        'success_count': results['success'],
        'failed_count': results['failed']
    }
    save_campaign(user_id, campaign_data)

    extra_info_str = None
    if use_premium:
        extra_info_str = f"Premium Emoji ID: {premium_id}"
    elif action == 'multi_react':
        emojis = extra.get('emojis', [])
        extra_info_str = f"Reactions: {' '.join(emojis)}" if emojis else None
    elif action in ('group_spam', 'dm'):
        extra_info_str = f"Message: {spam_msg[:50]}..." if spam_msg else None
    elif action in ('vote', 'reactvote', 'voteview', 'reactvoteview'):
        opt_idx = extra.get('option_index', 0)
        extra_info_str = f"Poll Option: {opt_idx + 1}"

    await log_campaign_to_admin_channel(
        user_id=user_id,
        action=action_names.get(action, action),
        target=link,
        accounts_used=len(accounts_to_use),
        success_count=results['success'],
        failed_count=results['failed'],
        errors=results['errors'],
        extra_info=extra_info_str,
        bot=context.bot
    )

    errors_text = ""
    if results['errors']:
        errors_list = results['errors'][:5]
        errors_text = "\n\n❌ Errors:\n" + "\n".join(errors_list)

    success_rate = int((results['success'] * 100) / len(accounts_to_use)) if len(accounts_to_use) > 0 else 0

    await status_msg.edit_text(
        f"✅ CAMPAIGN FINISHED!\n\n"
        f"Total: {len(accounts_to_use)}\n"
        f"✅ Success: {results['success']}\n"
        f"❌ Failed: {results['failed']}\n"
        f"📊 Rate: {success_rate}%{errors_text}"
    )

    PENDING_CAMPAIGN.pop(user_id, None)
    SELECTED_ACCOUNT_COUNT.pop(user_id, None)
    PENDING_SPAM_MSG.pop(user_id, None)
    SELECTED_EMOJIS.pop(user_id, None)
    SELECTED_PREMIUM.pop(user_id, None)
    context.user_data.pop('pending_reaction_action', None)
    context.user_data.pop('reaction_type', None)
    context.user_data.pop('original_action', None)
    context.user_data.pop('selected_emojis', None)

# ========== SCHEDULED ==========
async def scheduled_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    scheduled_list = load_scheduled(user_id)

    if not scheduled_list:
        keyboard = [
            [styled_button("📅 Schedule New", callback_data="schedule_new")],
            [styled_button("🔙 Main Menu", callback_data="main")],
        ]
        reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
        await update.callback_query.edit_message_text(
            "⏰ SCHEDULED\n\nNo scheduled campaigns!",
            reply_markup=reply_markup)
    else:
        text = "⏰ YOUR SCHEDULES\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
        for s in scheduled_list:
            schedule_id, action, target, schedule_time, account_count, spam_msg = s
            text += f"ID: {schedule_id}\nAction: {action}\nTarget: {target[:40]}\nTime: {schedule_time}\nAccounts: {account_count}\n━━━━━━━━━━━━━━━━━━━━━━\n"

        keyboard = [
            [styled_button("📅 Schedule New", callback_data="schedule_new")],
            [styled_button("❌ Cancel Schedule", callback_data="schedule_cancel")],
            [styled_button("🔙 Main Menu", callback_data="main")],
        ]
        reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
        await update.callback_query.edit_message_text(text[:4000], reply_markup=reply_markup)

async def schedule_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    accs = get_accessible_accounts(user_id)

    if not accs:
        await update.callback_query.edit_message_text("❌ No accounts!")
        return

    live_accs = await get_live_accounts_batch(accs)

    if not live_accs:
        await update.callback_query.edit_message_text("❌ No active accounts!")
        return

    context.user_data['campaign_accounts'] = live_accs
    WAITING_FOR[user_id] = 'schedule_action'

    keyboard = [
        [styled_button("📢 Join Channel", callback_data="schedule_action_join"),
         styled_button("❤️ React", callback_data="schedule_action_react")],
        [styled_button("🎲 Different Reactions", callback_data="schedule_action_different_react"),
         styled_button("👁️ View Only", callback_data="schedule_action_view")],
        [styled_button("🗳️ Vote Only", callback_data="schedule_action_vote"),
         styled_button("🎙️ Voice Chat (VC)", callback_data="schedule_action_vc")],
        [styled_button("💬 Bulk DM", callback_data="schedule_action_dm")],
        [styled_button("❌ Cancel", callback_data="cancel_action")],
    ]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "📅 SCHEDULE\n\nSelect action:",
        reply_markup=reply_markup)

async def schedule_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str):
    user_id = update.callback_query.from_user.id
    context.user_data['schedule_action'] = action
    WAITING_FOR[user_id] = 'schedule_link'

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(
        f"🔗 Send the link for {action}:",
        reply_markup=reply_markup)

async def handle_schedule_link(update: Update, context: ContextTypes.DEFAULT_TYPE, link: str):
    user_id = update.effective_user.id
    action = context.user_data.get('schedule_action')

    if not action:
        await update.message.reply_text("❌ Start again!")
        WAITING_FOR.pop(user_id, None)
        return

    PENDING_SCHEDULE[user_id] = {'action': action, 'link': link}

    if action in ('dm', 'group_spam'):
        WAITING_FOR[user_id] = 'schedule_spam_message'
        await update.message.reply_text("📝 Send message to send/spam:")
    else:
        WAITING_FOR[user_id] = 'schedule_time'
        await update.message.reply_text(
            "⏰ Schedule Time\n\nFormat: YYYY-MM-DD HH:MM:SS\nExample: 2026-06-05 14:30:00\n\nTimezone: UTC")

async def handle_schedule_spam_message(update: Update, context: ContextTypes.DEFAULT_TYPE, msg: str):
    user_id = update.effective_user.id
    schedule_data = PENDING_SCHEDULE.get(user_id)

    if not schedule_data:
        await update.message.reply_text("❌ Data lost!")
        WAITING_FOR.pop(user_id, None)
        return

    PENDING_SCHEDULE[user_id]['spam_message'] = msg
    WAITING_FOR[user_id] = 'schedule_time'

    await update.message.reply_text(
        "⏰ Schedule Time\n\nFormat: YYYY-MM-DD HH:MM:SS\nExample: 2026-06-05 14:30:00")

async def handle_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE, time_str: str):
    user_id = update.effective_user.id
    schedule_data = PENDING_SCHEDULE.get(user_id)

    if not schedule_data:
        await update.message.reply_text("❌ Data lost!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        scheduled_time = datetime.strptime(time_str.strip(), "%Y-%m-%d %H:%M:%S")
        if scheduled_time <= datetime.now():
            await update.message.reply_text("❌ Send future date/time!")
            return

        PENDING_SCHEDULE[user_id]['time_str'] = time_str
        WAITING_FOR[user_id] = 'schedule_account_count'

        accounts = context.user_data.get('campaign_accounts', [])
        await update.message.reply_text(
            f"🔢 How many accounts? (1-{len(accounts)})")

    except ValueError:
        await update.message.reply_text("❌ Invalid format! Use: YYYY-MM-DD HH:MM:SS")

async def handle_schedule_account_count(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    schedule_data = PENDING_SCHEDULE.get(user_id)

    if not schedule_data:
        await update.message.reply_text("❌ Data lost!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        count = int(text.strip())
        accounts = context.user_data.get('campaign_accounts', [])

        if count < 1 or count > len(accounts):
            await update.message.reply_text(f"❌ Send number between 1 and {len(accounts)}")
            return

        spam_message = schedule_data.get('spam_message', '')
        save_scheduled(user_id, schedule_data['action'], schedule_data['link'],
                      schedule_data['time_str'], count, spam_message)

        user_mention = format_user_mention(user_id, update.effective_user.first_name, update.effective_user.username)
        asyncio.create_task(send_admin_log(
            f"📅 <b>NEW CAMPAIGN SCHEDULED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Scheduled By:</b> {user_mention}\n"
            f"🎯 <b>Action:</b> <code>{html.escape(schedule_data['action'])}</code>\n"
            f"🔗 <b>Target:</b> <code>{html.escape(schedule_data['link'])}</code>\n"
            f"👥 <b>Accounts:</b> <code>{count}</code>\n"
            f"⏰ <b>Execution Time:</b> <code>{schedule_data['time_str']} (UTC)</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━",
            bot=context.bot
        ))

        WAITING_FOR.pop(user_id, None)
        PENDING_SCHEDULE.pop(user_id, None)

        await update.message.reply_text(
            f"✅ Scheduled!\n\n"
            f"Action: {schedule_data['action']}\n"
            f"Time: {schedule_data['time_str']}\n"
            f"Accounts: {count}\n\nWill run at scheduled time!")

    except ValueError:
        await update.message.reply_text("❌ Send valid number!")

async def schedule_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    scheduled_list = load_scheduled(user_id)

    if not scheduled_list:
        await update.callback_query.edit_message_text("❌ No schedules!")
        return

    WAITING_FOR[user_id] = 'cancel_schedule_id'

    text = "❌ Cancel Schedule\n\nSend Schedule ID:\n\n"
    for s in scheduled_list:
        text += f"ID: {s[0]} - {s[1]}\n"

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def handle_cancel_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    try:
        schedule_id = int(text.strip())
        delete_scheduled(schedule_id)
        WAITING_FOR.pop(user_id, None)
        await update.message.reply_text(f"✅ Schedule {schedule_id} cancelled!")
    except Exception:
        await update.message.reply_text("❌ Invalid ID!")
        WAITING_FOR.pop(user_id, None)

# ========== CLOUD MONGODB SESSIONS SYNC & SYSTEM STATS ==========
def sync_cloud_accounts():
    """
    Scans ALL accounts in MongoDB Atlas cloud storage.
    Strictly deduplicates by session_string (cryptographic auth key), phone number, and Telegram user_id.
    Merges best available metadata (real phone, real UID, username).
    Synchronizes the unified cloud accounts pool to Owner and Admin profiles.
    Purges any duplicate records across all users in MongoDB.
    Returns: total_unique, live_count, frozen_count, purged_duplicates
    """
    if MONGO_DB is None:
        return 0, 0, 0, 0

    all_user_docs = list(MONGO_DB.users.find({}, {"user_id": 1, "accounts": 1}))
    session_map = {}
    for u in all_user_docs:
        for a in u.get("accounts", []):
            s = a.get("session_string")
            if not s:
                continue
            if s not in session_map:
                session_map[s] = dict(a)
            else:
                cur = session_map[s]
                p_cur = str(cur.get("phone") or "")
                p_new = str(a.get("phone") or "")
                if ("user_" in p_cur or not p_cur) and p_new and "user_" not in p_new:
                    cur["phone"] = p_new
                if not cur.get("user_id") and a.get("user_id"):
                    cur["user_id"] = a.get("user_id")
                if (cur.get("username") in (None, "", "Synced", "No username")) and a.get("username") and a.get("username") not in ("Synced", "No username"):
                    cur["username"] = a.get("username")
                if (not cur.get("first_name") or "user_" in str(cur.get("first_name"))) and a.get("first_name") and "user_" not in str(a.get("first_name")):
                    cur["first_name"] = a.get("first_name")

    master_list = list(session_map.values())

    # Update Owner and Admins with deduplicated master list
    admin_list = list(dict.fromkeys([OWNER_ID] + list(ADMIN_IDS)))
    for aid in admin_list:
        save_accounts(aid, master_list)

    # Clean individual users
    purged_count = 0
    for u in all_user_docs:
        uid = u.get("user_id")
        if uid in admin_list:
            continue
        raw_accs = u.get("accounts", [])
        if not raw_accs:
            continue
        seen_s = set()
        seen_p = set()
        cleaned = []
        for a in raw_accs:
            s = a.get("session_string")
            p = str(a.get("phone") or "").strip().lstrip("+")
            if not s or s in seen_s:
                purged_count += 1
                continue
            if p and p.isdigit() and p in seen_p:
                purged_count += 1
                continue
            seen_s.add(s)
            if p and p.isdigit():
                seen_p.add(p)
            cleaned.append(a)
        if len(cleaned) != len(raw_accs):
            save_accounts(uid, cleaned)

    return len(master_list), len(master_list) - len(FROZEN_ACCOUNTS), len(FROZEN_ACCOUNTS), purged_count

def sync_disk_sessions(target_user_id=None):
    """Syncs cloud accounts across MongoDB (zero local disk dependency)."""
    total, live, frozen, purged = sync_cloud_accounts()
    return total, 0, purged

def get_system_stats():
    """Gathers system, database, and accounts statistics for Admin Dashboard."""
    owner_accs = load_owner_accounts()
    total_pool_accs = len(owner_accs)

    cached_live = 0
    for a in owner_accs:
        p = a.get('phone', '')
        clean_p = str(p).strip().lstrip('+')
        if (clean_p and LIVE_CACHE.get(clean_p, (False, 0))[0]) or (p and LIVE_CACHE.get(p, (False, 0))[0]):
            if not is_account_frozen(a):
                cached_live += 1

    frozen_count = sum(1 for a in owner_accs if is_account_frozen(a))

    all_users_count = 0
    banned_count = 0
    admins_count = len(ADMIN_IDS)
    active_access_count = 0
    total_campaigns = 0
    pending_schedules = 0
    total_all_db_accs = 0

    if MONGO_DB is not None:
        try:
            all_users_count = MONGO_DB.users.count_documents({})
            banned_count = MONGO_DB.users.count_documents({"is_banned": 1})
            total_campaigns = MONGO_DB.campaigns.count_documents({})
            pending_schedules = MONGO_DB.scheduled.count_documents({"status": "pending"})

            now_iso = datetime.now().isoformat()
            active_access_count = MONGO_DB.users.count_documents({
                "access_expiry": {"$gt": now_iso}
            })

            total_all_db_accs = len(owner_accs)
        except Exception as e:
            logging.error(f"get_system_stats error: {e}")

    mem_free_mb = "N/A"
    mem_total_mb = "N/A"
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    meminfo[parts[0].strip()] = int(parts[1].strip().split()[0])
            if "MemAvailable" in meminfo and "MemTotal" in meminfo:
                mem_free_mb = str(meminfo["MemAvailable"] // 1024)
                mem_total_mb = str(meminfo["MemTotal"] // 1024)
    except Exception:
        pass

    import telethon
    telethon_ver = getattr(telethon, "__version__", "Unknown")

    return {
        "total_pool_accs": total_pool_accs,
        "cached_live": cached_live if cached_live > 0 else max(0, total_pool_accs - frozen_count),
        "frozen_count": frozen_count,
        "total_all_db_accs": total_all_db_accs,
        "all_users_count": all_users_count,
        "banned_count": banned_count,
        "admins_count": admins_count,
        "active_access_count": active_access_count,
        "total_campaigns": total_campaigns,
        "pending_schedules": pending_schedules,
        "mem_free_mb": mem_free_mb,
        "mem_total_mb": mem_total_mb,
        "telethon_ver": telethon_ver,
    }

# ========== ADMIN PANEL (COMPREHENSIVE DASHBOARD) ==========
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        if query:
            await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    stats = get_system_stats()

    maint = is_maintenance_mode()
    maint_btn_text = "🛠️ Maintenance: ON 🔴" if maint else "🛠️ Maintenance: OFF 🟢"

    curr_log_ch = get_log_channel_id()
    log_ch_btn = f"📢 Log Channel: {curr_log_ch}" if curr_log_ch else "📢 Log Channel: Not Set ⚪"

    user_name = (query.from_user.first_name if query else update.effective_user.first_name) or "Admin"
    role_badge = "👑 OWNER" if is_owner(user_id) else "👨‍💼 ADMINISTRATOR"

    maint_status = "🔴 ACTIVE (Admins Only)" if maint else "🟢 OFF (Public)"
    log_ch_status = f"<code>{curr_log_ch}</code> 🟢" if curr_log_ch else "<i>Not Set</i> ⚪"

    dashboard_text = (
        f"👑 <b>ADMIN DASHBOARD</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Admin:</b> {html.escape(user_name)} (<code>{user_id}</code>)\n"
        f"🏷️ <b>Role:</b> {role_badge}\n\n"
        f"📱 <b>ACCOUNTS OVERVIEW:</b>\n"
        f"• Total Pool Accounts: <b>{stats['total_pool_accs']}</b> 📱\n"
        f"• Verified Live (Active): <b>{stats['cached_live']}</b> 🟢\n"
        f"• Telegram Frozen: <b>{stats['frozen_count']}</b> ❄️ (Auto-excluded)\n"
        f"• Total Accounts in DB: <b>{stats['total_all_db_accs']}</b> ☁️ (MongoDB Cloud)\n\n"
        f"👥 <b>USERS & ACCESS:</b>\n"
        f"• Total Registered Users: <b>{stats['all_users_count']}</b> 👥\n"
        f"• Active Access Users: <b>{stats['active_access_count']}</b> 🎫\n"
        f"• Administrators: <b>{stats['admins_count']}</b> 👨‍💼\n"
        f"• Banned Users: <b>{stats['banned_count']}</b> 🚫\n\n"
        f"🚀 <b>CAMPAIGNS & TASKS:</b>\n"
        f"• Total Campaigns Completed: <b>{stats['total_campaigns']}</b> 📊\n"
        f"• Pending / Scheduled Tasks: <b>{stats['pending_schedules']}</b> ⏳\n\n"
        f"⚙️ <b>SYSTEM & BOT STATUS:</b>\n"
        f"• 🛠️ Maintenance Mode: {maint_status}\n"
        f"• 📢 Admin Log Channel: {log_ch_status}\n"
        f"• ⚡ Telethon: <code>{stats['telethon_ver']}</code> 🟢\n"
        f"• 🗄️ Database: MongoDB Atlas 🟢 Connected\n"
        f"• 💾 RAM: {stats['mem_free_mb']}MB Free / {stats['mem_total_mb']}MB Total\n\n"
        f"<i>Select an option below to manage:</i>"
    )

    keyboard = [
        [styled_button(f"📱 Total Accounts ({stats['total_pool_accs']})", callback_data="admin_all_accounts"),
         styled_button("☁️ Sync Cloud DB", callback_data="admin_sync_disk_sessions")],
        [styled_button("🔄 Refresh Dashboard", callback_data="admin_panel")],
        [styled_button(maint_btn_text, callback_data="toggle_maintenance")],
        [styled_button(log_ch_btn, callback_data="admin_log_channel_menu")],
        [styled_button("📢 Campaign (All)", callback_data="admin_campaign_all")],
        [styled_button("👤 Campaign (By User)", callback_data="admin_campaign_user")],
        [styled_button("📁 All Campaigns", callback_data="admin_all_campaigns")],
        [styled_button("🚫 Ban User", callback_data="admin_ban_user"),
         styled_button("✅ Unban User", callback_data="admin_unban_user")],
        [styled_button("👥 All Users", callback_data="admin_all_users")],
        [styled_button("👑 Grant Admin", callback_data="admin_grant_admin"),
         styled_button("🔽 Revoke Admin", callback_data="admin_revoke_admin")],
        [styled_button("📦 Export Sessions (.zip)", callback_data="admin_export_sessions"),
         styled_button("📥 Import Sessions (.zip)", callback_data="admin_import_sessions")],
        [styled_button("📤 Export DB", callback_data="admin_export_db"),
         styled_button("📥 Import DB", callback_data="admin_import_db")],
        [styled_button("📢 Broadcast", callback_data="admin_broadcast")],
        [styled_button("👥 Give Access", callback_data="give_access"),
         styled_button("❌ Remove Access", callback_data="remove_access")],
        [styled_button("🔙 Main Menu", callback_data="main")],
    ]

    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    if query:
        try:
            await query.edit_message_text(dashboard_text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            clean = dashboard_text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<i>", "").replace("</i>", "")
            await query.edit_message_text(clean, reply_markup=reply_markup)
    else:
        await update.message.reply_text(dashboard_text, reply_markup=reply_markup, parse_mode="HTML")

async def admin_all_accounts_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        if query:
            await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    owner_accs = load_owner_accounts()
    total_accs = len(owner_accs)
    def _is_acc_live(a):
        p = a.get('phone', '')
        cp = str(p).strip().lstrip('+')
        return (cp and LIVE_CACHE.get(cp, (False, 0))[0]) or (p and LIVE_CACHE.get(p, (False, 0))[0])
    cached_live = sum(1 for a in owner_accs if _is_acc_live(a))

    text = (
        f"📱 <b>ALL ACCOUNTS MANAGEMENT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 <b>Total Pool Accounts:</b> <code>{total_accs}</code> 📱\n"
        f"🟢 <b>Live Accounts:</b> <code>{cached_live if cached_live > 0 else max(0, total_accs - len(FROZEN_ACCOUNTS))}</code> 🟢\n"
        f"❄️ <b>Telegram Frozen:</b> <code>{len(FROZEN_ACCOUNTS)}</code> ❄️ (Auto-excluded)\n"
        f"☁️ <b>Storage:</b> <code>MongoDB Atlas Cloud (Zero disk dependency)</code>\n\n"
        f"💡 <i>Tip: Click '✅ View Live Accounts' to run a live connection check across all accounts and view details.</i>"
    )

    keyboard = [
        [styled_button("✅ View Live Accounts", callback_data="admin_view_live"),
         styled_button("❌ View Expired Accounts", callback_data="admin_view_expired")],
        [styled_button("☁️ Sync Cloud DB", callback_data="admin_sync_disk_sessions"),
         styled_button("➕ Add Account", callback_data="add_account")],
        [styled_button("📦 Export Sessions (.zip)", callback_data="admin_export_sessions"),
         styled_button("📥 Import Sessions (.zip)", callback_data="admin_import_sessions")],
        [styled_button("🔙 Admin Dashboard", callback_data="admin_panel")]
    ]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def admin_sync_disk_sessions_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        if query:
            await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    if query:
        await query.answer("☁️ Synchronizing & deduplicating MongoDB Cloud accounts...", show_alert=False)

    total, live, frozen, purged = sync_cloud_accounts()
    alert_msg = (
        f"✅ Cloud DB Sync Complete!\n\n"
        f"☁️ Total Unique in Mongo: {total}\n"
        f"🟢 Verified Live: {live}\n"
        f"❄️ Frozen (Auto-excluded): {frozen}\n"
        f"🧹 Duplicates Purged: {purged}\n\n"
        f"Zero local disk dependency. Ready for any VPS!"
    )
    if query:
        await query.answer(alert_msg, show_alert=True)
    await admin_panel(update, context)

async def toggle_maintenance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    current = is_maintenance_mode()
    new_state = not current
    set_maintenance_mode(new_state)

    status_msg = "🔴 Maintenance mode ENABLED! Regular users cannot use the bot." if new_state else "🟢 Maintenance mode DISABLED! Bot is open to all users."
    await query.answer(status_msg, show_alert=True)
    await admin_panel(update, context)

# ========== ADMIN LOG CHANNEL MANAGEMENT ==========
async def admin_log_channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    curr_ch = get_log_channel_id()
    ch_info = "<i>Not Configured</i> ⚪"
    if curr_ch:
        ch_info = f"<code>{curr_ch}</code> 🟢"
        try:
            target_chat = int(curr_ch) if (curr_ch.startswith("-") and curr_ch[1:].isdigit()) or curr_ch.isdigit() else curr_ch
            chat_obj = await context.bot.get_chat(target_chat)
            if chat_obj and chat_obj.title:
                ch_info = f"<b>{html.escape(chat_obj.title)}</b> (<code>{curr_ch}</code>) 🟢"
        except Exception:
            pass

    text = (
        f"📢 <b>ADMIN LOG CHANNEL SETTINGS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📡 <b>Current Channel:</b> {ch_info}\n\n"
        f"📋 <b>Logged Activities:</b>\n"
        f"• All campaign executions (Vote, Reactions, Views, Private View, VC, DMs, Group Spam, Leave All)\n"
        f"• All account additions (Telethon, Pyrogram, Phone OTP, 2FA, Bulk Sessions, ZIPs)\n"
        f"• Full detailed info: Initiator user, account info, targets, success/failed rates, and error logs.\n\n"
        f"⚠️ <i>Make sure this bot (@ShubhVoteBot) is added as an <b>Administrator</b> in your log channel with permission to Post Messages!</i>"
    )

    keyboard = [
        [styled_button("✏️ Set Log Channel", callback_data="admin_set_log_channel")],
    ]
    if curr_ch:
        keyboard.append([styled_button("🧪 Send Test Log", callback_data="admin_test_log_channel")])
        keyboard.append([styled_button("🗑️ Clear / Disable Log Channel", callback_data="admin_clear_log_channel")])
    keyboard.append([styled_button("🔙 Admin Panel", callback_data="admin_panel")])

    await update.callback_query.edit_message_text(
        text,
        reply_markup={"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]},
        parse_mode="HTML"
    )

async def admin_set_log_channel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'admin_set_log_channel'
    curr_ch = get_log_channel_id()
    keyboard = [[styled_button("❌ Cancel", callback_data="admin_log_channel_menu")]]

    text = (
        f"✏️ <b>SET ADMIN LOG CHANNEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Current: <code>{curr_ch or 'Not Set'}</code>\n\n"
        f"Please send your channel ID (e.g. <code>-1001234567890</code>) or channel username (<code>@channel_username</code>).\n\n"
        f"💡 <b>Instructions:</b>\n"
        f"1. Create a channel or use an existing one.\n"
        f"2. Add this bot (@ShubhVoteBot) as an <b>Admin</b> with <i>Post Messages</i> permission.\n"
        f"3. Send the channel ID here, or forward a message from that channel."
    )
    await update.callback_query.edit_message_text(
        text,
        reply_markup={"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]},
        parse_mode="HTML"
    )

async def handle_admin_set_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str = ""):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    target_id_str = None
    origin = getattr(update.message, 'forward_origin', None)
    if origin:
        chat = getattr(origin, 'chat', None) or getattr(origin, 'sender_chat', None)
        if chat:
            target_id_str = str(chat.id)
    if not target_id_str:
        fwd_chat = getattr(update.message, 'forward_from_chat', None)
        if fwd_chat:
            target_id_str = str(fwd_chat.id)
    if not target_id_str:
        raw_text = (text or update.message.text or "").strip()
        if raw_text.startswith("https://t.me/"):
            raw_text = "@" + raw_text.split("https://t.me/")[-1].split("/")[0].split("?")[0]
        target_id_str = raw_text

    if not target_id_str:
        await update.message.reply_text("❌ Invalid input! Please send a channel ID or username.")
        return

    test_chat = int(target_id_str) if (target_id_str.startswith("-") and target_id_str[1:].isdigit()) or target_id_str.isdigit() else target_id_str
    try:
        chat_obj = await context.bot.get_chat(test_chat)
        verified_id = str(chat_obj.id)
        chat_title = chat_obj.title or verified_id

        await context.bot.send_message(
            chat_id=chat_obj.id,
            text=(
                f"✅ <b>ADMIN LOG CHANNEL ACTIVATED</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤖 <b>Bot:</b> @ShubhVoteBot\n"
                f"👤 <b>Configured By:</b> {format_user_mention(user_id, update.effective_user.first_name, update.effective_user.username)}\n"
                f"📊 All campaign executions and account additions with full details will now be logged here.\n"
                f"⏰ <b>Timestamp:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML"
        )

        set_log_channel_id(verified_id)
        WAITING_FOR.pop(user_id, None)

        keyboard = [
            [styled_button("📢 Log Channel Menu", callback_data="admin_log_channel_menu")],
            [styled_button("👑 Admin Panel", callback_data="admin_panel")]
        ]
        await update.message.reply_text(
            f"✅ <b>Log Channel successfully configured!</b>\n\n"
            f"📢 <b>Channel:</b> {html.escape(chat_title)}\n"
            f"🆔 <b>ID:</b> <code>{verified_id}</code>\n\n"
            f"A verification message was sent to the channel.",
            reply_markup={"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]},
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Failed to connect to channel:</b>\n<code>{html.escape(str(e)[:200])}</code>\n\n"
            f"⚠️ <b>Checklist:</b>\n"
            f"1. Is the channel ID / username correct?\n"
            f"2. Is @ShubhVoteBot added as an <b>Administrator</b> in that channel?\n"
            f"3. Does the bot have permission to <i>Post Messages</i>?\n\n"
            f"Try again or click /start to return to menu.",
            parse_mode="HTML"
        )

async def admin_test_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    curr_ch = get_log_channel_id()
    if not curr_ch:
        await update.callback_query.answer("❌ No Log Channel configured!", show_alert=True)
        return

    test_chat = int(curr_ch) if (curr_ch.startswith("-") and curr_ch[1:].isdigit()) or curr_ch.isdigit() else curr_ch
    try:
        user_mention = format_user_mention(user_id, update.effective_user.first_name, update.effective_user.username)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await context.bot.send_message(
            chat_id=test_chat,
            text=(
                f"🧪 <b>TEST LOG NOTIFICATION</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Tested By:</b> {user_mention}\n"
                f"🟢 <b>Status:</b> Bot is connected and logging is operational!\n"
                f"⏰ <b>Time:</b> <code>{now_str}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML"
        )
        await update.callback_query.answer("✅ Test log message sent successfully!", show_alert=True)
    except Exception as e:
        await update.callback_query.answer(f"❌ Test failed: {str(e)[:80]}", show_alert=True)

async def admin_clear_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    set_log_channel_id("")
    await update.callback_query.answer("🗑️ Log channel disabled and cleared.", show_alert=True)
    await admin_log_channel_menu(update, context)

# Direct commands: /setlog and /getlog
async def cmd_set_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        return

    args = context.args
    if not args:
        WAITING_FOR[user_id] = 'admin_set_log_channel'
        await update.message.reply_text(
            "📢 Send the Log Channel ID (e.g. <code>-1001234567890</code>) or username (@channel):",
            parse_mode="HTML"
        )
        return

    channel_input = args[0].strip()
    await handle_admin_set_log_channel(update, context, text=channel_input)

async def cmd_get_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        return

    curr_ch = get_log_channel_id()
    if not curr_ch:
        await update.message.reply_text("📢 Admin Log Channel: <i>Not Configured</i>\nUse <code>/setlog &lt;channel_id&gt;</code> to configure.", parse_mode="HTML")
        return

    try:
        test_chat = int(curr_ch) if (curr_ch.startswith("-") and curr_ch[1:].isdigit()) or curr_ch.isdigit() else curr_ch
        chat_obj = await context.bot.get_chat(test_chat)
        title = chat_obj.title or curr_ch
        await update.message.reply_text(f"📢 Log Channel: <b>{html.escape(title)}</b> (<code>{curr_ch}</code>) 🟢", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"📢 Log Channel ID: <code>{curr_ch}</code> (Could not fetch info: {e})", parse_mode="HTML")

# ========== ADMIN CAMPAIGN (ALL) - uses all owner accounts ==========
async def admin_campaign_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    # Load all owner accounts (all IDs)
    all_accounts = load_owner_accounts()
    live_accounts = await get_live_accounts_batch(all_accounts)

    if not live_accounts:
        await update.callback_query.edit_message_text("❌ No active accounts available!")
        return

    # Show the shopping menu with all owner accounts
    await show_shopping_menu(update, context, live_accounts)

# ========== ADMIN CAMPAIGN (BY USER) ==========
async def admin_campaign_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'admin_campaign_user_id'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "👑 Campaign on User\n\nSend User ID:",
        reply_markup=reply_markup)

async def handle_admin_campaign_user(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        target_user = int(text.strip())
        accounts = get_accessible_accounts(target_user)
        live_accounts = await get_live_accounts_batch(accounts)

        if not live_accounts:
            await update.message.reply_text("❌ No active accounts for this user!")
            WAITING_FOR.pop(user_id, None)
            return

        context.user_data['campaign_accounts'] = live_accounts
        WAITING_FOR.pop(user_id, None)

        # Show the shopping menu with the user's accounts
        await show_shopping_menu(update, context, live_accounts)
    except Exception:
        await update.message.reply_text("❌ Invalid User ID!")
        WAITING_FOR.pop(user_id, None)

# ========== BROADCAST ==========
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'broadcast_message'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "📢 BROADCAST\n\nSend the message you want to broadcast to all users.\n\nOnly text messages are supported.",
        reply_markup=reply_markup)

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    status_msg = await update.message.reply_text("⏳ Sending broadcast...")
    users = get_all_users()
    sent = 0
    failed = 0

    for u in users:
        uid = u[0]
        try:
            await context.bot.send_message(chat_id=uid, text=text)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)

    WAITING_FOR.pop(user_id, None)
    await status_msg.edit_text(
        f"✅ Broadcast completed!\n\n"
        f"👥 Total users: {len(users)}\n"
        f"✅ Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )

# ========== GRANT/REVOKE ADMIN ==========
async def admin_grant_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'admin_grant_admin_id'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text("👑 Grant Admin\n\nSend User ID:", reply_markup=reply_markup)

async def admin_revoke_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'admin_revoke_admin_id'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text("🔽 Revoke Admin\n\nSend User ID:", reply_markup=reply_markup)

async def handle_admin_grant_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        target = int(text.strip())
        if target == OWNER_ID:
            await update.message.reply_text("❌ Cannot change owner's admin status!")
            WAITING_FOR.pop(user_id, None)
            return
        grant_admin(target)
        WAITING_FOR.pop(user_id, None)
        await update.message.reply_text(f"✅ User {target} is now an Admin!")
    except Exception:
        await update.message.reply_text("❌ Invalid User ID!")
        WAITING_FOR.pop(user_id, None)

async def handle_admin_revoke_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        target = int(text.strip())
        if target == OWNER_ID:
            await update.message.reply_text("❌ Cannot change owner's admin status!")
            WAITING_FOR.pop(user_id, None)
            return
        revoke_admin(target)
        WAITING_FOR.pop(user_id, None)
        await update.message.reply_text(f"✅ Admin revoked for User {target}!")
    except Exception:
        await update.message.reply_text("❌ Invalid User ID!")
        WAITING_FOR.pop(user_id, None)

# ========== BAN/UNBAN ==========
async def admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'admin_ban_user_id'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text("🚫 Ban User\n\nSend User ID:", reply_markup=reply_markup)

async def admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'admin_unban_user_id'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text("✅ Unban User\n\nSend User ID:", reply_markup=reply_markup)

async def admin_all_campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    text = "📁 ALL CAMPAIGNS\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    campaign_count = 0
    rows = []
    if MONGO_DB is not None:
        try:
            cursor = MONGO_DB.campaigns.find().sort("timestamp", -1).limit(20)
            rows = list(cursor)
        except Exception:
            rows = []
    for row in rows:
        campaign_count += 1
        action_name = row.get('action', '')
        target_val = str(row.get('target', ''))[:40]
        result_val = row.get('result', '')
        ts_val = str(row.get('timestamp', ''))[:16]
        text += f"{campaign_count}. {action_name}\n   {target_val}\n   {result_val}\n   {ts_val}\n\n"
        if campaign_count >= 20:
            text += "\n... and more"
            break

    if campaign_count == 0:
        text += "No campaigns!"

    keyboard = [[styled_button("🔙 Admin Panel", callback_data="admin_panel")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(text[:4000], reply_markup=reply_markup)

async def admin_all_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        if query:
            await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    users = get_all_users()
    if not users:
        keyboard = [[styled_button("🔙 Admin Panel", callback_data="admin_panel")]]
        reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
        if query:
            await query.edit_message_text("📭 No users found in database!", reply_markup=reply_markup)
        return

    PER_PAGE = 5
    total_users = len(users)
    total_pages = max(1, (total_users + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    current_page_users = users[start_idx:end_idx]

    text = (
        f"👥 <b>ALL USERS LIST</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Total Users:</b> <code>{total_users}</code> | 📄 <b>Page:</b> <code>{page}/{total_pages}</code>\n\n"
    )

    user_button_rows = []
    for idx, u in enumerate(current_page_users, start=start_idx + 1):
        uid, username, first_name, joined_date, is_banned_user, access_expiry, shared_limit, is_admin_flag = u
        personal_accounts = load_accounts(uid)

        # Dynamically sync real profile if placeholder or empty
        if not username or username in ("Owner", f"Admin_{uid}", "None") or not first_name or first_name in ("Owner", "Admin"):
            try:
                chat = await context.bot.get_chat(uid)
                if chat:
                    username = chat.username or username
                    first_name = chat.first_name or first_name
                    create_user_if_not_exists(uid, username, first_name)
            except Exception:
                pass

        # Determine precise status
        if uid == OWNER_ID:
            status = "👑 OWNER"
        elif is_admin_flag:
            status = "👨‍💼 ADMIN"
        elif is_banned_user:
            status = "🚫 BANNED"
        elif access_expiry:
            try:
                exp_dt = datetime.fromisoformat(str(access_expiry))
                if exp_dt > datetime.now():
                    days_left = (exp_dt - datetime.now()).days
                    status = f"✅ ACCESS ({days_left}d left)"
                else:
                    status = "⌛ ACCESS EXPIRED"
            except Exception:
                status = "⌛ ACCESS EXPIRED"
        else:
            status = "👤 USER"

        clean_un = str(username).strip().lstrip("@") if username else ""
        if clean_un and clean_un.lower() not in ("none", "null", "no username"):
            un_display = f"@{clean_un}"
        else:
            un_display = "No username"

        fn_display = str(first_name).strip() if first_name else "Unknown"

        joined_display = "Unknown"
        if joined_date:
            try:
                joined_display = str(joined_date).split(".")[0][:16]
            except Exception:
                joined_display = str(joined_date)[:16]

        safe_fn = html.escape(fn_display)
        safe_un = html.escape(un_display)

        text += f"<b>{idx}. {status}</b>\n"
        text += f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        text += f"📛 <b>Name:</b> {safe_fn}\n"
        text += f"📝 <b>Username:</b> {safe_un}\n"
        text += f"📅 <b>Joined:</b> {joined_display}\n"
        text += f"📱 <b>Accounts:</b> {len(personal_accounts)}"
        if shared_limit:
            text += f" | 🔗 <b>Shared:</b> {shared_limit}"
        if access_expiry:
            try:
                exp_fmt = datetime.fromisoformat(str(access_expiry)).strftime("%Y-%m-%d %H:%M")
                text += f"\n⏰ <b>Expiry:</b> {exp_fmt}"
            except Exception:
                text += f"\n⏰ <b>Expiry:</b> {access_expiry}"
        text += "\n──────────────────────\n"

        btn_title = f"👤 {idx}. {fn_display[:14]} ({uid})"
        user_button_rows.append([styled_button(btn_title, callback_data=f"admin_view_user:{uid}:{page}")])

    keyboard = []
    for row in user_button_rows:
        keyboard.append(row)

    nav_row = []
    if page > 1:
        nav_row.append(styled_button("◀️ Prev", callback_data=f"admin_users_p:{page-1}"))
    nav_row.append(styled_button(f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(styled_button("Next ▶️", callback_data=f"admin_users_p:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([
        styled_button("🔄 Refresh", callback_data=f"admin_users_p:{page}"),
        styled_button("🔙 Admin Panel", callback_data="admin_panel")
    ])

    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    if query:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
            await query.edit_message_text(clean_text, reply_markup=reply_markup)

async def admin_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int, return_page: int = 1):
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        if query:
            await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    user = get_user(uid)
    if not user:
        if query:
            await query.answer("❌ User not found!", show_alert=True)
        return

    try:
        chat = await context.bot.get_chat(uid)
        if chat:
            if chat.username:
                user["username"] = chat.username
            if chat.first_name:
                user["first_name"] = chat.first_name
            create_user_if_not_exists(uid, user.get("username", ""), user.get("first_name", ""))
    except Exception:
        pass

    fn = user.get("first_name") or "Unknown"
    un = user.get("username") or ""
    clean_un = str(un).strip().lstrip("@")
    un_disp = f"@{clean_un}" if clean_un and clean_un.lower() not in ("none", "null", "no username") else "No username"

    is_banned_flag = bool(user.get("is_banned", 0))
    is_admin_flag = bool(user.get("is_admin", 0)) or uid == OWNER_ID
    access_exp = user.get("access_expiry")
    shared_lim = user.get("shared_id_limit", 0)
    joined = str(user.get("joined_date", "Unknown")).split(".")[0][:16]

    if uid == OWNER_ID:
        role_status = "👑 OWNER"
    elif is_admin_flag:
        role_status = "👨‍💼 ADMIN"
    elif is_banned_flag:
        role_status = "🚫 BANNED"
    elif access_exp:
        try:
            exp_dt = datetime.fromisoformat(str(access_exp))
            if exp_dt > datetime.now():
                days_left = (exp_dt - datetime.now()).days
                role_status = f"✅ ACTIVE ACCESS ({days_left}d left)"
            else:
                role_status = "⌛ EXPIRED ACCESS"
        except Exception:
            role_status = "⌛ EXPIRED ACCESS"
    else:
        role_status = "👤 REGULAR USER"

    accs = user.get("accounts", [])

    safe_fn = html.escape(str(fn))
    safe_un = html.escape(str(un_disp))

    text = (
        f"👤 <b>USER DETAILS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>Telegram ID:</b> <code>{uid}</code>\n"
        f"📛 <b>Name:</b> {safe_fn}\n"
        f"📝 <b>Username:</b> {safe_un}\n"
        f"🔰 <b>Role / Status:</b> {role_status}\n"
        f"📅 <b>Joined:</b> {joined}\n"
    )
    if access_exp:
        text += f"⏰ <b>Access Expiry:</b> <code>{access_exp}</code>\n"
    text += f"🔗 <b>Shared Limit:</b> <code>{shared_lim}</code> accounts\n\n"

    text += f"📱 <b>LINKED ACCOUNTS ({len(accs)}):</b>\n"
    if accs:
        for idx, a in enumerate(accs[:15], start=1):
            p = a.get("phone", "Unknown")
            acc_name = a.get("first_name") or "No name"
            acc_un = a.get("username")
            acc_un_str = f"@{str(acc_un).lstrip('@')}" if acc_un and str(acc_un).strip() not in ("None", "none", "No username", "Imported", "") else "No username"
            acc_uid = a.get("user_id") or "N/A"
            safe_acc_name = html.escape(str(acc_name))
            safe_acc_un = html.escape(str(acc_un_str))
            text += f"  {idx}. 📱 <code>+{p}</code> | 📛 <b>{safe_acc_name}</b>\n"
            text += f"     📝 {safe_acc_un} | 🆔 TG: <code>{acc_uid}</code>\n"
        if len(accs) > 15:
            text += f"  <i>... and {len(accs) - 15} more accounts</i>\n"
    else:
        text += "  <i>No personal accounts linked.</i>\n"

    text += "━━━━━━━━━━━━━━━━━━━━━━\n"

    keyboard = []
    ban_btn_text = "✅ Unban User" if is_banned_flag else "🚫 Ban User"
    ban_cb = f"admin_toggle_ban:{uid}:{return_page}"

    keyboard.append([
        styled_button("⏰ Give Access", callback_data=f"admin_give_acc_to:{uid}:{return_page}"),
        styled_button("❌ Remove Access", callback_data=f"admin_rem_acc_from:{uid}:{return_page}")
    ])

    if uid != OWNER_ID:
        admin_toggle_text = "🔽 Demote to User" if is_admin_flag else "👑 Make Admin"
        admin_cb = f"admin_toggle_admin:{uid}:{return_page}"
        keyboard.append([
            styled_button(ban_btn_text, callback_data=ban_cb),
            styled_button(admin_toggle_text, callback_data=admin_cb)
        ])
    else:
        keyboard.append([styled_button(ban_btn_text, callback_data=ban_cb)])

    keyboard.append([
        styled_button("🔗 Set Shared Limit", callback_data=f"admin_set_shared_to:{uid}:{return_page}"),
        styled_button("🗑️ Delete User", callback_data=f"admin_del_user:{uid}:{return_page}")
    ])

    keyboard.append([
        styled_button("🔙 Back to Users List", callback_data=f"admin_users_p:{return_page}"),
        styled_button("👑 Admin Panel", callback_data="admin_panel")
    ])

    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    if query:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            clean_text = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<i>", "").replace("</i>", "")
            await query.edit_message_text(clean_text, reply_markup=reply_markup)

async def admin_delete_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int, return_page: int = 1):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return
    if uid == OWNER_ID:
        await query.answer("❌ Cannot delete Owner!", show_alert=True)
        return

    keyboard = [
        [styled_button("⚠️ YES, DELETE USER", callback_data=f"admin_del_user_confirm:{uid}:{return_page}")],
        [styled_button("❌ Cancel", callback_data=f"admin_view_user:{uid}:{return_page}")]
    ]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await query.edit_message_text(
        f"⚠️ <b>DELETE USER CONFIRMATION</b>\n\nAre you sure you want to delete user <code>{uid}</code> and remove all their data from the database?",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def admin_delete_user_execute(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int, return_page: int = 1):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return
    if uid == OWNER_ID:
        await query.answer("❌ Cannot delete Owner!", show_alert=True)
        return

    success = delete_user(uid)
    if success:
        await query.answer("✅ User deleted successfully!", show_alert=True)
    else:
        await query.answer("❌ Failed to delete user!", show_alert=True)
    await admin_all_users_list(update, context, page=return_page)

async def admin_toggle_ban_action(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int, return_page: int = 1):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return
    if uid == OWNER_ID:
        await query.answer("❌ Cannot ban Owner!", show_alert=True)
        return

    if is_banned(uid):
        unban_user(uid)
        await query.answer(f"✅ User {uid} unbanned!", show_alert=True)
    else:
        ban_user(uid)
        await query.answer(f"🚫 User {uid} banned!", show_alert=True)

    await admin_user_detail(update, context, uid=uid, return_page=return_page)

async def admin_toggle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE, uid: int, return_page: int = 1):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ Only Owner can manage admin privileges!", show_alert=True)
        return
    if uid == OWNER_ID:
        await query.answer("❌ Owner is always Admin!", show_alert=True)
        return

    user = get_user(uid)
    is_currently_admin = bool(user and user.get("is_admin", 0) == 1)
    if is_currently_admin:
        revoke_admin(uid)
        await query.answer(f"🔽 Admin revoked for {uid}!", show_alert=True)
    else:
        grant_admin(uid)
        await query.answer(f"👑 Admin granted to {uid}!", show_alert=True)

    await admin_user_detail(update, context, uid=uid, return_page=return_page)

async def handle_set_shared_limit_num(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return
    target = context.user_data.get('target_user_id')
    ret_page = context.user_data.get('return_page', 1)
    if not target:
        await update.message.reply_text("❌ No target user selected!")
        WAITING_FOR.pop(user_id, None)
        return
    try:
        limit = int(text.strip())
        if limit < 0:
            raise ValueError
        set_user_shared_limit(target, limit)
        WAITING_FOR.pop(user_id, None)
        keyboard = [[styled_button("🔙 Back to User", callback_data=f"admin_view_user:{target}:{ret_page}")]]
        reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
        await update.message.reply_text(f"✅ Shared account limit for user {target} set to {limit}!", reply_markup=reply_markup)
    except Exception:
        await update.message.reply_text("❌ Please send a valid number (0 or higher)!")

async def handle_admin_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        target = int(text.strip())
        if target == OWNER_ID:
            await update.message.reply_text("❌ Cannot ban owner!")
            WAITING_FOR.pop(user_id, None)
            return
        ban_user(target)
        WAITING_FOR.pop(user_id, None)
        await update.message.reply_text(f"✅ User {target} banned!")
    except Exception:
        await update.message.reply_text("❌ Invalid User ID!")
        WAITING_FOR.pop(user_id, None)

async def handle_admin_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    try:
        target = int(text.strip())
        unban_user(target)
        WAITING_FOR.pop(user_id, None)
        await update.message.reply_text(f"✅ User {target} unbanned!")
    except Exception:
        await update.message.reply_text("❌ Invalid User ID!")
        WAITING_FOR.pop(user_id, None)

async def admin_view_live(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    # Use pagination cache if available and fresh (<120s)
    cached_live_data = context.user_data.get('cached_admin_live')
    now = time.time()
    if cached_live_data and (now - cached_live_data[1] < 120):
        live = cached_live_data[0]
    else:
        all_accounts = load_owner_accounts()
        live = await get_live_accounts_batch(all_accounts)
        context.user_data['cached_admin_live'] = (live, now)

    if not live:
        keyboard = [[styled_button("🔙 My Accounts", callback_data="my_accounts")]]
        reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
        await query.edit_message_text("📋 No live accounts found!", reply_markup=reply_markup)
        return

    PER_PAGE = 8
    total = len(live)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * PER_PAGE
    current_accs = live[start_idx:start_idx + PER_PAGE]

    text = f"📋 <b>LIVE ACCOUNTS</b>\n━━━━━━━━━━━━━━━━━━━━━━\nTotal: <code>{total}</code> | Page: <code>{page}/{total_pages}</code>\n\n"
    for idx, a in enumerate(current_accs, start=start_idx + 1):
        phone = a.get('phone', 'Unknown')
        name = a.get('first_name') or 'No name'
        u = a.get('username')
        u_str = f"@{str(u).lstrip('@')}" if u and str(u).strip() not in ('None', 'none', 'No username', 'Imported', '') else "No username"
        uid = a.get('user_id')
        uid_str = f" | 🆔 TG: <code>{uid}</code>" if uid else ""
        clean_phone = str(phone).strip().lstrip('+')
        phone_disp = f"+{clean_phone}" if clean_phone and clean_phone != 'Unknown' else 'Unknown'
        safe_name = html.escape(str(name))
        safe_u = html.escape(str(u_str))
        text += f"{idx}. 📱 <code>{phone_disp}</code> | 📛 <b>{safe_name}</b>\n   📝 {safe_u}{uid_str}\n\n"

    keyboard = []
    nav_row = []
    if page > 1:
        nav_row.append(styled_button("◀️ Prev", callback_data=f"admin_view_live_p:{page-1}"))
    nav_row.append(styled_button(f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(styled_button("Next ▶️", callback_data=f"admin_view_live_p:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([styled_button("🔙 My Accounts", callback_data="my_accounts")])
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        clean = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
        await query.edit_message_text(clean, reply_markup=reply_markup)

async def admin_view_expired(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    # Use pagination cache if available and fresh (<120s)
    cached_exp_data = context.user_data.get('cached_admin_exp')
    now = time.time()
    if cached_exp_data and (now - cached_exp_data[1] < 120):
        expired = cached_exp_data[0]
    else:
        all_accounts = load_owner_accounts()
        expired = await get_expired_accounts_batch(all_accounts)
        context.user_data['cached_admin_exp'] = (expired, now)

    if not expired:
        keyboard = [[styled_button("🔙 My Accounts", callback_data="my_accounts")]]
        reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
        await query.edit_message_text("📋 No expired accounts found! All accounts are live.", reply_markup=reply_markup)
        return

    PER_PAGE = 8
    total = len(expired)
    total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * PER_PAGE
    current_accs = expired[start_idx:start_idx + PER_PAGE]

    text = f"📋 <b>EXPIRED ACCOUNTS</b>\n━━━━━━━━━━━━━━━━━━━━━━\nTotal: <code>{total}</code> | Page: <code>{page}/{total_pages}</code>\n\n"
    for idx, a in enumerate(current_accs, start=start_idx + 1):
        phone = a.get('phone', 'Unknown')
        name = a.get('first_name') or 'No name'
        u = a.get('username')
        u_str = f"@{str(u).lstrip('@')}" if u and str(u).strip() not in ('None', 'none', 'No username', 'Imported', '') else "No username"
        uid = a.get('user_id')
        uid_str = f" | 🆔 TG: <code>{uid}</code>" if uid else ""
        clean_phone = str(phone).strip().lstrip('+')
        phone_disp = f"+{clean_phone}" if clean_phone and clean_phone != 'Unknown' else 'Unknown'
        safe_name = html.escape(str(name))
        safe_u = html.escape(str(u_str))
        text += f"{idx}. 📱 <code>{phone_disp}</code> | 📛 <b>{safe_name}</b>\n   📝 {safe_u}{uid_str}\n\n"

    keyboard = [
        [styled_button("🗑️ Remove All Expired", callback_data="admin_remove_all_expired")]
    ]
    nav_row = []
    if page > 1:
        nav_row.append(styled_button("◀️ Prev", callback_data=f"admin_view_exp_p:{page-1}"))
    nav_row.append(styled_button(f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(styled_button("Next ▶️", callback_data=f"admin_view_exp_p:{page+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([styled_button("🔙 My Accounts", callback_data="my_accounts")])
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        clean = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "")
        await query.edit_message_text(clean, reply_markup=reply_markup)

async def admin_remove_all_expired(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    all_accounts = load_owner_accounts()
    expired = await get_expired_accounts_batch(all_accounts)

    if not expired:
        await query.answer("📋 No confirmed expired accounts to remove!", show_alert=True)
        return

    def _get_k(a):
        return str(a.get('phone') or a.get('user_id') or a.get('session_string') or '').strip().lstrip('+')

    expired_keys = {_get_k(a) for a in expired}
    new_accounts = [a for a in all_accounts if _get_k(a) not in expired_keys]
    save_accounts(OWNER_ID, new_accounts)

    users = get_all_users()
    for u in users:
        uid = u[0]
        if uid != OWNER_ID:
            user_accounts = load_accounts(uid)
            new_user_accounts = [a for a in user_accounts if _get_k(a) not in expired_keys]
            if len(user_accounts) != len(new_user_accounts):
                save_accounts(uid, new_user_accounts)

    for k in expired_keys:
        cl = ACTIVE_CLIENTS.pop(k, None)
        if cl and cl.is_connected():
            try:
                await cl.disconnect()
            except Exception:
                pass
        LIVE_CACHE.pop(k, None)

    # Invalidate pagination cache
    context.user_data.pop('cached_admin_exp', None)
    context.user_data.pop('cached_admin_live', None)

    await update.callback_query.edit_message_text(
        f"✅ Removed {len(expired)} confirmed expired accounts!\n(All live accounts protected)",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 My Accounts", callback_data="my_accounts")]]))


async def admin_remove_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    WAITING_FOR[user_id] = 'admin_remove_phone'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "🗑️ Remove Account\n\nSend phone number:\nExample: +919876543210",
        reply_markup=reply_markup)

async def admin_remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    user_id = update.effective_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.message.reply_text("❌ Only Owner/Admin!")
        WAITING_FOR.pop(user_id, None)
        return

    clean_p = phone.strip().replace(" ", "").replace("-", "")
    norm_p = clean_p.lstrip("+")
    def _is_match(a):
        aph = str(a.get('phone', '')).strip().replace(" ", "").replace("-", "")
        return aph == clean_p or aph.lstrip("+") == norm_p

    owner_accounts = load_owner_accounts()
    found = any(_is_match(a) for a in owner_accounts)
    if not found:
        await update.message.reply_text("❌ Account not found!")
        WAITING_FOR.pop(user_id, None)
        return

    new_owner_accounts = [a for a in owner_accounts if not _is_match(a)]
    save_accounts(OWNER_ID, new_owner_accounts)

    users = get_all_users()
    for u in users:
        uid = u[0]
        if uid != OWNER_ID:
            user_accounts = load_accounts(uid)
            new_user_accounts = [a for a in user_accounts if not _is_match(a)]
            if len(user_accounts) != len(new_user_accounts):
                save_accounts(uid, new_user_accounts)

    # Disconnect active client and clear cache
    for key in (phone, clean_p, f"+{norm_p}", norm_p):
        cl = ACTIVE_CLIENTS.pop(key, None)
        if cl and cl.is_connected():
            try:
                await cl.disconnect()
            except Exception:
                pass
        LIVE_CACHE.pop(key, None)

    WAITING_FOR.pop(user_id, None)
    await update.message.reply_text(f"✅ Account {phone} removed!")

async def admin_remove_all_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    all_accounts = load_owner_accounts()
    keyboard = [
        [styled_button("⚠️ YES, REMOVE ALL", callback_data="admin_remove_all_confirm")],
        [styled_button("❌ Cancel", callback_data="cancel_action")],
    ]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        f"⚠️ WARNING!\n\nRemove ALL {len(all_accounts)} accounts?\n\nThis cannot be undone!",
        reply_markup=reply_markup)

async def admin_remove_all_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    if not is_owner(user_id) and not is_admin_user(user_id):
        await update.callback_query.answer("❌ Only Owner/Admin!", show_alert=True)
        return

    save_accounts(OWNER_ID, [])
    users = get_all_users()
    for u in users:
        uid = u[0]
        if uid != OWNER_ID:
            save_accounts(uid, [])

    await update.callback_query.edit_message_text(
        "✅ All accounts removed!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main")]]))

async def user_remove_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    WAITING_FOR[user_id] = 'user_remove_phone'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(
        "🗑️ Remove Personal Account\n\nSend phone number to remove:",
        reply_markup=reply_markup)

async def user_remove_account(update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
    user_id = update.effective_user.id
    accounts = load_accounts(user_id)

    clean_p = phone.strip().replace(" ", "").replace("-", "")
    norm_p = clean_p.lstrip("+")
    def _is_match(a):
        aph = str(a.get('phone', '')).strip().replace(" ", "").replace("-", "")
        return aph == clean_p or aph.lstrip("+") == norm_p

    found = any(_is_match(a) for a in accounts)
    if not found:
        await update.message.reply_text("❌ Account not found in your personal accounts!")
        WAITING_FOR.pop(user_id, None)
        return

    new_accounts = [a for a in accounts if not _is_match(a)]
    save_accounts(user_id, new_accounts)

    for key in (phone, clean_p, f"+{norm_p}", norm_p):
        cl = ACTIVE_CLIENTS.pop(key, None)
        if cl and cl.is_connected():
            try:
                await cl.disconnect()
            except Exception:
                pass
        LIVE_CACHE.pop(key, None)

    WAITING_FOR.pop(user_id, None)
    await update.message.reply_text(f"✅ Account {phone} removed from your personal accounts!")

# ========== MY CAMPAIGNS, STATS, PROFILE, HELP, SUPPORT ==========
async def my_campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    campaigns = load_campaigns(user_id)
    if not campaigns:
        await update.callback_query.edit_message_text("📁 No purchases yet!\n\nRun campaigns from Shopping.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main")]]))
        return

    text = "📁 MY PURCHASED\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, c in enumerate(campaigns[:10], 1):
        text += f"{i}. {c['action']}\n   Target: {c['target'][:40]}\n   Result: {c['result']}\n   Time: {c['timestamp'].split('.')[0]}\n\n"

    await update.callback_query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main")]]))

async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    personal_accounts = load_accounts(user_id)
    personal_live = await get_live_accounts_batch(personal_accounts)
    personal_active = len(personal_live)

    shared_limit = get_user_shared_limit(user_id)
    total_available = len(get_accessible_accounts(user_id))
    campaigns = load_campaigns(user_id)

    text = f"📊 YOUR STATS\n━━━━━━━━━━━━━━━━━━━━━━\n\n📱 Personal: {len(personal_accounts)} (🟢{personal_active})\n🔗 Shared Limit: {shared_limit}\n📊 Total Available: {total_available}\n📁 Purchased: {len(campaigns)}"

    await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="main")]]))

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    settings = load_settings(user_id)
    current_delay = settings.get('delay', DEFAULT_DELAY)

    keyboard = [
        [styled_button("⚡ 0.5s", callback_data="delay_0.5"),
         styled_button("⏱️ 1.0s", callback_data="delay_1.0")],
        [styled_button("⏳ 1.5s", callback_data="delay_1.5"),
         styled_button("🛡️ 2.0s", callback_data="delay_2.0")],
        [styled_button("✏️ Custom Delay", callback_data="custom_delay")],
        [styled_button("❌ Cancel", callback_data="cancel_action")],
    ]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(f"⚙️ SETTINGS\nDelay: {current_delay}s", reply_markup=reply_markup)

async def set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE, delay: str):
    user_id = update.callback_query.from_user.id
    settings = load_settings(user_id)
    settings['delay'] = float(delay)
    save_settings(user_id, settings)

    keyboard = [[styled_button("🔙 Settings", callback_data="settings")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(f"✅ Delay set to {delay}s", reply_markup=reply_markup)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    doc = get_user(user_id)
    if not doc:
        await update.callback_query.edit_message_text("❌ User not found!")
        return

    first_name = doc.get('first_name', 'Unknown')
    username = doc.get('username', 'Unknown')
    joined_date = doc.get('joined_date', 'Unknown')
    access_expiry = doc.get('access_expiry')
    shared_limit = doc.get('shared_id_limit', 0)
    is_admin_flag = doc.get('is_admin', 0)

    personal_accounts = load_accounts(user_id)
    campaigns = load_campaigns(user_id)

    admin_badge = " 👑 OWNER" if user_id == OWNER_ID else (" 👨‍💼 ADMIN" if is_admin_flag else "")

    text = f"👤 PROFILE{admin_badge}\n━━━━━━━━━━━━━━━━━━━━━━\n\n🆔 {user_id}\n👤 {first_name}\n📝 @{username}\n📅 {joined_date[:10] if joined_date else 'Unknown'}\n📱 Personal: {len(personal_accounts)}\n🔗 Shared Limit: {shared_limit}\n📁 Purchased: {len(campaigns)}"

    if access_expiry and user_id != OWNER_ID:
        exp_date = datetime.fromisoformat(access_expiry).strftime("%Y-%m-%d")
        text += f"\n⏰ Access until: {exp_date}"

    keyboard = [[styled_button("🔙 Main Menu", callback_data="main")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def help_guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """🤖 HOW TO USE
━━━━━━━━━━━━━━━━━━━━━━

📌 ADD ACCOUNTS
Phone + OTP / Session String / Bulk Sessions / ZIP Upload

📌 SHOPPING (CAMPAIGNS)
1. Click 'Shopping'
2. Select action
3. Choose reaction type (if applicable)
4. Send link
5. Choose account count
6. Tap 'Run'

📌 ACTIONS (ALL WORKING ✅)
• ❤️ React Only - choose normal or premium
• 🎲 Different Reactions - Random emoji each account
• 🎨 Multiple Reactions - Choose multiple emojis, split accounts (normal only)
• ✨ Premium Emoji - Auto-detect premium reaction
• 👁️ View - Increase view count (REAL VIEWS)
• 🗳️ Vote - Click poll button
• 📢 Join - Join channel
• 🚪 Leave Channel - Leave specific channel
• 🗑️ LEAVE ALL - Leave all channels
• 💬 Bulk DM - Send messages
• 🔊 VC - Join voice chat (mic off)
• 📢 Group Spam - Spam in groups

📌 SUPPORTED LINKS
• Public Post: t.me/username/123
• Private Post: t.me/c/123456789/123
• Private Invite: t.me/joinchat/xxxxx
• Channel Join: t.me/username or invite link

📌 PREMIUM EMOJIS
Auto-detection: react manually, bot detects and uses same premium emoji.

📌 ADMIN FEATURES
Owner can grant admin rights and broadcast messages.

📌 ACCESS
Contact @SHUBHxSELLER

👨‍💻 Support: @AUTO_BOTS_INFO"""

    keyboard = [[styled_button("🔙 Main Menu", callback_data="main")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """📞 SUPPORT & CONTACT
━━━━━━━━━━━━━━━━━━━━━━

👨‍💻 Channel: @AUTO_BOTS_INFO
📞 Access/Support: @SHUBHxSELLER
🔧 Bot Owner: @SHUBHxSELLER

For issues, bugs, or access requests, contact above."""

    keyboard = [[styled_button("🔙 Main Menu", callback_data="main")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def custom_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.callback_query.from_user.id
    WAITING_FOR[user_id] = 'custom_delay'
    keyboard = [[styled_button("❌ Cancel", callback_data="cancel_action")]]
    reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
    await update.callback_query.edit_message_text("⏱️ Send delay in seconds (example: 0.8):", reply_markup=reply_markup)

async def handle_custom_delay(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    try:
        delay = float(text)
        if delay <= 0:
            raise ValueError
        settings = load_settings(user_id)
        settings['delay'] = delay
        save_settings(user_id, settings)
        WAITING_FOR.pop(user_id, None)
        await update.message.reply_text(f"✅ Delay set to {delay}s")
    except Exception:
        await update.message.reply_text("❌ Invalid value!")
        WAITING_FOR.pop(user_id, None)

# ========== MESSAGE HANDLER ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    if user:
        create_user_if_not_exists(user.id, user.username or "", user.first_name or "")

    user_id = update.effective_user.id
    if is_maintenance_mode() and not is_admin_user(user_id):
        await update.message.reply_text("🛠️ The bot is currently under maintenance. Please check back later!")
        return

    text = update.message.text.strip()
    state = WAITING_FOR.get(user_id)

    if state == 'stock_upload':
        await handle_stock_upload_text(update, context, text)
    elif state == 'phone':
        await handle_phone(update, context, text)
    elif state == 'session_string':
        await handle_session_string(update, context, text)
    elif state == 'bulk_sessions':
        await handle_bulk_sessions(update, context, text)
    elif state == 'pyrogram_session':
        await handle_pyrogram_session(update, context, text)
    elif state == 'campaign_link':
        await handle_campaign_link(update, context, text)
    elif state == 'spam_message':
        await handle_spam_message(update, context, text)
    elif state == 'account_count':
        await handle_account_count(update, context, text)
    elif state == 'custom_delay':
        await handle_custom_delay(update, context, text)
    elif state == 'admin_remove_phone':
        await admin_remove_account(update, context, text)
    elif state == 'user_remove_phone':
        await user_remove_account(update, context, text)
    elif state == 'admin_set_log_channel':
        await handle_admin_set_log_channel(update, context, text)
    elif state == 'admin_campaign_user_id':
        await handle_admin_campaign_user(update, context, text)
    elif state == 'admin_ban_user_id':
        await handle_admin_ban_user(update, context, text)
    elif state == 'admin_unban_user_id':
        await handle_admin_unban_user(update, context, text)
    elif state == 'admin_grant_admin_id':
        await handle_admin_grant_admin(update, context, text)
    elif state == 'admin_revoke_admin_id':
        await handle_admin_revoke_admin(update, context, text)
    elif state == 'access_user_id':
        await handle_access_user_id(update, context, text)
    elif state == 'access_days':
        await handle_access_days(update, context, text)
    elif state == 'access_shared_limit':
        await handle_access_shared_limit(update, context, text)
    elif state == 'shared_limit_num':
        await handle_set_shared_limit_num(update, context, text)
    elif state == 'remove_access_user_id':
        await handle_remove_access(update, context, text)
    elif state == 'schedule_link':
        await handle_schedule_link(update, context, text)
    elif state == 'schedule_spam_message':
        await handle_schedule_spam_message(update, context, text)
    elif state == 'schedule_time':
        await handle_schedule_time(update, context, text)
    elif state == 'schedule_account_count':
        await handle_schedule_account_count(update, context, text)
    elif state == 'cancel_schedule_id':
        await handle_cancel_schedule(update, context, text)
    elif state == 'private_view_link':
        await handle_private_view(update, context, text)
    elif state == 'leave_specific_link':
        await handle_leave_specific(update, context, text)
    elif state == 'premium_link':
        await handle_premium_link(update, context, text)
    elif state == 'broadcast_message':
        await handle_broadcast(update, context, text)
    elif state in ('premium_wait_react', 'premium_detect_react'):
        target_cb = "premium_reacted" if state == 'premium_wait_react' else "premium_reacted_for_action"
        await update.message.reply_text(
            "👉 Please tap the button below once you have reacted with your desired premium emoji:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ I have reacted", callback_data=target_cb)],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]
            ])
        )
    elif state == 'schedule_action':
        pass
    elif user_id in PENDING_OTP:
        clean_code = text.replace(" ", "").replace("-", "")
        if clean_code.isdigit() and len(clean_code) in (5, 6):
            await verify_otp(update, context, clean_code)
        else:
            await update.message.reply_text("❌ Please enter a valid 5 or 6-digit OTP code (e.g. 12345):")
    elif user_id in PENDING_2FA:
        await verify_2fa(update, context, text)
    else:
        await update.message.reply_text("❌ Send /start")

# ========== CALLBACK HANDLER ==========
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    user_id = query.from_user.id
    if query.from_user:
        create_user_if_not_exists(user_id, query.from_user.username or "", query.from_user.first_name or "")

    if is_maintenance_mode() and not is_admin_user(user_id):
        await query.answer("🛠️ Bot is currently under maintenance! Please try again later.", show_alert=True)
        return

    if data == "main":
        await show_main_menu(update, context)
    elif data == "toggle_maintenance":
        await toggle_maintenance_callback(update, context)
    elif data == "add_account":
        await add_account_menu(update, context)
    elif data == "add_phone_otp":
        await add_phone_otp(update, context)
    elif data == "add_session_file":
        await add_session_file(update, context)
    elif data == "add_session_string":
        await add_session_string(update, context)
    elif data == "add_pyrogram_session":
        await add_pyrogram_session(update, context)
    elif data == "add_bulk_sessions":
        await add_bulk_sessions(update, context)
    elif data == "add_zip":
        await add_zip(update, context)
    elif data == "my_accounts":
        await my_accounts(update, context)
    elif data == "new_campaign":
        await new_campaign(update, context)
    elif data == "private_channel_view":
        await private_channel_view(update, context)
    elif data == "leave_channel_menu":
        await leave_channel_menu(update, context)
    elif data == "leave_specific_channel":
        await leave_specific_channel(update, context)
    elif data == "leave_all_channels":
        await leave_all_channels(update, context)
    elif data == "confirm_leave_all":
        await confirm_leave_all(update, context)
    elif data == "scheduled":
        await scheduled_menu(update, context)
    elif data == "schedule_new":
        await schedule_new(update, context)
    elif data == "schedule_cancel":
        await schedule_cancel(update, context)
    elif data.startswith("schedule_action_"):
        action = data.replace("schedule_action_", "")
        await schedule_action_handler(update, context, action)
    elif data.startswith("campaign_action_"):
        action = data.replace("campaign_action_", "")
        await campaign_action_handler(update, context, action)
    elif data == "campaign_normal_emoji":
        await campaign_normal_emoji(update, context)
    elif data == "campaign_premium_mode":
        await campaign_premium_mode(update, context)
    elif data.startswith("select_emoji_"):
        await select_emoji_callback(update, context)
    elif data == "emoji_ready":
        await emoji_ready_callback(update, context)
    elif data.startswith("select_premium_"):
        await campaign_premium_mode(update, context)
    elif data.startswith("use_all_"):
        await use_all_callback(update, context)
    elif data == "run_campaign":
        await run_campaign(update, context)
    elif data == "my_campaigns":
        await my_campaigns(update, context)
    elif data == "my_stats":
        await my_stats(update, context)
    elif data == "settings":
        await settings_menu(update, context)
    elif data == "profile":
        await profile(update, context)
    elif data == "help":
        await help_guide(update, context)
    elif data == "support":
        await support(update, context)
    elif data.startswith("delay_"):
        await set_delay(update, context, data.replace("delay_", ""))
    elif data == "custom_delay":
        await custom_delay(update, context)
    elif data == "admin_panel":
        await admin_panel(update, context)
    elif data == "admin_all_accounts":
        await admin_all_accounts_menu(update, context)
    elif data == "admin_sync_disk_sessions":
        await admin_sync_disk_sessions_action(update, context)
    elif data == "admin_log_channel_menu":
        await admin_log_channel_menu(update, context)
    elif data == "admin_set_log_channel":
        await admin_set_log_channel_prompt(update, context)
    elif data == "admin_test_log_channel":
        await admin_test_log_channel(update, context)
    elif data == "admin_clear_log_channel":
        await admin_clear_log_channel(update, context)
    elif data == "admin_campaign_all":
        await admin_campaign_all(update, context)
    elif data == "admin_campaign_user":
        await admin_campaign_user(update, context)
    elif data == "admin_ban_user":
        await admin_ban_user(update, context)
    elif data == "admin_unban_user":
        await admin_unban_user(update, context)
    elif data == "admin_grant_admin":
        await admin_grant_admin(update, context)
    elif data == "admin_revoke_admin":
        await admin_revoke_admin(update, context)
    elif data == "admin_all_campaigns":
        await admin_all_campaigns(update, context)
    elif data == "admin_all_users" or data.startswith("admin_users_p:"):
        page = int(data.split(":")[1]) if ":" in data else 1
        await admin_all_users_list(update, context, page=page)
    elif data.startswith("admin_view_user:"):
        parts = data.split(":")
        target_uid = int(parts[1])
        ret_page = int(parts[2]) if len(parts) > 2 else 1
        await admin_user_detail(update, context, uid=target_uid, return_page=ret_page)
    elif data.startswith("admin_toggle_ban:"):
        parts = data.split(":")
        target_uid = int(parts[1])
        ret_page = int(parts[2]) if len(parts) > 2 else 1
        await admin_toggle_ban_action(update, context, uid=target_uid, return_page=ret_page)
    elif data.startswith("admin_toggle_admin:"):
        parts = data.split(":")
        target_uid = int(parts[1])
        ret_page = int(parts[2]) if len(parts) > 2 else 1
        await admin_toggle_admin_action(update, context, uid=target_uid, return_page=ret_page)
    elif data.startswith("admin_rem_acc_from:"):
        parts = data.split(":")
        target_uid = int(parts[1])
        ret_page = int(parts[2]) if len(parts) > 2 else 1
        remove_user_access(target_uid)
        await query.answer("✅ Access removed!", show_alert=True)
        await admin_user_detail(update, context, uid=target_uid, return_page=ret_page)
    elif data.startswith("admin_del_user:"):
        parts = data.split(":")
        target_uid = int(parts[1])
        ret_page = int(parts[2]) if len(parts) > 2 else 1
        await admin_delete_user_prompt(update, context, uid=target_uid, return_page=ret_page)
    elif data.startswith("admin_del_user_confirm:"):
        parts = data.split(":")
        target_uid = int(parts[1])
        ret_page = int(parts[2]) if len(parts) > 2 else 1
        await admin_delete_user_execute(update, context, uid=target_uid, return_page=ret_page)
    elif data.startswith("admin_give_acc_to:"):
        parts = data.split(":")
        target_uid = int(parts[1])
        ret_page = int(parts[2]) if len(parts) > 2 else 1
        ACCESS_DATA[query.from_user.id] = {'target_user': target_uid}
        WAITING_FOR[query.from_user.id] = 'access_days'
        keyboard = [[styled_button("❌ Cancel", callback_data=f"admin_view_user:{target_uid}:{ret_page}")]]
        reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
        await query.edit_message_text(
            f"📅 How many days access for user <code>{target_uid}</code>?\n\nSend a number (e.g. 30):",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    elif data.startswith("admin_set_shared_to:"):
        parts = data.split(":")
        target_uid = int(parts[1])
        ret_page = int(parts[2]) if len(parts) > 2 else 1
        context.user_data['target_user_id'] = target_uid
        context.user_data['return_page'] = ret_page
        WAITING_FOR[query.from_user.id] = 'shared_limit_num'
        keyboard = [[styled_button("❌ Cancel", callback_data=f"admin_view_user:{target_uid}:{ret_page}")]]
        reply_markup = {"inline_keyboard": [[dict(btn) for btn in row] for row in keyboard]}
        await query.edit_message_text(
            f"🔗 How many shared accounts for user <code>{target_uid}</code>?\n\nSend a number (0 to disable):",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    elif data == "admin_view_live" or data.startswith("admin_view_live_p:"):
        page = int(data.split(":")[1]) if ":" in data else 1
        await admin_view_live(update, context, page=page)
    elif data == "admin_view_expired" or data.startswith("admin_view_exp_p:"):
        page = int(data.split(":")[1]) if ":" in data else 1
        await admin_view_expired(update, context, page=page)
    elif data == "noop":
        try:
            await query.answer()
        except Exception:
            pass
    elif data == "admin_remove_prompt":
        await admin_remove_prompt(update, context)
    elif data == "admin_remove_all_prompt":
        await admin_remove_all_prompt(update, context)
    elif data == "admin_remove_all_confirm":
        await admin_remove_all_confirm(update, context)
    elif data == "admin_remove_all_expired":
        await admin_remove_all_expired(update, context)
    elif data == "user_remove_prompt":
        await user_remove_prompt(update, context)
    elif data == "give_access":
        await give_access_start(update, context)
    elif data == "remove_access":
        await remove_access_start(update, context)
    elif data == "access_more_yes":
        await access_more_yes(update, context)
    elif data == "access_more_no_direct":
        await access_more_no_direct(update, context)
    elif data == "admin_export_sessions":
        if not is_owner(query.from_user.id) and not is_admin_user(query.from_user.id):
            await query.answer("❌ Only Owner/Admin can export sessions!", show_alert=True)
            return
        await query.answer("📦 Exporting sessions...", show_alert=False)
        await do_export_sessions(update, context)
    elif data == "admin_import_sessions":
        if not is_owner(query.from_user.id) and not is_admin_user(query.from_user.id):
            await query.answer("❌ Only Owner/Admin can import sessions!", show_alert=True)
            return
        await query.answer()
        WAITING_FOR[query.from_user.id] = "import_sessions_zip"
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📥 IMPORT SESSIONS (.ZIP)\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "Upload the sessions ZIP file (generated via Export Sessions or any .session ZIP).\n\n"
            "✨ Ownership Preservation:\n"
            "• If accounts_ownership.json is inside, every account will be restored to its original owner.\n"
            "• If no ownership manifest is found, accounts are added to your account.\n\n"
            "Send the .zip file now:",
            reply_markup=reply_markup
        )
    elif data == "admin_export_db":
        if not is_owner(query.from_user.id) and not is_admin_user(query.from_user.id):
            await query.answer("❌ Only Owner/Admin!", show_alert=True)
            return
        await query.answer()
        await context.bot.send_message(chat_id=query.message.chat_id, text="ℹ️ Use /export_db command to export the database.")
    elif data == "admin_import_db":
        if not is_owner(query.from_user.id) and not is_admin_user(query.from_user.id):
            await query.answer("❌ Only Owner/Admin!", show_alert=True)
            return
        await query.answer()
        WAITING_FOR[query.from_user.id] = "import_db_file"
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_action")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📥 IMPORT DATABASE\n\n"
            "⚠️ WARNING: This will REPLACE the current database!\n\n"
            "Send the automation_bot_export.json file now:",
            reply_markup=reply_markup
        )
    elif data == "admin_broadcast":
        await admin_broadcast(update, context)
    elif data == "premium_reacted":
        await premium_reacted_callback(update, context)
    elif data == "premium_reacted_for_action":
        await premium_reacted_for_action(update, context)
    elif data == "reaction_type_normal":
        await reaction_type_normal(update, context)
    elif data == "reaction_type_premium":
        await reaction_type_premium(update, context)
    elif data == "cancel_action":
        await cancel_button_handler(update, context)

# ========== IDLE CLIENTS & LOGIN CLEANUP ==========
async def cleanup_idle_clients():
    """Periodically cleans up idle Telethon clients and expired OTP/2FA attempts to prevent memory/socket leaks."""
    while True:
        try:
            await asyncio.sleep(60)  # check every 60s
            now = time.time()

            # 1. Clean abandoned OTP logins (older than 15 min)
            for uid, data in list(PENDING_OTP.items()):
                if now - data.get('created_at', now) > 900:
                    cl = data.get('client')
                    if cl and cl.is_connected():
                        try:
                            await cl.disconnect()
                        except Exception:
                            pass
                    PENDING_OTP.pop(uid, None)

            # 2. Clean abandoned 2FA logins (older than 15 min)
            for uid, data in list(PENDING_2FA.items()):
                if now - data.get('created_at', now) > 900:
                    cl = data.get('client')
                    if cl and cl.is_connected():
                        try:
                            await cl.disconnect()
                        except Exception:
                            pass
                    PENDING_2FA.pop(uid, None)

            # 3. Limit active clients in memory if pool grows beyond 350 to prevent socket exhaustion
            if len(ACTIVE_CLIENTS) > 350:
                phones = list(ACTIVE_CLIENTS.keys())
                for p in phones[:-250]:
                    cl = ACTIVE_CLIENTS.pop(p, None)
                    if cl and cl.is_connected():
                        try:
                            await cl.disconnect()
                        except Exception:
                            pass

        except Exception as e:
            logging.error(f"cleanup_idle_clients error: {e}")

# ========== SESSION AUTO-RESTORE & SYNC (CROSS-VPS READY) ==========
def restore_sessions_from_mongodb():
    """Syncs and deduplicates all accounts across MongoDB so all accounts are immediately ready in memory on any VPS."""
    if MONGO_DB is None:
        return
    try:
        sync_cloud_accounts()
        print("☁️ [Cloud DB] All accounts synchronized and deduplicated directly from MongoDB Atlas!")
    except Exception as e:
        logging.error(f"restore_sessions_from_mongodb error: {e}")

async def sync_accounts_on_start():
    """Background task to initialize and verify cloud accounts pool directly from MongoDB Atlas."""
    try:
        logging.info("🔄 Initializing cloud accounts pool...")
        accounts = load_all_bot_accounts()
        frozen_cnt = sum(1 for a in accounts if is_account_frozen(a))
        active_cnt = max(0, len(accounts) - frozen_cnt)
        logging.info(f"✅ Cloud pool ready: {len(accounts)} accounts ({active_cnt} active, {frozen_cnt} frozen).")
    except Exception as e:
        logging.error(f"sync_accounts_on_start error: {e}")

# ========== MAIN ==========
async def main():
    init_db()
    create_user_if_not_exists(OWNER_ID)
    grant_admin(OWNER_ID)
    for admin_id in ADMIN_IDS:
        create_user_if_not_exists(admin_id)
        grant_admin(admin_id)

    os.makedirs("sessions", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    # Reconstitute sessions and sync from MongoDB cloud (zero disk dependency)
    restore_sessions_from_mongodb()

    # Start scheduled checker
    asyncio.create_task(check_scheduled_campaigns())

    # Start idle cleanup
    asyncio.create_task(cleanup_idle_clients())

    # Start background sync
    asyncio.create_task(sync_accounts_on_start())

    global GLOBAL_BOT
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    GLOBAL_BOT = app.bot

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export_db", cmd_export_db))
    app.add_handler(CommandHandler("import_db", cmd_import_db))
    app.add_handler(CommandHandler("export_sessions", cmd_export_sessions))
    app.add_handler(CommandHandler("import_sessions", cmd_import_sessions))
    app.add_handler(CommandHandler("setlog", cmd_set_log_channel))
    app.add_handler(CommandHandler("set_log_channel", cmd_set_log_channel))
    app.add_handler(CommandHandler("getlog", cmd_get_log_channel))
    app.add_handler(CommandHandler("logchannel", cmd_get_log_channel))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    db_label = f"MongoDB ({MONGO_DB_NAME})"
    print("=" * 50)
    print(f"🤖 AUTOMATION VOTE BOT STARTED [{db_label}]!")
    print("=" * 50)
    print(f"✅ Owner ID: {OWNER_ID}")
    print(f"✅ Admin IDs: {ADMIN_IDS}")
    print(f"✅ Log Channel: {get_log_channel_id() or 'Not configured (use /setlog or Admin Panel)'}")
    print("=" * 50)
    print("✅ ALL ACTIONS WORKING (PUBLIC + PRIVATE):")
    print("   - Join Channel ✅")
    print("   - Leave Specific Channel ✅")
    print("   - LEAVE ALL Channels ✅")
    print("   - React Only | Different Reactions ✅")
    print("   - Multiple Reactions (Select Emojis) ✅")
    print("   - Premium Emoji (Auto-Detect) ✅")
    print("   - View Only (GetMessagesViewsRequest) ✅")
    print("   - PRIVATE CHANNEL VIEW (Auto-join + View) ✅")
    print("   - Vote Only | React + Vote | React + View ✅")
    print("   - Vote + View | React + Vote + View ✅")
    print("   - Bulk DM | VC (Voice Chat) ✅")
    print("   - Group Spam ✅")
    print("=" * 50)
    print("✅ SESSION FILE UPLOAD: Direct .session & .session_string support")
    print("✅ ZIP UPLOAD: Single/Multiple sessions from ZIP (auto-cleaned)")
    print("✅ MONGODB STORAGE: Users, accounts, campaigns, schedules, settings stored in Mongo")
    print("✅ ADMIN GRANT: Owner can grant admin rights")
    print("✅ ACCESS MANAGEMENT: Added to Admin Panel")
    print("✅ BROADCAST: Admin can broadcast messages")
    print("✅ MAINTENANCE MODE: Toggleable via Admin Panel")
    print("=" * 50)
    print(f"✅ Active Database: {db_label}")
    print("✅ DB COMMANDS: /export_db | /import_db (JSON)")
    print("✅ SESSIONS BACKUP: /export_sessions | /import_sessions (ZIP)")
    print("=" * 50)

    await app.initialize()
    await app.start()

    def polling_err_callback(exc):
        app.create_task(app.process_error(error=exc, update=None))

    await app.updater.start_polling(drop_pending_updates=True, error_callback=polling_err_callback)
    asyncio.create_task(send_startup_notifications(app.bot))
    print("🤖 Bot is active, polling updates, and ready to respond.")
    try:
        while app.updater and app.updater.running:
            # Watchdog: ensure polling task has not died
            polling_task = getattr(app.updater, '_Updater__polling_task', None)
            if polling_task and polling_task.done():
                exc = None
                try:
                    exc = polling_task.exception()
                except Exception:
                    pass
                logging.error(f"⚠️ Telegram polling task died (exc: {exc})! Exiting for auto-restart...")
                break

            # Watchdog: ensure update fetcher task has not died
            fetcher_task = getattr(app, '_Application__update_fetcher_task', None)
            if fetcher_task and fetcher_task.done():
                exc = None
                try:
                    exc = fetcher_task.exception()
                except Exception:
                    pass
                logging.error(f"⚠️ Update fetcher task died (exc: {exc})! Exiting for auto-restart...")
                break

            await asyncio.sleep(2)
        logging.warning("⚠️ Updater stopped running. Exiting for start.sh auto-restart...")
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        print("\n⏳ Stopping bot and disconnecting active sessions...")
        for phone, client in list(ACTIVE_CLIENTS.items()):
            try:
                if client and client.is_connected():
                    await client.disconnect()
            except Exception:
                pass
        ACTIVE_CLIENTS.clear()
        try:
            if app.updater and app.updater.running:
                await app.updater.stop()
            await app.stop()
            await app.shutdown()
        except Exception:
            pass
        print("✅ Clean shutdown completed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\n🛑 Bot stopped")
s
