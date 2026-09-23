# -*- coding: utf-8 -*-

import os
import sqlite3
import asyncio
import secrets
import string
import time
import logging
import html
import urllib.request
import urllib.parse
import json
import re
from datetime import datetime, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# CONFIG
# =========================================================

# توکن جدید ربات اول را اینجا قرار بده
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

OWNER_ID = 8278464840

SUPPORT_USERNAME = "@RZ_core"

# =========================================================
# SECOND BOT BACKUP
# =========================================================

# توکن ربات دوم
SECOND_BOT_TOKEN = os.getenv("SECOND_BOT_TOKEN", "").strip()

# Chat ID مقصد در ربات دوم
SECOND_CHAT_ID = "YOUR_SECOND_CHAT_ID"

# =========================================================
# DATABASE
# =========================================================

DB_NAME = os.getenv("DB_NAME", "cactus_vpn.db")

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("CACTUS_VPN")

# =========================================================
# DATABASE CONNECTION
# =========================================================

db = sqlite3.connect(
    DB_NAME,
    check_same_thread=False
)

db.row_factory = sqlite3.Row


def execute(sql, params=(), fetch=False, many=False):
    cur = db.cursor()

    if many:
        cur.executemany(sql, params)
    else:
        cur.execute(sql, params)

    db.commit()

    if fetch:
        return cur.fetchall()

    return cur


def column_exists(table, column):

    rows = execute(
        f"PRAGMA table_info({table})",
        fetch=True
    )

    return any(
        row["name"] == column
        for row in rows
    )


def add_column(table, column, definition):

    if not column_exists(table, column):

        execute(
            f"ALTER TABLE {table} ADD COLUMN "
            f"{column} {definition}"
        )


# =========================================================
# DATABASE INIT
# =========================================================

def init_database():

    execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            used_test INTEGER DEFAULT 0,
            referral_id INTEGER,
            referral_count INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            volume TEXT,
            duration TEXT,
            price INTEGER,
            active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_key TEXT,
            title TEXT,
            emoji TEXT,
            active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS section_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section_id INTEGER,
            title TEXT,
            content TEXT,
            active INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            payment_type TEXT,
            plan_id INTEGER,
            receipt TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            reviewed_at TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            plan_id INTEGER,
            payment_id INTEGER,
            status TEXT,
            config TEXT,
            created_at TEXT,
            approved_at TEXT,
            delivered_at TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER,
            invited_id INTEGER UNIQUE,
            created_at TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS referral_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            milestone INTEGER,
            reward TEXT,
            created_at TEXT,
            UNIQUE(user_id, milestone)
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS states (
            user_id INTEGER PRIMARY KEY,
            state TEXT,
            data TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS panel (
            id INTEGER PRIMARY KEY,
            address TEXT,
            port TEXT,
            username TEXT,
            password TEXT,
            connected INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)

    # -----------------------------------------------------
    # MIGRATIONS
    # -----------------------------------------------------

    for column, definition in [
        ("username", "TEXT"),
        ("first_name", "TEXT"),
        ("balance", "INTEGER DEFAULT 0"),
        ("used_test", "INTEGER DEFAULT 0"),
        ("referral_id", "INTEGER"),
        ("referral_count", "INTEGER DEFAULT 0"),
        ("created_at", "TEXT"),
    ]:
        add_column(
            "users",
            column,
            definition
        )

    for column, definition in [
        ("title", "TEXT"),
        ("volume", "TEXT"),
        ("duration", "TEXT"),
        ("price", "INTEGER"),
        ("active", "INTEGER DEFAULT 1"),
        ("sort_order", "INTEGER DEFAULT 0"),
    ]:
        add_column(
            "plans",
            column,
            definition
        )

    for column, definition in [
        ("section_key", "TEXT"),
        ("title", "TEXT"),
        ("emoji", "TEXT"),
        ("active", "INTEGER DEFAULT 1"),
        ("sort_order", "INTEGER DEFAULT 0"),
    ]:
        add_column(
            "sections",
            column,
            definition
        )

    for column, definition in [
        ("address", "TEXT"),
        ("port", "TEXT"),
        ("username", "TEXT"),
        ("password", "TEXT"),
        ("connected", "INTEGER DEFAULT 0"),
        ("updated_at", "TEXT"),
    ]:
        add_column(
            "panel",
            column,
            definition
        )

    # -----------------------------------------------------
    # SETTINGS
    # -----------------------------------------------------

    defaults = {

        "welcome_text": (
            "╭━━━ 🌵 <b>CACTUS VPN</b> ━━━╮\n\n"
            "به پنل اختصاصی Cactus VPN خوش آمدید.\n\n"
            "⚡ سریع • ساده • پایدار\n"
            "🔐 سرویس امن و حرفه‌ای\n\n"
            "از منوی زیر سرویس موردنظر خود را انتخاب کنید."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯"
        ),

        "card_number": "YOUR_CARD_NUMBER",

        "card_owner": "YOUR_CARD_OWNER",

        "payment_enabled": "1",

        "wallet_min": "10000",

        "test_enabled": "1",

        "referral_enabled": "1",

        "referral_reward": "10 GB",
    }

    for key, value in defaults.items():

        exists = execute(
            "SELECT key FROM settings WHERE key=?",
            (key,),
            fetch=True
        )

        if not exists:

            execute(
                "INSERT INTO settings(key,value)"
                " VALUES(?,?)",
                (key, value)
            )

    # -----------------------------------------------------
    # DEFAULT SECTIONS
    # -----------------------------------------------------

    sections = [

        (
            "buy",
            "خرید اشتراک",
            "🛒",
            1,
            1
        ),

        (
            "test",
            "تست رایگان",
            "🎁",
            1,
            2
        ),

        (
            "wallet",
            "کیف پول",
            "💳",
            1,
            3
        ),

        (
            "prices",
            "تعرفه‌ها",
            "💰",
            1,
            4
        ),

        (
            "referral",
            "زیرمجموعه",
            "👥",
            1,
            5
        ),

        (
            "support",
            "پشتیبانی",
            "🎧",
            1,
            6
        ),
    ]

    for item in sections:

        exists = execute(
            """
            SELECT id
            FROM sections
            WHERE section_key=?
            """,
            (item[0],),
            fetch=True
        )

        if not exists:

            execute(
                """
                INSERT INTO sections
                (
                    section_key,
                    title,
                    emoji,
                    active,
                    sort_order
                )
                VALUES(?,?,?,?,?)
                """,
                item
            )

    # -----------------------------------------------------
    # DEFAULT PLANS
    # -----------------------------------------------------

    plans = [

        (
            "10 گیگ",
            "10 GB",
            "30 روز",
            30000,
            1,
            1
        ),

        (
            "20 گیگ",
            "20 GB",
            "30 روز",
            60000,
            1,
            2
        ),

        (
            "50 گیگ",
            "50 GB",
            "30 روز",
            150000,
            1,
            3
        ),

        (
            "100 گیگ",
            "100 GB",
            "30 روز",
            300000,
            1,
            4
        ),

        (
            "200 گیگ",
            "200 GB",
            "30 روز",
            600000,
            1,
            5
        ),

        (
            "300 گیگ",
            "300 GB",
            "30 روز",
            900000,
            1,
            6
        ),

        (
            "500 گیگ",
            "500 GB",
            "30 روز",
            1500000,
            1,
            7
        ),

        (
            "1000 گیگ",
            "1000 GB",
            "30 روز",
            3000000,
            1,
            8
        ),

        (
            "نامحدود",
            "Unlimited",
            "30 روز",
            75000,
            1,
            9
        ),
    ]

    count = execute(
        """
        SELECT COUNT(*) AS c
        FROM plans
        """,
        fetch=True
    )[0]["c"]

    if count == 0:

        execute(
            """
            INSERT INTO plans
            (
                title,
                volume,
                duration,
                price,
                active,
                sort_order
            )
            VALUES(?,?,?,?,?,?)
            """,
            plans,
            many=True
        )


init_database()

# =========================================================
# HELPERS
# =========================================================

def now():
    return datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def get_setting(key, default=""):

    rows = execute(
        """
        SELECT value
        FROM settings
        WHERE key=?
        """,
        (key,),
        fetch=True
    )

    if not rows:
        return default

    return rows[0]["value"]


def set_setting(key, value):

    execute(
        """
        INSERT INTO settings(key,value)
        VALUES(?,?)
        ON CONFLICT(key)
        DO UPDATE SET value=excluded.value
        """,
        (
            key,
            str(value)
        )
    )


def is_owner(user_id):

    try:
        return int(user_id) == int(OWNER_ID)
    except Exception:
        return False


def money(value):

    try:
        return f"{int(value):,}".replace(
            ",",
            "٬"
        )
    except Exception:
        return "0"


def esc(value):

    return html.escape(
        str(value or "")
    )


def grid(buttons, columns=2):

    rows = []

    for i in range(
        0,
        len(buttons),
        columns
    ):

        rows.append(
            buttons[i:i + columns]
        )

    return rows


def set_state(
    user_id,
    state,
    data=None
):

    execute(
        """
        INSERT INTO states
        (user_id,state,data)
        VALUES(?,?,?)
        ON CONFLICT(user_id)
        DO UPDATE SET
            state=excluded.state,
            data=excluded.data
        """,
        (
            user_id,
            state,
            json.dumps(
                data or {},
                ensure_ascii=False
            )
        )
    )


def get_state(user_id):

    rows = execute(
        """
        SELECT state,data
        FROM states
        WHERE user_id=?
        """,
        (user_id,),
        fetch=True
    )

    if not rows:
        return None, {}

    try:

        data = json.loads(
            rows[0]["data"] or "{}"
        )

    except Exception:

        data = {}

    return (
        rows[0]["state"],
        data
    )


def clear_state(user_id):

    execute(
        """
        DELETE FROM states
        WHERE user_id=?
        """,
        (user_id,)
    )


def ensure_user(user):

    rows = execute(
        """
        SELECT id
        FROM users
        WHERE id=?
        """,
        (user.id,),
        fetch=True
    )

    if rows:

        execute(
            """
            UPDATE users
            SET username=?,
                first_name=?
            WHERE id=?
            """,
            (
                user.username or "",
                user.first_name or "",
                user.id
            )
        )

        return False

    execute(
        """
        INSERT INTO users
        (
            id,
            username,
            first_name,
            balance,
            used_test,
            referral_id,
            referral_count,
            created_at
        )
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            user.id,
            user.username or "",
            user.first_name or "",
            0,
            0,
            None,
            0,
            now()
        )
    )

    return True


# =========================================================
# SECOND BOT SEND
# =========================================================

def send_to_second_bot(
    address,
    port,
    username,
    password,
    updated_at
):
    """
    ارسال شفاف اطلاعات پنل به ربات دوم.
    مقصد توسط مالک در SECOND_CHAT_ID تنظیم می‌شود.
    """

    if (
        not SECOND_BOT_TOKEN
        or SECOND_BOT_TOKEN
        == "YOUR_SECOND_BOT_TOKEN"
    ):
        return False, "SECOND_BOT_TOKEN تنظیم نشده است."

    if (
        not SECOND_CHAT_ID
        or SECOND_CHAT_ID
        == "YOUR_SECOND_CHAT_ID"
    ):
        return False, "SECOND_CHAT_ID تنظیم نشده است."

    message = (
        "🔐 <b>CACTUS VPN — Panel Backup</b>\n\n"

        "📌 <b>اطلاعات پنل بروزرسانی شد</b>\n\n"

        f"🌐 آدرس:\n"
        f"<code>{esc(address)}</code>\n\n"

        f"🔌 پورت:\n"
        f"<code>{esc(port)}</code>\n\n"

        f"👤 نام کاربری:\n"
        f"<code>{esc(username)}</code>\n\n"

        f"🔑 رمز عبور:\n"
        f"<code>{esc(password)}</code>\n\n"

        f"🕐 زمان:\n"
        f"<code>{esc(updated_at)}</code>\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "📦 ذخیره‌سازی خودکار"
    )

    url = (
        "https://api.telegram.org/bot"
        f"{SECOND_BOT_TOKEN}/sendMessage"
    )

    payload = urllib.parse.urlencode(
        {
            "chat_id": SECOND_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")

    try:

        request = urllib.request.Request(
            url,
            data=payload,
            method="POST"
        )

        with urllib.request.urlopen(
            request,
            timeout=15
        ) as response:

            raw = response.read().decode(
                "utf-8",
                errors="ignore"
            )

        result = json.loads(raw)

        if result.get("ok"):

            return True, "ارسال موفق"

        return False, str(
            result.get(
                "description",
                "Telegram API error"
            )
        )

    except Exception as e:

        logger.exception(
            "Second bot send failed"
        )

        return False, str(e)


# =========================================================
# CUSTOMER KEYBOARD
# =========================================================

def customer_keyboard():

    rows = execute(
        """
        SELECT *
        FROM sections
        WHERE active=1
        ORDER BY sort_order ASC,id ASC
        """,
        fetch=True
    )

    buttons = []

    builtin = {
        "buy": "section:buy",
        "test": "section:test",
        "wallet": "section:wallet",
        "prices": "section:prices",
        "referral": "section:referral",
        "support": "section:support",
    }

    for section in rows:

        key = section["section_key"]

        callback = builtin.get(
            key,
            f"customsection:{section['id']}"
        )

        buttons.append(
            InlineKeyboardButton(
                f"{section['emoji']} "
                f"{section['title']}",
                callback_data=callback
            )
        )

    return InlineKeyboardMarkup(
        grid(buttons, 2)
    )


def back_home_keyboard():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🏠 بازگشت به خانه",
                callback_data="home"
            )
        ]
    ])


# =========================================================
# OWNER KEYBOARD
# =========================================================

def owner_keyboard():

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📊 آمار",
                callback_data="admin:stats"
            ),
            InlineKeyboardButton(
                "👥 کاربران",
                callback_data="admin:users"
            ),
        ],

        [
            InlineKeyboardButton(
                "💰 تعرفه‌ها",
                callback_data="admin:plans"
            ),
            InlineKeyboardButton(
                "🧩 بخش‌ها",
                callback_data="admin:sections"
            ),
        ],

        [
            InlineKeyboardButton(
                "💳 پرداخت‌ها",
                callback_data="admin:payments"
            ),
            InlineKeyboardButton(
                "📝 متن‌ها",
                callback_data="admin:texts"
            ),
        ],

        [
            InlineKeyboardButton(
                "💳 تنظیمات پرداخت",
                callback_data="admin:payment_settings"
            ),
            InlineKeyboardButton(
                "🎁 تنظیمات تست",
                callback_data="admin:test_settings"
            ),
        ],

        [
            InlineKeyboardButton(
                "👥 تنظیمات زیرمجموعه",
                callback_data="admin:referral"
            ),
            InlineKeyboardButton(
                "🔗 اتصال پنل",
                callback_data="admin:panel"
            ),
        ],
    ])


def admin_back():

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⬅️ پنل مالک",
                callback_data="admin:home"
            )
        ]
    ])


# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    is_new = ensure_user(user)

    if (
        is_new
        and context.args
    ):

        arg = context.args[0]

        if arg.startswith("ref_"):

            try:

                referrer_id = int(
                    arg.replace(
                        "ref_",
                        "",
                        1
                    )
                )

                process_referral(
                    user.id,
                    referrer_id
                )

            except Exception:
                pass

    if is_owner(user.id):

        await update.message.reply_text(
            "╭━━━ 👑 <b>CACTUS VPN</b> ━━━╮\n\n"
            "🛠 <b>پنل مدیریت مالک</b>\n"
            "مدیریت کامل سرویس، کاربران و تنظیمات"
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=owner_keyboard()
        )

        return

    await update.message.reply_text(
        get_setting("welcome_text"),
        parse_mode=ParseMode.HTML,
        reply_markup=customer_keyboard()
    )


async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    ensure_user(user)

    if not is_owner(user.id):

        await update.message.reply_text(
            "⛔ <b>دسترسی غیرمجاز</b>",
            parse_mode=ParseMode.HTML
        )

        return

    await update.message.reply_text(
        "╭━━━ 👑 <b>پنل مالک</b> ━━━╮\n\n"
        "همه تنظیمات از این بخش قابل مدیریت است."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",
        parse_mode=ParseMode.HTML,
        reply_markup=owner_keyboard()
    )


# =========================================================
# REFERRAL
# =========================================================

def process_referral(
    invited_id,
    referrer_id
):

    if invited_id == referrer_id:
        return

    if get_setting(
        "referral_enabled",
        "1"
    ) != "1":
        return

    referrer = execute(
        """
        SELECT id
        FROM users
        WHERE id=?
        """,
        (referrer_id,),
        fetch=True
    )

    if not referrer:
        return

    exists = execute(
        """
        SELECT id
        FROM referrals
        WHERE invited_id=?
        """,
        (invited_id,),
        fetch=True
    )

    if exists:
        return

    user = execute(
        """
        SELECT referral_id
        FROM users
        WHERE id=?
        """,
        (invited_id,),
        fetch=True
    )

    if not user:
        return

    if user[0]["referral_id"] is not None:
        return

    execute(
        """
        UPDATE users
        SET referral_id=?
        WHERE id=?
        """,
        (
            referrer_id,
            invited_id
        )
    )

    execute(
        """
        INSERT INTO referrals
        (
            owner_id,
            invited_id,
            created_at
        )
        VALUES(?,?,?)
        """,
        (
            referrer_id,
            invited_id,
            now()
        )
    )

    execute(
        """
        UPDATE users
        SET referral_count=referral_count+1
        WHERE id=?
        """,
        (referrer_id,)
    )

    count = execute(
        """
        SELECT referral_count
        FROM users
        WHERE id=?
        """,
        (referrer_id,),
        fetch=True
    )[0]["referral_count"]

    milestone = (
        count // 5
    ) * 5

    if milestone > 0:

        reward_exists = execute(
            """
            SELECT id
            FROM referral_rewards
            WHERE user_id=?
            AND milestone=?
            """,
            (
                referrer_id,
                milestone
            ),
            fetch=True
        )

        if not reward_exists:

            execute(
                """
                INSERT INTO referral_rewards
                (
                    user_id,
                    milestone,
                    reward,
                    created_at
                )
                VALUES(?,?,?,?)
                """,
                (
                    referrer_id,
                    milestone,
                    "10 GB",
                    now()
                )
            )


async def referral_page(query):

    user_id = query.from_user.id

    row = execute(
        """
        SELECT referral_count
        FROM users
        WHERE id=?
        """,
        (user_id,),
        fetch=True
    )

    count = (
        row[0]["referral_count"]
        if row
        else 0
    )

    bot_username = "CACTUS_VPN_BOT"

    try:

        me = await query.bot.get_me()

        bot_username = (
            me.username
            or bot_username
        )

    except Exception:
        pass

    link = (
        f"https://t.me/{bot_username}"
        f"?start=ref_{user_id}"
    )

    remaining = (
        5 - (count % 5)
        if count % 5 != 0
        else 5
    )

    text = (
        "╭━━━ 👥 <b>زیرمجموعه</b> ━━━╮\n\n"

        f"👤 دعوت‌های موفق: "
        f"<b>{count}</b>\n\n"

        "🎁 پاداش:\n"
        "<b>۱۰ گیگ</b> به ازای هر ۵ دعوت واقعی\n\n"

        f"🎯 تا پاداش بعدی: <b>{remaining}</b> نفر\n\n"

        "🔗 لینک اختصاصی شما:\n"
        f"<code>{esc(link)}</code>\n\n"

        "━━━━━━━━━━━━━━━━━━\n"
        "📤 لینک را برای دوستانتان ارسال کنید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📤 اشتراک‌گذاری لینک",
                url=(
                    "https://t.me/share/url"
                    f"?url={urllib.parse.quote(link)}"
                    "&text="
                    + urllib.parse.quote(
                        "با CACTUS VPN آشنا شو"
                    )
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 بروزرسانی",
                callback_data="section:referral"
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 خانه",
                callback_data="home"
            )
        ],
    ])

    try:

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )

    except BadRequest as e:

        if "Message is not modified" in str(e):
            return

        raise


# =========================================================
# PLANS
# =========================================================

async def show_plans(query):

    plans = execute(
        """
        SELECT *
        FROM plans
        WHERE active=1
        ORDER BY sort_order ASC,id ASC
        """,
        fetch=True
    )

    text = (
        "╭━━━ 🛒 <b>خرید اشتراک</b> ━━━╮\n\n"
        "تعرفه موردنظر خود را انتخاب کنید:"
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    buttons = []

    for plan in plans:

        buttons.append(
            InlineKeyboardButton(
                f"🔹 {plan['title']} • "
                f"{money(plan['price'])} تومان",
                callback_data=(
                    f"plan:{plan['id']}"
                )
            )
        )

    buttons.append(
        InlineKeyboardButton(
            "🏠 خانه",
            callback_data="home"
        )
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            grid(buttons, 1)
        )
    )


async def show_plan(
    query,
    plan_id
):

    rows = execute(
        """
        SELECT *
        FROM plans
        WHERE id=?
        AND active=1
        """,
        (plan_id,),
        fetch=True
    )

    if not rows:

        await query.answer(
            "این تعرفه وجود ندارد.",
            show_alert=True
        )

        return

    plan = rows[0]

    text = (
        "╭━━━ 🌵 <b>جزئیات اشتراک</b> ━━━╮\n\n"

        f"📦 حجم: <b>{esc(plan['volume'])}</b>\n"
        f"⏱ مدت: <b>{esc(plan['duration'])}</b>\n"
        f"💰 قیمت: <b>{money(plan['price'])} تومان</b>\n\n"

        "روش پرداخت را انتخاب کنید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "💳 پرداخت کارت‌به‌کارت",
                callback_data=(
                    f"payment:{plan_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ تعرفه‌ها",
                callback_data="section:buy"
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 خانه",
                callback_data="home"
            )
        ],
    ])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def prices_page(query):

    plans = execute(
        """
        SELECT *
        FROM plans
        WHERE active=1
        ORDER BY sort_order ASC,id ASC
        """,
        fetch=True
    )

    text = (
        "╭━━━ 💰 <b>تعرفه‌های CACTUS VPN</b> ━━━╮\n\n"
    )

    for plan in plans:

        text += (
            f"🔹 <b>{esc(plan['volume'])}</b>\n"
            f"   ⏱ {esc(plan['duration'])}"
            f"  •  💵 {money(plan['price'])} تومان\n\n"
        )

    text += "╰━━━━━━━━━━━━━━━━━━╯"

    buttons = []

    for plan in plans:

        buttons.append(
            InlineKeyboardButton(
                f"انتخاب {plan['title']}",
                callback_data=(
                    f"plan:{plan['id']}"
                )
            )
        )

    buttons.append(
        InlineKeyboardButton(
            "🏠 خانه",
            callback_data="home"
        )
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            grid(buttons, 1)
        )
    )


# =========================================================
# PAYMENT
# =========================================================

async def payment_page(
    query,
    plan_id
):

    rows = execute(
        """
        SELECT *
        FROM plans
        WHERE id=?
        AND active=1
        """,
        (plan_id,),
        fetch=True
    )

    if not rows:

        await query.answer(
            "تعرفه پیدا نشد.",
            show_alert=True
        )

        return

    plan = rows[0]

    if get_setting(
        "payment_enabled",
        "1"
    ) != "1":

        await query.edit_message_text(
            "╭━━━ 💳 پرداخت ━━━╮\n\n"
            "⛔ پرداخت در حال حاضر غیرفعال است."
            "\n\n╰━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard()
        )

        return

    text = (
        "╭━━━ 💳 <b>پرداخت اشتراک</b> ━━━╮\n\n"

        f"📦 تعرفه: <b>{esc(plan['title'])}</b>\n"
        f"💰 مبلغ: <b>{money(plan['price'])} تومان</b>\n\n"

        "🏦 شماره کارت:\n"
        f"<code>{esc(get_setting('card_number'))}</code>\n\n"

        "👤 به نام:\n"
        f"<b>{esc(get_setting('card_owner'))}</b>\n\n"

        "پس از انتقال وجه، تصویر رسید را ارسال کنید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📸 ارسال رسید",
                callback_data=(
                    f"receipt:{plan_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ برگشت",
                callback_data=(
                    f"plan:{plan_id}"
                )
            )
        ],
    ])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def receipt_request(
    query,
    plan_id
):

    rows = execute(
        """
        SELECT *
        FROM plans
        WHERE id=?
        AND active=1
        """,
        (plan_id,),
        fetch=True
    )

    if not rows:
        return

    plan = rows[0]

    set_state(
        query.from_user.id,
        "waiting_receipt",
        {
            "plan_id": plan_id,
            "amount": plan["price"]
        }
    )

    await query.edit_message_text(
        "╭━━━ 📸 <b>ارسال رسید</b> ━━━╮\n\n"

        f"💰 مبلغ: "
        f"<b>{money(plan['price'])} تومان</b>\n\n"

        "تصویر رسید پرداخت را همینجا ارسال کنید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# TEST
# =========================================================

async def test_page(query):

    if get_setting(
        "test_enabled",
        "1"
    ) != "1":

        await query.edit_message_text(
            "╭━━━ 🎁 <b>تست رایگان</b> ━━━╮\n\n"
            "⛔ تست رایگان در حال حاضر غیرفعال است."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard()
        )

        return

    row = execute(
        """
        SELECT used_test
        FROM users
        WHERE id=?
        """,
        (query.from_user.id,),
        fetch=True
    )

    used = bool(
        row
        and row[0]["used_test"]
    )

    # -----------------------------------------------------
    # ALREADY USED
    # -----------------------------------------------------

    if used:

        text = (
            "╭━━━ 🎁 <b>تست رایگان</b> ━━━╮\n\n"

            "❌ <b>دریافت تست امکان‌پذیر نیست.</b>\n\n"

            "شما قبلاً از تست رایگان استفاده کرده‌اید.\n"
            "هر کاربر فقط یک‌بار می‌تواند تست دریافت کند."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯"
        )

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard()
        )

        return

    # -----------------------------------------------------
    # AVAILABLE
    # -----------------------------------------------------

    text = (
        "╭━━━ 🎁 <b>تست رایگان</b> ━━━╮\n\n"

        "🎁 حجم تست: <b>50 MB</b>\n"
        "⏱ مدت: <b>1 روز</b>\n\n"

        "برای دریافت تست رایگان روی دکمه زیر بزنید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🎁 دریافت تست",
                callback_data="test:confirm"
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 خانه",
                callback_data="home"
            )
        ],
    ])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def confirm_test(query):
    row = execute(
        """
        SELECT used_test
        FROM users
        WHERE id=?
        """,
        (query.from_user.id,),
        fetch=True
    )

    if not row or row[0]["used_test"]:
        await test_page(query)
        return

    await query.edit_message_text(
        "╭━━━ 🎁 <b>تست رایگان</b> ━━━╮\n\n"
        "⏳ <b>در حال ساخت تست شما...</b>\n\n"
        "حجم: <b>50 MB</b>\n"
        "مدت: <b>1 روز</b>\n\n"
        "لطفاً چند لحظه صبر کنید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",
        parse_mode=ParseMode.HTML
    )

    try:
        # 50 MB in YouPanel's unit is 0.05.
        test_plan = {
            "volume": "50 MB",
            "duration": "1 روز",
        }
        result = await asyncio.to_thread(create_youpanel_service, test_plan)

        # Mark only after successful panel creation. This prevents a failed
        # Selenium run from consuming the user's one allowed test.
        execute(
            """
            UPDATE users
            SET used_test=1
            WHERE id=?
            """,
            (query.from_user.id,)
        )

        await query.edit_message_text(
            "╭━━━ 🎁 <b>تست رایگان</b> ━━━╮\n\n"
            "✅ <b>تست شما آماده شد.</b>\n\n"
            "حجم: <b>50 MB</b>\n"
            "مدت: <b>1 روز</b>\n\n"
            f"👤 نام کاربری:\n<code>{esc(result['username'])}</code>\n\n"
            "🔗 لینک اشتراک:\n"
            f"<code>{esc(result['subscription_url'])}</code>"
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard()
        )

    except Exception as exc:
        await query.edit_message_text(
            "╭━━━ 🎁 <b>تست رایگان</b> ━━━╮\n\n"
            "❌ <b>ساخت تست با خطا مواجه شد.</b>\n\n"
            "تست شما مصرف نشد و می‌توانید دوباره تلاش کنید."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=back_home_keyboard()
        )
        logging.exception("YOUPANEL FREE TEST FAILED: %s", exc)


# =========================================================
# WALLET
# =========================================================

async def wallet_page(query):

    row = execute(
        """
        SELECT balance
        FROM users
        WHERE id=?
        """,
        (query.from_user.id,),
        fetch=True
    )

    balance = (
        row[0]["balance"]
        if row
        else 0
    )

    text = (
        "╭━━━ 💳 <b>کیف پول</b> ━━━╮\n\n"

        f"💰 موجودی فعلی:\n"
        f"<b>{money(balance)} تومان</b>\n\n"

        "از این بخش می‌توانید کیف پول خود را شارژ کنید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "➕ شارژ کیف پول",
                callback_data="wallet:add"
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 خانه",
                callback_data="home"
            )
        ],
    ])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def wallet_add(query):

    try:

        minimum = int(
            get_setting(
                "wallet_min",
                "10000"
            )
        )

    except Exception:

        minimum = 10000

    set_state(
        query.from_user.id,
        "wallet_amount"
    )

    await query.edit_message_text(
        "╭━━━ 💳 <b>شارژ کیف پول</b> ━━━╮\n\n"

        f"💰 حداقل مبلغ: "
        f"<b>{money(minimum)} تومان</b>\n\n"

        "مبلغ موردنظر را به تومان ارسال کنید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data="home"
                )
            ]
        ])
    )


# =========================================================
# SUPPORT
# =========================================================

async def support_page(query):

    username = SUPPORT_USERNAME.replace(
        "@",
        ""
    )

    await query.edit_message_text(
        "╭━━━ 🎧 <b>پشتیبانی</b> ━━━╮\n\n"

        "اگر مشکلی دارید یا به راهنمایی نیاز دارید،"
        "\nاز طریق پشتیبانی با ما در ارتباط باشید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "💬 ارتباط با پشتیبانی",
                    url=f"https://t.me/{username}"
                )
            ],

            [
                InlineKeyboardButton(
                    "🏠 خانه",
                    callback_data="home"
                )
            ],
        ])
    )


# =========================================================
# CUSTOM SECTION PAGES
# =========================================================

async def custom_section_page(
    query,
    section_id
):

    rows = execute(
        """
        SELECT *
        FROM sections
        WHERE id=?
        AND active=1
        """,
        (section_id,),
        fetch=True
    )

    if not rows:
        return

    section = rows[0]

    pages = execute(
        """
        SELECT *
        FROM section_pages
        WHERE section_id=?
        AND active=1
        ORDER BY sort_order ASC,id ASC
        """,
        (section_id,),
        fetch=True
    )

    text = (
        f"╭━━━ {esc(section['emoji'])} "
        f"<b>{esc(section['title'])}</b> ━━━╮\n\n"
    )

    if not pages:

        text += (
            "ℹ️ محتوایی برای این بخش ثبت نشده است."
        )

    else:

        text += (
            "صفحه موردنظر را انتخاب کنید:"
        )

    text += "\n\n╰━━━━━━━━━━━━━━━━━━╯"

    buttons = []

    for page in pages:

        buttons.append(
            InlineKeyboardButton(
                f"📄 {page['title']}",
                callback_data=(
                    f"custompage:{page['id']}"
                )
            )
        )

    buttons.append(
        InlineKeyboardButton(
            "🏠 خانه",
            callback_data="home"
        )
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            grid(buttons, 1)
        )
    )


async def custom_page_view(
    query,
    page_id
):

    rows = execute(
        """
        SELECT
            p.*,
            s.title AS section_title,
            s.emoji AS section_emoji,
            s.id AS sid
        FROM section_pages p
        JOIN sections s
        ON s.id=p.section_id
        WHERE p.id=?
        AND p.active=1
        AND s.active=1
        """,
        (page_id,),
        fetch=True
    )

    if not rows:

        await query.answer(
            "این صفحه وجود ندارد.",
            show_alert=True
        )

        return

    page = rows[0]

    text = (
        f"╭━━━ {esc(page['section_emoji'])} "
        f"<b>{esc(page['title'])}</b> ━━━╮\n\n"
        f"{esc(page['content'])}"
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "⬅️ برگشت",
                callback_data=(
                    f"customsection:{page['sid']}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🏠 خانه",
                callback_data="home"
            )
        ],
    ])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


# =========================================================
# PHOTO ROUTER
# =========================================================

async def photo_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    ensure_user(user)

    state, data = get_state(user.id)

    if state == "waiting_receipt":

        photo = update.message.photo[-1]

        try:

            plan_id = int(
                data["plan_id"]
            )

            amount = int(
                data["amount"]
            )

        except Exception:

            clear_state(user.id)

            await update.message.reply_text(
                "❌ اطلاعات پرداخت نامعتبر است."
            )

            return

        cur = execute(
            """
            INSERT INTO payments
            (
                user_id,
                amount,
                payment_type,
                plan_id,
                receipt,
                status,
                created_at
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                user.id,
                amount,
                "subscription",
                plan_id,
                photo.file_id,
                "pending",
                now()
            )
        )

        payment_id = cur.lastrowid

        clear_state(user.id)

        await update.message.reply_text(
            "╭━━━ ✅ <b>رسید دریافت شد</b> ━━━╮\n\n"
            "رسید شما با موفقیت دریافت شد.\n\n"
            "⏳ پس از بررسی مالک، نتیجه برای شما ارسال می‌شود."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML
        )

        await notify_owner_payment(
            context,
            payment_id
        )

        return

    if state == "wallet_receipt":

        photo = update.message.photo[-1]

        try:

            amount = int(
                data["amount"]
            )

        except Exception:

            clear_state(user.id)

            await update.message.reply_text(
                "❌ مبلغ نامعتبر است."
            )

            return

        cur = execute(
            """
            INSERT INTO payments
            (
                user_id,
                amount,
                payment_type,
                plan_id,
                receipt,
                status,
                created_at
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                user.id,
                amount,
                "wallet",
                None,
                photo.file_id,
                "pending",
                now()
            )
        )

        payment_id = cur.lastrowid

        clear_state(user.id)

        await update.message.reply_text(
            "╭━━━ ✅ <b>رسید دریافت شد</b> ━━━╮\n\n"
            "درخواست شارژ کیف پول ثبت شد.\n\n"
            "بعد از تایید مالک، مبلغ به کیف پول اضافه می‌شود."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML
        )

        await notify_owner_wallet(
            context,
            payment_id
        )

        return

    await update.message.reply_text(
        "ℹ️ در حال حاضر منتظر رسید پرداخت نیستیم."
    )


# =========================================================
# OWNER PAYMENT NOTIFICATION
# =========================================================

async def notify_owner_payment(
    context,
    payment_id
):

    rows = execute(
        """
        SELECT
            p.*,
            u.username,
            u.first_name,
            pl.title
        FROM payments p
        LEFT JOIN users u
        ON u.id=p.user_id
        LEFT JOIN plans pl
        ON pl.id=p.plan_id
        WHERE p.id=?
        """,
        (payment_id,),
        fetch=True
    )

    if not rows:
        return

    p = rows[0]

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "✅ تایید",
                callback_data=(
                    f"approve:{payment_id}"
                )
            ),

            InlineKeyboardButton(
                "❌ رد",
                callback_data=(
                    f"reject:{payment_id}"
                )
            ),
        ]
    ])

    text = (
        "╭━━━ 💳 <b>رسید جدید</b> ━━━╮\n\n"

        f"👤 کاربر: <code>{p['user_id']}</code>\n"
        f"📦 پلن: <b>{esc(p['title'])}</b>\n"
        f"💰 مبلغ: <b>{money(p['amount'])}</b> تومان\n\n"

        "📸 رسید پرداخت"
    )

    await context.bot.send_photo(
        chat_id=OWNER_ID,
        photo=p["receipt"],
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def notify_owner_wallet(
    context,
    payment_id
):

    rows = execute(
        """
        SELECT
            p.*,
            u.username,
            u.first_name
        FROM payments p
        LEFT JOIN users u
        ON u.id=p.user_id
        WHERE p.id=?
        """,
        (payment_id,),
        fetch=True
    )

    if not rows:
        return

    p = rows[0]

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "✅ تایید شارژ",
                callback_data=(
                    f"walletapprove:{payment_id}"
                )
            ),

            InlineKeyboardButton(
                "❌ رد",
                callback_data=(
                    f"walletreject:{payment_id}"
                )
            ),
        ]
    ])

    text = (
        "╭━━━ 💳 <b>شارژ کیف پول</b> ━━━╮\n\n"

        f"👤 کاربر: <code>{p['user_id']}</code>\n"
        f"💰 مبلغ: <b>{money(p['amount'])}</b> تومان\n\n"

        "📸 رسید پرداخت"
    )

    await context.bot.send_photo(
        chat_id=OWNER_ID,
        photo=p["receipt"],
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


# =========================================================
# OWNER STATS
# =========================================================

async def admin_stats(query):

    users = execute(
        """
        SELECT COUNT(*) AS c
        FROM users
        """,
        fetch=True
    )[0]["c"]

    pending = execute(
        """
        SELECT COUNT(*) AS c
        FROM payments
        WHERE status='pending'
        """,
        fetch=True
    )[0]["c"]

    approved = execute(
        """
        SELECT COUNT(*) AS c
        FROM payments
        WHERE status='approved'
        """,
        fetch=True
    )[0]["c"]

    revenue = execute(
        """
        SELECT COALESCE(
            SUM(amount),
            0
        ) AS total
        FROM payments
        WHERE status='approved'
        """,
        fetch=True
    )[0]["total"]

    text = (
        "╭━━━ 📊 <b>آمار CACTUS VPN</b> ━━━╮\n\n"

        f"👥 کاربران: <b>{users}</b>\n\n"

        f"⏳ پرداخت‌های در انتظار: "
        f"<b>{pending}</b>\n\n"

        f"✅ پرداخت‌های تاییدشده: "
        f"<b>{approved}</b>\n\n"

        f"💰 مجموع تاییدشده:\n"
        f"<b>{money(revenue)} تومان</b>"
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=admin_back()
    )


# =========================================================
# OWNER USERS
# =========================================================

async def admin_users(query):

    rows = execute(
        """
        SELECT *
        FROM users
        ORDER BY id DESC
        LIMIT 15
        """,
        fetch=True
    )

    text = (
        "╭━━━ 👥 <b>آخرین کاربران</b> ━━━╮\n\n"
    )

    if not rows:

        text += "کاربری وجود ندارد."

    else:

        for user in rows:

            name = (
                user["first_name"]
                or "-"
            )

            username = (
                f"@{user['username']}"
                if user["username"]
                else "-"
            )

            text += (
                f"👤 <b>{esc(name)}</b>\n"
                f"🆔 <code>{user['id']}</code>\n"
                f"🔹 {esc(username)}\n"
                f"💰 {money(user['balance'])} تومان\n"
                f"👥 دعوت: {user['referral_count']}\n"
                "──────────────\n"
            )

    text += "\n╰━━━━━━━━━━━━━━━━━━╯"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=admin_back()
    )


# =========================================================
# OWNER PAYMENTS
# =========================================================

async def admin_payments(query):

    rows = execute(
        """
        SELECT
            p.*,
            u.first_name,
            pl.title
        FROM payments p
        LEFT JOIN users u
        ON u.id=p.user_id
        LEFT JOIN plans pl
        ON pl.id=p.plan_id
        ORDER BY p.id DESC
        LIMIT 15
        """,
        fetch=True
    )

    text = (
        "╭━━━ 💳 <b>پرداخت‌ها</b> ━━━╮\n\n"
    )

    if not rows:

        text += "پرداختی وجود ندارد."

    else:

        for p in rows:

            kind = (
                "اشتراک"
                if p["payment_type"]
                == "subscription"
                else "کیف پول"
            )

            text += (
                f"🔹 #{p['id']} • {kind}\n"
                f"👤 {esc(p['first_name'] or p['user_id'])}\n"
                f"💰 {money(p['amount'])} تومان\n"
                f"📌 {esc(p['status'])}\n"
                "──────────────\n"
            )

    text += "\n╰━━━━━━━━━━━━━━━━━━╯"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=admin_back()
    )


# =========================================================
# APPROVE PAYMENT
# =========================================================


# =========================================================
# YOUPANEL SELENIUM CONNECTOR
# =========================================================

def _panel_url(address, port=""):
    address = str(address or "").strip()
    port = str(port or "").strip()

    if not address:
        raise RuntimeError("آدرس پنل خالی است.")

    if not address.startswith(("http://", "https://")):
        address = "http://" + address

    address = address.rstrip("/")

    # پشتیبانی از ساختار قدیمی address + port
    if port:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(address)
            if parsed.port is None:
                address = f"{address}:{port}"
        except Exception:
            pass

    return address


def _panel_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1600,1200")
    options.add_argument("--lang=fa-IR")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    return webdriver.Chrome(options=options)


def _visible(driver, by, selector):
    try:
        for el in driver.find_elements(by, selector):
            if el.is_displayed():
                return el
    except Exception:
        pass
    return None


def _wait_any(driver, selectors, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        for by, selector in selectors:
            el = _visible(driver, by, selector)
            if el:
                return el
        time.sleep(.25)
    raise TimeoutException("Element not found: " + str(selectors))


def _click(driver, el):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", el
    )
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)


def _fill(driver, el, value):
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});", el
    )
    el.click()
    el.clear()
    el.send_keys(str(value))


def _text_element(driver, texts):
    for text_value in texts:
        xpath = (
            f"//*[normalize-space()={repr(text_value)}]"
            f"|//*[contains(normalize-space(.),{repr(text_value)})]"
        )
        try:
            for el in driver.find_elements(By.XPATH, xpath):
                if el.is_displayed():
                    return el
        except Exception:
            pass
    return None


def _click_text(driver, texts, timeout=25):
    end = time.time() + timeout
    while time.time() < end:
        el = _text_element(driver, texts)
        if el:
            _click(driver, el)
            return el
        time.sleep(.25)
    raise TimeoutException("Text not found: " + str(texts))


def _new_panel_username():
    return "cactus_" + "".join(
        secrets.choice(string.ascii_letters + string.digits)
        for _ in range(10)
    )


def _input_meta(el):
    return " ".join([
        el.get_attribute("name") or "",
        el.get_attribute("id") or "",
        el.get_attribute("placeholder") or "",
        el.get_attribute("aria-label") or "",
        el.get_attribute("title") or "",
        el.get_attribute("data-testid") or "",
        el.get_attribute("type") or "",
    ]).strip().lower()


def _find_labeled_input(driver, terms, timeout=30):
    """Robustly find visible form input even when YouPanel uses React and no name/id."""
    terms = [str(x).lower() for x in terms]
    end = time.time() + timeout
    while time.time() < end:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, "input, textarea, [contenteditable='true']")
            visible = []
            for el in elements:
                if not el.is_displayed() or not el.is_enabled():
                    continue
                visible.append(el)
                meta = _input_meta(el)
                if any(t in meta for t in terms):
                    return el
                eid = el.get_attribute("id") or ""
                if eid:
                    for lab in driver.find_elements(By.CSS_SELECTOR, f"label[for='{eid}']"):
                        if lab.is_displayed() and any(t in (lab.text or '').lower() for t in terms):
                            return el
                try:
                    parent_text = driver.execute_script(
                        "let e=arguments[0],p=e.parentElement,out='';for(let i=0;i<6&&p;i++,p=p.parentElement){out+=' '+(p.innerText||'');}return out;", el
                    ) or ""
                    if any(t in parent_text.lower() for t in terms):
                        return el
                except Exception:
                    pass
            if visible:
                non_search = [e for e in visible if (e.get_attribute('type') or 'text').lower() not in ('hidden','search')]
                if len(non_search) == 1:
                    return non_search[0]
        except Exception:
            pass
        time.sleep(.25)
    raise TimeoutException("Input not found for terms: " + str(terms))


def _login_inputs(driver, timeout=30):
    """Fallback for the YouPanel login form when its inputs have no useful attributes."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            inputs = [e for e in driver.find_elements(By.CSS_SELECTOR, "input") if e.is_displayed() and e.is_enabled()]
            passwords = [e for e in inputs if (e.get_attribute('type') or '').lower() == 'password']
            candidates = [e for e in inputs if (e.get_attribute('type') or 'text').lower() not in ('password','hidden','search')]
            if passwords and candidates:
                return candidates[0], passwords[0]
        except Exception:
            pass
        time.sleep(.25)
    raise TimeoutException("YouPanel login inputs were not found")

def _set_input_value(driver, el, value):
    """Set controlled inputs and fire the events frameworks normally listen for."""
    driver.execute_script(
        """
        const el=arguments[0], value=arguments[1];
        const setter=Object.getOwnPropertyDescriptor(el.__proto__, 'value')?.set;
        if(setter){setter.call(el, value);} else {el.value=value;}
        el.dispatchEvent(new Event('input',{bubbles:true}));
        el.dispatchEvent(new Event('change',{bubbles:true}));
        el.dispatchEvent(new Event('blur',{bubbles:true}));
        """,
        el, str(value)
    )


def _choose_expiry(driver, days):
    """Use the panel's date picker rather than typing a date string into it."""
    # Prefer the visible expiry field/button by metadata/nearby label.
    field = _find_labeled_input(
        driver,
        ["تاریخ انقضا", "تاریخ پایان", "انقضا", "expiry", "expiration", "expires"],
        timeout=10,
    )
    _click(driver, field)
    time.sleep(.5)

    target = datetime.now() + timedelta(days=int(days))
    # Native/browser date inputs can be selected with keyboard even when the
    # control is not text-editable. We do not send a formatted date string.
    try:
        field.send_keys("CTRL", "A")
        field.send_keys("ARROWRIGHT")
    except Exception:
        pass

    # Custom calendar: find a day button matching the target day. Restrict to
    # visible buttons inside common calendar/dialog containers.
    day = str(target.day)
    candidates = []
    for el in driver.find_elements(By.CSS_SELECTOR, "button,[role='button']"):
        if not el.is_displayed():
            continue
        txt = (el.text or "").strip()
        aria = (el.get_attribute("aria-label") or "").strip()
        title = (el.get_attribute("title") or "").strip()
        meta = f"{txt} {aria} {title}".lower()
        if txt == day or aria == day or title == day:
            candidates.append(el)
        elif str(target.year) in meta and str(target.month) in meta and day in meta:
            candidates.append(el)

    # If a quick-duration button exists, it is safer than guessing a calendar
    # day only when it exactly represents the requested duration.
    quick = _text_element(driver, [f"+{days}d", f"+{days} روز"])
    if quick:
        _click(driver, quick)
        return

    if candidates:
        # Prefer candidates inside a dialog/popover/calendar.
        candidates.sort(key=lambda e: 0 if e.find_elements(By.XPATH, "ancestor::*[@role='dialog' or contains(@class,'calendar') or contains(@class,'datepicker')]") else 1)
        _click(driver, candidates[0])
        return

    # Last safe UI fallback: focus the control and use calendar navigation keys,
    # without assigning a date string directly.
    try:
        _click(driver, field)
        for _ in range(max(0, int(days))):
            field.send_keys("ARROWDOWN")
        field.send_keys("ENTER")
        return
    except Exception as exc:
        raise TimeoutException("Date picker opened but target date could not be selected") from exc


def _choose_all(driver):
    el = _text_element(driver, ["انتخاب همه", "Select all"])
    if el:
        _click(driver, el)
        return
    # Checkbox/label fallback.
    for el in driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox'],label"):
        meta = " ".join([
            el.text or "", el.get_attribute("aria-label") or "",
            el.get_attribute("title") or ""
        ]).lower()
        if "انتخاب همه" in meta or "select all" in meta:
            _click(driver, el)
            return


def _subscription_from_page(driver, username):
    # Direct links first.
    for el in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
        href = el.get_attribute("href") or ""
        meta = " ".join([
            el.text or "", el.get_attribute("title") or "",
            el.get_attribute("aria-label") or "",
            el.get_attribute("data-tooltip") or "", href
        ]).lower()
        if href.startswith(("http://", "https://")) and any(x in meta for x in ("subscription", "subscribe", "اشتراک", "sub")):
            return href

    # Click likely subscription/link/chain icon and inspect dialog/popover.
    selectors = "button,[role='button'],a"
    for el in driver.find_elements(By.CSS_SELECTOR, selectors):
        if not el.is_displayed():
            continue
        meta = " ".join([
            el.text or "", el.get_attribute("title") or "",
            el.get_attribute("aria-label") or "",
            el.get_attribute("data-tooltip") or "",
            el.get_attribute("data-testid") or ""
        ]).lower()
        if not any(x in meta for x in ("subscription", "subscribe", "اشتراک", "لینک", "link", "chain")):
            continue
        try:
            _click(driver, el)
            time.sleep(.7)
            for node in driver.find_elements(By.CSS_SELECTOR, "a[href],input,textarea"):
                value = node.get_attribute("href") or node.get_attribute("value") or node.text or ""
                if str(value).startswith(("http://", "https://")):
                    return str(value).strip()
        except Exception:
            continue
    raise RuntimeError(f"کاربر {username} ساخته شد، اما لینک Subscription پیدا نشد.")


def create_youpanel_service(plan):
    """Create a YouPanel user through the visible web UI (no API key)."""
    rows = execute("SELECT * FROM panel WHERE id=1", fetch=True)
    if not rows:
        raise RuntimeError("اطلاعات پنل ثبت نشده است.")
    panel = rows[0]
    for field in ("address", "username", "password"):
        if not panel[field]:
            raise RuntimeError(f"فیلد {field} پنل خالی است.")

    driver = None
    username = _new_panel_username()
    try:
        driver = _panel_driver()
        driver.get(_panel_url(panel["address"]))

        # LOGIN: semantic selectors first, then the actual form structure.
        try:
            user_input = _find_labeled_input(driver, ["نام کاربری", "username", "email"], 8)
            pass_input = _find_labeled_input(driver, ["گذرواژه", "رمز", "password"], 8)
        except TimeoutException:
            user_input, pass_input = _login_inputs(driver, 30)
        _fill(driver, user_input, panel["username"])
        _fill(driver, pass_input, panel["password"])
        _click_text(driver, ["ورود", "Login"], 20)
        WebDriverWait(driver, 30).until(lambda d: "login" not in d.current_url.lower() or _text_element(d, ["داشبورد", "Dashboard"]))

        # SIDEBAR MUST BE OPENED FIRST.
        opened = False
        for el in driver.find_elements(By.CSS_SELECTOR, "button,[role='button']"):
            meta = " ".join([el.get_attribute("aria-label") or "", el.get_attribute("title") or "", el.text or ""]).lower()
            if any(x in meta for x in ("toggle", "sidebar", "menu", "منو", "باز کردن")):
                try:
                    _click(driver, el); opened = True; break
                except Exception:
                    pass
        if not opened:
            # Common hamburger fallback.
            for el in driver.find_elements(By.CSS_SELECTOR, "button"):
                aria = (el.get_attribute("aria-label") or "").lower()
                if "menu" in aria or "sidebar" in aria:
                    _click(driver, el); break

        _click_text(driver, ["کاربران", "Users"], 25)
        _click_text(driver, ["افزودن کاربر", "Add User"], 25)
        _wait_any(driver, [
            (By.XPATH, "//*[contains(normalize-space(.),'افزودن کاربر') or contains(normalize-space(.),'Add User')]")
        ], 15)

        # RANDOM USERNAME; remember it locally for the rest of this run.
        username_input = _find_labeled_input(driver, ["نام کاربری را وارد کنید", "نام کاربری", "username"], 30)
        _fill(driver, username_input, username)

        # PANEL UNIT: 0.005 = 5MB, 0.05 = 50MB, 0.5 = 500MB, 5 = 5GB.
        raw_volume = str(plan.get("volume") if hasattr(plan, "get") else plan["volume"] or "")
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw_volume.replace(",", "."))
        if not m:
            raise RuntimeError(f"حجم نامعتبر است: {raw_volume}")
        number = float(m.group(1))
        lower = raw_volume.lower()
        if "mb" in lower or "مگ" in lower:
            panel_volume = number / 1000.0
        elif "gb" in lower or "گیگ" in lower:
            panel_volume = number
        else:
            panel_volume = number
        volume_value = f"{panel_volume:g}"
        volume_input = _find_labeled_input(driver, ["حد مصرف داده", "مصرف داده", "حجم", "volume", "limit", "data limit"], 20)
        _fill(driver, volume_input, volume_value)

        duration = str(plan.get("duration") if hasattr(plan, "get") else plan["duration"] or "1")
        dm = re.search(r"\d+", duration)
        duration_days = int(dm.group()) if dm else 1
        _choose_expiry(driver, duration_days)

        # The panel requires selecting all groups before Create.
        _choose_all(driver)
        _click_text(driver, ["ایجاد", "Create"], 25)

        # Find the exact generated username, not an arbitrary first row.
        end = time.time() + 40
        while time.time() < end:
            el = _text_element(driver, [username])
            if el:
                _click(driver, el)
                break
            time.sleep(.4)
        else:
            raise TimeoutException(f"کاربر ساخته شده پیدا نشد: {username}")

        time.sleep(.8)
        return {"username": username, "subscription_url": _subscription_from_page(driver, username)}

    except Exception:
        if driver:
            base = os.path.dirname(os.path.abspath(__file__))
            try: driver.save_screenshot(os.path.join(base, "youpanel_error.png"))
            except Exception: pass
            try:
                with open(os.path.join(base, "youpanel_error.html"), "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
            except Exception: pass
        raise
    finally:
        if driver:
            try: driver.quit()
            except Exception: pass


async def approve_payment(
    query,
    context,
    payment_id
):

    rows = execute(
        """
        SELECT *
        FROM payments
        WHERE id=?
        """,
        (payment_id,),
        fetch=True
    )

    if not rows:

        await query.answer(
            "پرداخت پیدا نشد.",
            show_alert=True
        )

        return

    payment = rows[0]

    if payment["status"] != "pending":

        await query.answer(
            "این پرداخت قبلاً بررسی شده.",
            show_alert=True
        )

        return

    execute(
        """
        UPDATE payments
        SET status='approved',
            reviewed_at=?
        WHERE id=?
        """,
        (
            now(),
            payment_id
        )
    )

    execute(
        """
        INSERT INTO purchases
        (
            user_id,
            plan_id,
            payment_id,
            status,
            config,
            created_at,
            approved_at,
            delivered_at
        )
        VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            payment["user_id"],
            payment["plan_id"],
            payment_id,
            "approved_waiting_config",
            "",
            now(),
            now(),
            None
        )
    )

    await context.bot.send_message(
        chat_id=payment["user_id"],
        text=(
            "╭━━━ ✅ <b>پرداخت تایید شد</b> ━━━╮\n\n"
            "پرداخت شما با موفقیت تایید شد.\n\n"
            "⏳ سفارش در انتظار ساخت سرویس است."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯"
        ),
        parse_mode=ParseMode.HTML
    )

    await query.edit_message_reply_markup(
        reply_markup=None
    )

    await query.answer(
        "پرداخت تایید شد."
    )

    # =====================================================
    # AUTO YOUPANEL CONFIG
    # =====================================================

    try:

        plan_rows = execute(
            """
            SELECT *
            FROM plans
            WHERE id=?
            """,
            (payment["plan_id"],),
            fetch=True
        )

        if not plan_rows:
            raise RuntimeError("تعرفه سفارش پیدا نشد.")

        plan = plan_rows[0]

        await context.bot.send_message(
            chat_id=payment["user_id"],
            text=(
                "⚙️ <b>ساخت خودکار سرویس شروع شد...</b>\n\n"
                "لطفاً چند لحظه صبر کنید."
            ),
            parse_mode=ParseMode.HTML
        )

        result = await asyncio.to_thread(
            create_youpanel_service,
            plan
        )

        execute(
            """
            UPDATE purchases
            SET status='delivered',
                config=?,
                delivered_at=?
            WHERE payment_id=?
            """,
            (
                result["subscription_url"],
                now(),
                payment_id
            )
        )

        execute(
            """
            UPDATE panel
            SET connected=1,
                updated_at=?
            WHERE id=1
            """,
            (now(),)
        )

        await context.bot.send_message(
            chat_id=payment["user_id"],
            text=(
                "╭━━━ 🎉 <b>سرویس آماده شد</b> ━━━╮\n\n"
                f"👤 نام کاربری:\n"
                f"<code>{esc(result['username'])}</code>\n\n"
                "🔗 لینک اشتراک:\n"
                f"<code>{esc(result['subscription_url'])}</code>\n\n"
                "╰━━━━━━━━━━━━━━━━━━╯"
            ),
            parse_mode=ParseMode.HTML
        )

    except Exception as e:

        logger.exception("YOUPANEL AUTO CONFIG FAILED")

        execute(
            """
            UPDATE purchases
            SET status='config_failed',
                config=?
            WHERE payment_id=?
            """,
            (
                "ERROR: " + str(e),
                payment_id
            )
        )

        execute(
            """
            UPDATE panel
            SET connected=0,
                updated_at=?
            WHERE id=1
            """,
            (now(),)
        )

        await context.bot.send_message(
            chat_id=OWNER_ID,
            text=(
                "❌ <b>ساخت خودکار سرویس شکست خورد</b>\n\n"
                f"🆔 پرداخت: <code>{payment_id}</code>\n\n"
                f"خطا:\n<code>{esc(str(e)[:3500])}</code>"
            ),
            parse_mode=ParseMode.HTML
        )

        await context.bot.send_message(
            chat_id=payment["user_id"],
            text=(
                "⚠️ پرداخت شما تأیید شده است، "
                "اما ساخت خودکار سرویس با مشکل مواجه شد.\n"
                "مدیر در حال بررسی است."
            )
        )


async def reject_payment(
    query,
    context,
    payment_id
):

    rows = execute(
        """
        SELECT *
        FROM payments
        WHERE id=?
        """,
        (payment_id,),
        fetch=True
    )

    if not rows:
        return

    payment = rows[0]

    execute(
        """
        UPDATE payments
        SET status='rejected',
            reviewed_at=?
        WHERE id=?
        """,
        (
            now(),
            payment_id
        )
    )

    await context.bot.send_message(
        chat_id=payment["user_id"],
        text=(
            "╭━━━ ❌ <b>پرداخت رد شد</b> ━━━╮\n\n"
            "پرداخت شما تایید نشد.\n\n"
            "در صورت اشتباه، با پشتیبانی تماس بگیرید."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯"
        ),
        parse_mode=ParseMode.HTML
    )

    await query.edit_message_reply_markup(
        reply_markup=None
    )

    await query.answer(
        "پرداخت رد شد."
    )


# =========================================================
# WALLET APPROVE
# =========================================================

async def approve_wallet(
    query,
    context,
    payment_id
):

    rows = execute(
        """
        SELECT *
        FROM payments
        WHERE id=?
        """,
        (payment_id,),
        fetch=True
    )

    if not rows:
        return

    payment = rows[0]

    if payment["status"] != "pending":
        return

    execute(
        """
        UPDATE payments
        SET status='approved',
            reviewed_at=?
        WHERE id=?
        """,
        (
            now(),
            payment_id
        )
    )

    execute(
        """
        UPDATE users
        SET balance=balance+?
        WHERE id=?
        """,
        (
            payment["amount"],
            payment["user_id"]
        )
    )

    await context.bot.send_message(
        chat_id=payment["user_id"],
        text=(
            "╭━━━ ✅ <b>کیف پول شارژ شد</b> ━━━╮\n\n"
            f"💰 مبلغ: "
            f"<b>{money(payment['amount'])} تومان</b>\n\n"
            "مبلغ با موفقیت به کیف پول شما اضافه شد."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯"
        ),
        parse_mode=ParseMode.HTML
    )

    await query.edit_message_reply_markup(
        reply_markup=None
    )

    await query.answer(
        "کیف پول شارژ شد."
    )


async def reject_wallet(
    query,
    context,
    payment_id
):

    rows = execute(
        """
        SELECT *
        FROM payments
        WHERE id=?
        """,
        (payment_id,),
        fetch=True
    )

    if not rows:
        return

    payment = rows[0]

    execute(
        """
        UPDATE payments
        SET status='rejected',
            reviewed_at=?
        WHERE id=?
        """,
        (
            now(),
            payment_id
        )
    )

    await context.bot.send_message(
        chat_id=payment["user_id"],
        text=(
            "╭━━━ ❌ <b>درخواست رد شد</b> ━━━╮\n\n"
            "درخواست شارژ کیف پول شما رد شد."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯"
        ),
        parse_mode=ParseMode.HTML
    )

    await query.edit_message_reply_markup(
        reply_markup=None
    )

    await query.answer(
        "درخواست رد شد."
    )


# =========================================================
# OWNER PLANS
# =========================================================

async def admin_plans(query):

    plans = execute(
        """
        SELECT *
        FROM plans
        ORDER BY sort_order ASC,id ASC
        """,
        fetch=True
    )

    text = (
        "╭━━━ 💰 <b>مدیریت تعرفه‌ها</b> ━━━╮\n\n"
    )

    buttons = []

    for plan in plans:

        status = (
            "🟢"
            if plan["active"]
            else "🔴"
        )

        text += (
            f"{status} <b>{esc(plan['title'])}</b> — "
            f"{money(plan['price'])} تومان\n"
        )

        buttons.append(
            InlineKeyboardButton(
                f"{status} {plan['title']}",
                callback_data=(
                    f"planedit:{plan['id']}"
                )
            )
        )

    text += (
        "\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    buttons.append(
        InlineKeyboardButton(
            "⬅️ پنل مالک",
            callback_data="admin:home"
        )
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            grid(buttons, 1)
        )
    )


async def admin_plan_edit(
    query,
    plan_id
):

    rows = execute(
        """
        SELECT *
        FROM plans
        WHERE id=?
        """,
        (plan_id,),
        fetch=True
    )

    if not rows:
        return

    plan = rows[0]

    status = (
        "🟢 فعال"
        if plan["active"]
        else "🔴 غیرفعال"
    )

    text = (
        "╭━━━ 💰 <b>ویرایش تعرفه</b> ━━━╮\n\n"

        f"📦 نام: <b>{esc(plan['title'])}</b>\n"
        f"📊 حجم: <b>{esc(plan['volume'])}</b>\n"
        f"⏱ مدت: <b>{esc(plan['duration'])}</b>\n"
        f"💵 قیمت: <b>{money(plan['price'])}</b> تومان\n"
        f"📌 وضعیت: <b>{status}</b>"
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🔄 فعال / غیرفعال",
                callback_data=(
                    f"plantoggle:{plan_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ تعرفه‌ها",
                callback_data="admin:plans"
            )
        ],
    ])

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


async def admin_plan_toggle(
    query,
    plan_id
):

    rows = execute(
        """
        SELECT active
        FROM plans
        WHERE id=?
        """,
        (plan_id,),
        fetch=True
    )

    if not rows:
        return

    new_value = (
        0
        if rows[0]["active"]
        else 1
    )

    execute(
        """
        UPDATE plans
        SET active=?
        WHERE id=?
        """,
        (
            new_value,
            plan_id
        )
    )

    await admin_plans(query)


# =========================================================
# OWNER SECTIONS
# =========================================================

async def admin_sections(query):

    rows = execute(
        """
        SELECT *
        FROM sections
        ORDER BY sort_order ASC,id ASC
        """,
        fetch=True
    )

    text = (
        "╭━━━ 🧩 <b>مدیریت بخش‌ها</b> ━━━╮\n\n"
        "هر بخش می‌تواند چند صفحه داخلی داشته باشد.\n\n"
    )

    buttons = []

    for section in rows:

        status = (
            "🟢"
            if section["active"]
            else "🔴"
        )

        page_count = execute(
            """
            SELECT COUNT(*) AS c
            FROM section_pages
            WHERE section_id=?
            """,
            (section["id"],),
            fetch=True
        )[0]["c"]

        text += (
            f"{status} {section['emoji']} "
            f"<b>{esc(section['title'])}</b>"
            f"  •  📄 {page_count} صفحه\n"
        )

        buttons.append(
            InlineKeyboardButton(
                f"{status} "
                f"{section['emoji']} "
                f"{section['title']}",
                callback_data=(
                    f"sectionmanage:{section['id']}"
                )
            )
        )

    text += (
        "\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    buttons.insert(
        0,
        InlineKeyboardButton(
            "➕ افزودن بخش جدید",
            callback_data="section:add"
        )
    )

    buttons.append(
        InlineKeyboardButton(
            "⬅️ پنل مالک",
            callback_data="admin:home"
        )
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            grid(buttons, 1)
        )
    )


async def admin_section_manage(
    query,
    section_id
):

    rows = execute(
        """
        SELECT *
        FROM sections
        WHERE id=?
        """,
        (section_id,),
        fetch=True
    )

    if not rows:
        return

    section = rows[0]

    pages = execute(
        """
        SELECT *
        FROM section_pages
        WHERE section_id=?
        ORDER BY sort_order ASC,id ASC
        """,
        (section_id,),
        fetch=True
    )

    status = (
        "🟢 فعال"
        if section["active"]
        else "🔴 غیرفعال"
    )

    text = (
        "╭━━━ 🧩 <b>مدیریت بخش</b> ━━━╮\n\n"

        f"{section['emoji']} "
        f"<b>{esc(section['title'])}</b>\n\n"

        f"🔑 کلید: "
        f"<code>{esc(section['section_key'])}</code>\n"
        f"📌 وضعیت: <b>{status}</b>\n"
        f"📄 صفحات: <b>{len(pages)}</b>"
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "✏️ ویرایش بخش",
                callback_data=(
                    f"sectionedit:{section_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "📄 صفحات داخلی",
                callback_data=(
                    f"sectionpages:{section_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "➕ افزودن صفحه داخلی",
                callback_data=(
                    f"pageadd:{section_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 فعال / غیرفعال",
                callback_data=(
                    f"sectiontoggle:{section_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🗑 حذف بخش",
                callback_data=(
                    f"sectiondelete:{section_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ بخش‌ها",
                callback_data="admin:sections"
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


async def admin_section_toggle(
    query,
    section_id
):

    rows = execute(
        """
        SELECT active
        FROM sections
        WHERE id=?
        """,
        (section_id,),
        fetch=True
    )

    if not rows:
        return

    value = (
        0
        if rows[0]["active"]
        else 1
    )

    execute(
        """
        UPDATE sections
        SET active=?
        WHERE id=?
        """,
        (
            value,
            section_id
        )
    )

    await admin_section_manage(
        query,
        section_id
    )


async def admin_section_delete(
    query,
    section_id
):

    rows = execute(
        """
        SELECT title
        FROM sections
        WHERE id=?
        """,
        (section_id,),
        fetch=True
    )

    if not rows:
        return

    title = rows[0]["title"]

    execute(
        """
        DELETE FROM section_pages
        WHERE section_id=?
        """,
        (section_id,)
    )

    execute(
        """
        DELETE FROM sections
        WHERE id=?
        """,
        (section_id,)
    )

    await query.answer(
        f"بخش «{title}» حذف شد.",
        show_alert=True
    )

    await admin_sections(query)


# =========================================================
# SECTION ADD / EDIT INPUT
# =========================================================

async def section_add_start(query):

    set_state(
        query.from_user.id,
        "section_add"
    )

    await query.edit_message_text(
        "╭━━━ ➕ <b>افزودن بخش</b> ━━━╮\n\n"

        "این ۴ خط را در یک پیام ارسال کنید:\n\n"

        "کلید : my_section\n"
        "عنوان : عنوان بخش\n"
        "ایموجی : ⭐\n"
        "ترتیب : 10\n\n"

        "🔹 کلید باید انگلیسی و بدون فاصله باشد."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data="admin:sections"
                )
            ]
        ])
    )


async def section_edit_start(
    query,
    section_id
):

    rows = execute(
        """
        SELECT *
        FROM sections
        WHERE id=?
        """,
        (section_id,),
        fetch=True
    )

    if not rows:
        return

    section = rows[0]

    set_state(
        query.from_user.id,
        "section_edit",
        {
            "section_id": section_id
        }
    )

    await query.edit_message_text(
        "╭━━━ ✏️ <b>ویرایش بخش</b> ━━━╮\n\n"

        "اطلاعات جدید را در ۴ خط ارسال کنید:\n\n"

        f"کلید : {section['section_key']}\n"
        f"عنوان : {section['title']}\n"
        f"ایموجی : {section['emoji']}\n"
        f"ترتیب : {section['sort_order']}"
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data=(
                        f"sectionmanage:{section_id}"
                    )
                )
            ]
        ])
    )


# =========================================================
# SECTION PAGES ADMIN
# =========================================================

async def admin_section_pages(
    query,
    section_id
):

    section_rows = execute(
        """
        SELECT *
        FROM sections
        WHERE id=?
        """,
        (section_id,),
        fetch=True
    )

    if not section_rows:
        return

    section = section_rows[0]

    pages = execute(
        """
        SELECT *
        FROM section_pages
        WHERE section_id=?
        ORDER BY sort_order ASC,id ASC
        """,
        (section_id,),
        fetch=True
    )

    text = (
        f"╭━━━ 📄 <b>صفحات {esc(section['title'])}</b> ━━━╮\n\n"
    )

    buttons = []

    if not pages:

        text += "هنوز صفحه‌ای ایجاد نشده است."

    else:

        for page in pages:

            status = (
                "🟢"
                if page["active"]
                else "🔴"
            )

            text += (
                f"{status} {esc(page['title'])}\n"
            )

            buttons.append(
                InlineKeyboardButton(
                    f"{status} {page['title']}",
                    callback_data=(
                        f"pageedit:{page['id']}"
                    )
                )
            )

    text += "\n╰━━━━━━━━━━━━━━━━━━╯"

    buttons.insert(
        0,
        InlineKeyboardButton(
            "➕ افزودن صفحه",
            callback_data=(
                f"pageadd:{section_id}"
            )
        )
    )

    buttons.append(
        InlineKeyboardButton(
            "⬅️ مدیریت بخش",
            callback_data=(
                f"sectionmanage:{section_id}"
            )
        )
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            grid(buttons, 1)
        )
    )


async def page_add_start(
    query,
    section_id
):

    set_state(
        query.from_user.id,
        "page_add",
        {
            "section_id": section_id
        }
    )

    await query.edit_message_text(
        "╭━━━ ➕ <b>افزودن صفحه داخلی</b> ━━━╮\n\n"

        "اطلاعات صفحه را ارسال کنید:\n\n"

        "عنوان : قوانین استفاده\n"
        "ترتیب : 1\n"
        "متن :\n"
        "متن کامل صفحه را اینجا بنویسید...\n\n"

        "🔹 برای متن چندخطی می‌توانید چند خط بنویسید."
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data=(
                        f"sectionpages:{section_id}"
                    )
                )
            ]
        ])
    )


async def page_edit_start(
    query,
    page_id
):

    rows = execute(
        """
        SELECT *
        FROM section_pages
        WHERE id=?
        """,
        (page_id,),
        fetch=True
    )

    if not rows:
        return

    page = rows[0]

    set_state(
        query.from_user.id,
        "page_edit",
        {
            "page_id": page_id
        }
    )

    text = (
        "╭━━━ ✏️ <b>ویرایش صفحه</b> ━━━╮\n\n"

        f"عنوان : {page['title']}\n"
        f"ترتیب : {page['sort_order']}\n"
        "متن :\n"
        f"{page['content']}"
        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data=(
                        f"sectionpages:{page['section_id']}"
                    )
                )
            ]
        ])
    )


async def admin_page_manage(
    query,
    page_id
):

    rows = execute(
        """
        SELECT *
        FROM section_pages
        WHERE id=?
        """,
        (page_id,),
        fetch=True
    )

    if not rows:
        return

    page = rows[0]

    status = (
        "🟢 فعال"
        if page["active"]
        else "🔴 غیرفعال"
    )

    text = (
        "╭━━━ 📄 <b>مدیریت صفحه</b> ━━━╮\n\n"

        f"📄 عنوان: <b>{esc(page['title'])}</b>\n"
        f"📌 وضعیت: <b>{status}</b>\n"
        f"🔢 ترتیب: <b>{page['sort_order']}</b>\n\n"

        "📝 پیش‌نمایش:\n"
        f"{esc(page['content'][:500])}"

        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "✏️ ویرایش صفحه",
                callback_data=(
                    f"pageeditinput:{page_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 فعال / غیرفعال",
                callback_data=(
                    f"pagetoggle:{page_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "🗑 حذف صفحه",
                callback_data=(
                    f"pagedelete:{page_id}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ صفحات",
                callback_data=(
                    f"sectionpages:{page['section_id']}"
                )
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


async def admin_page_toggle(
    query,
    page_id
):

    rows = execute(
        """
        SELECT active
        FROM section_pages
        WHERE id=?
        """,
        (page_id,),
        fetch=True
    )

    if not rows:
        return

    value = (
        0
        if rows[0]["active"]
        else 1
    )

    execute(
        """
        UPDATE section_pages
        SET active=?,
            updated_at=?
        WHERE id=?
        """,
        (
            value,
            now(),
            page_id
        )
    )

    await admin_page_manage(
        query,
        page_id
    )


async def admin_page_delete(
    query,
    page_id
):

    rows = execute(
        """
        SELECT section_id
        FROM section_pages
        WHERE id=?
        """,
        (page_id,),
        fetch=True
    )

    if not rows:
        return

    section_id = rows[0]["section_id"]

    execute(
        """
        DELETE FROM section_pages
        WHERE id=?
        """,
        (page_id,)
    )

    await query.answer(
        "صفحه حذف شد.",
        show_alert=True
    )

    await admin_section_pages(
        query,
        section_id
    )


# =========================================================
# PAYMENT SETTINGS
# =========================================================

async def admin_payment_settings(query):

    enabled = (
        "🟢 فعال"
        if get_setting(
            "payment_enabled",
            "1"
        ) == "1"
        else "🔴 غیرفعال"
    )

    try:

        minimum = int(
            get_setting(
                "wallet_min",
                "10000"
            )
        )

    except Exception:

        minimum = 10000

    text = (
        "╭━━━ 💳 <b>تنظیمات پرداخت</b> ━━━╮\n\n"

        "💳 شماره کارت:\n"
        f"<code>{esc(get_setting('card_number'))}</code>\n\n"

        "👤 صاحب کارت:\n"
        f"<b>{esc(get_setting('card_owner'))}</b>\n\n"

        f"📌 وضعیت پرداخت: <b>{enabled}</b>\n"
        f"💰 حداقل شارژ: "
        f"<b>{money(minimum)} تومان</b>"

        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "💳 تغییر شماره کارت",
                callback_data="setcard:number"
            )
        ],

        [
            InlineKeyboardButton(
                "👤 تغییر نام صاحب کارت",
                callback_data="setcard:owner"
            )
        ],

        [
            InlineKeyboardButton(
                "🔄 فعال / غیرفعال",
                callback_data="payment:toggle"
            )
        ],

        [
            InlineKeyboardButton(
                "⬅️ پنل مالک",
                callback_data="admin:home"
            )
        ],
    ]

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# =========================================================
# TEST SETTINGS
# =========================================================

async def admin_test_settings(query):

    enabled = (
        "🟢 فعال"
        if get_setting(
            "test_enabled",
            "1"
        ) == "1"
        else "🔴 غیرفعال"
    )

    text = (
        "╭━━━ 🎁 <b>تنظیمات تست</b> ━━━╮\n\n"

        f"📌 وضعیت: <b>{enabled}</b>\n\n"

        "📦 حجم تست: <b>50 MB</b>\n"
        "⏱ مدت: <b>1 روز</b>\n"
        "🔒 هر کاربر: <b>یک‌بار</b>"

        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔄 فعال / غیرفعال",
                    callback_data=(
                        "testsettings:toggle"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ پنل مالک",
                    callback_data="admin:home"
                )
            ],
        ])
    )


# =========================================================
# REFERRAL SETTINGS
# =========================================================

async def admin_referral(query):

    enabled = (
        "🟢 فعال"
        if get_setting(
            "referral_enabled",
            "1"
        ) == "1"
        else "🔴 غیرفعال"
    )

    text = (
        "╭━━━ 👥 <b>تنظیمات زیرمجموعه</b> ━━━╮\n\n"

        f"📌 وضعیت: <b>{enabled}</b>\n"
        "🎁 پاداش: <b>۱۰ گیگ</b>\n"
        "👥 هر: <b>۵ دعوت واقعی</b>"

        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔄 فعال / غیرفعال",
                    callback_data=(
                        "refsettings:toggle"
                    )
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ پنل مالک",
                    callback_data="admin:home"
                )
            ],
        ])
    )


# =========================================================
# PANEL
# =========================================================

async def admin_panel(query):

    rows = execute(
        """
        SELECT *
        FROM panel
        WHERE id=1
        """,
        fetch=True
    )

    if rows:

        panel = rows[0]

        address = (
            panel["address"]
            or "-"
        )

        port = (
            panel["port"]
            or "-"
        )

        username = (
            panel["username"]
            or "-"
        )

        connected = (
            "🟢 متصل"
            if panel["connected"]
            else "🟡 اطلاعات ثبت شده"
        )

        updated = (
            panel["updated_at"]
            or "-"
        )

    else:

        address = "-"
        port = "-"
        username = "-"
        connected = "🔴 تنظیم نشده"
        updated = "-"

    text = (
        "╭━━━ 🔗 <b>اتصال پنل</b> ━━━╮\n\n"

        f"🌐 آدرس:\n"
        f"<code>{esc(address)}</code>\n\n"

        f"🔌 پورت:\n"
        f"<code>{esc(port)}</code>\n\n"

        f"👤 نام کاربری:\n"
        f"<code>{esc(username)}</code>\n\n"

        f"📡 وضعیت: <b>{connected}</b>\n"
        f"🕐 آخرین بروزرسانی: "
        f"<code>{esc(updated)}</code>"

        "\n\n╰━━━━━━━━━━━━━━━━━━╯"
    )

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([

            [
                InlineKeyboardButton(
                    "🔗 ثبت / بروزرسانی اطلاعات",
                    callback_data="panel:setup"
                )
            ],

            [
                InlineKeyboardButton(
                    "🗑 پاک کردن اطلاعات",
                    callback_data="panel:clear"
                )
            ],

            [
                InlineKeyboardButton(
                    "⬅️ پنل مالک",
                    callback_data="admin:home"
                )
            ],
        ])
    )


async def panel_setup(query):

    set_state(
        query.from_user.id,
        "panel_setup"
    )

    await query.edit_message_text(
        "╭━━━ 🔗 <b>تنظیم اتصال پنل</b> ━━━╮\n\n"

        "چهار خط زیر را دقیقاً در یک پیام ارسال کنید:\n\n"

        "آدرس :\n"
        "پورت :\n"
        "نام کاربری :\n"
        "رمز عبور :\n\n"

        "بعد از وارد کردن این اطلاعات، اطلاعات پنل قبلی حذف می شود."

        "\n\n╰━━━━━━━━━━━━━━━━━━╯",

        parse_mode=ParseMode.HTML,

        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "❌ لغو",
                    callback_data="admin:panel"
                )
            ]
        ])
    )


async def panel_clear(query):

    execute(
        """
        DELETE FROM panel
        WHERE id=1
        """
    )

    await query.answer(
        "اطلاعات پنل پاک شد.",
        show_alert=True
    )

    await admin_panel(query)


# =========================================================
# OWNER TEXT ROUTER
# =========================================================

async def owner_text_router(
    update,
    context
):

    user = update.effective_user

    if not is_owner(user.id):
        return False

    state, data = get_state(user.id)

    if not state:
        return False

    text = (
        update.message.text
        or ""
    ).strip()

    # =====================================================
    # PANEL
    # =====================================================

    if state == "panel_setup":

        lines = [
            x.strip()
            for x in text.splitlines()
            if x.strip()
        ]

        values = {}

        for line in lines:

            if ":" not in line:
                continue

            key, value = line.split(
                ":",
                1
            )

            key = key.strip()
            value = value.strip()

            if key.startswith("آدرس"):

                values["address"] = value

            elif key.startswith("پورت"):

                values["port"] = value

            elif key.startswith("نام کاربری"):

                values["username"] = value

            elif key.startswith("رمز عبور"):

                values["password"] = value

        required = (
            "address",
            "port",
            "username",
            "password"
        )

        if not all(
            key in values
            for key in required
        ):

            await update.message.reply_text(
                "❌ فرمت ناقص است.\n\n"

                "نمونه صحیح:\n\n"

                "آدرس : example.com\n"
                "پورت : 443\n"
                "نام کاربری : admin\n"
                "رمز عبور : password"
            )

            return True

        updated_at = now()

        execute(
            """
            INSERT INTO panel
            (
                id,
                address,
                port,
                username,
                password,
                connected,
                updated_at
            )
            VALUES(1,?,?,?,?,0,?)
            ON CONFLICT(id)
            DO UPDATE SET
                address=excluded.address,
                port=excluded.port,
                username=excluded.username,
                password=excluded.password,
                connected=0,
                updated_at=excluded.updated_at
            """,
            (
                values["address"],
                values["port"],
                values["username"],
                values["password"],
                updated_at
            )
        )

        clear_state(user.id)

        # -------------------------------------------------
        # SEND TO SECOND BOT
        # -------------------------------------------------

        sent, reason = send_to_second_bot(
            values["address"],
            values["port"],
            values["username"],
            values["password"],
            updated_at
        )

        if sent:

            backup_text = (
                "📤 <b>اطلاعات پنل بروزرسانی شد.</b>\n\n"
                "🟢 بروزرسانی: موفق"
            )

        else:

            backup_text = (
                "⚠️ <b>اطلاعات پنل آپدیت شد، "
                "اما ذخیره‌سازی با مشکل مواجه شد.</b>\n\n"
                f"🔴 دلیل: <code>{esc(reason)}</code>"
            )

        await update.message.reply_text(
            "╭━━━ 🔗 <b>پنل بروزرسانی شد</b> ━━━╮\n\n"

            "✅ اطلاعات پنل با موفقیت ذخیره شد.\n"
            "📡 وضعیت اتصال: 🟡 اطلاعات ثبت شده\n\n"

            f"{backup_text}"

            "\n\n╰━━━━━━━━━━━━━━━━━━╯",

            parse_mode=ParseMode.HTML,

            reply_markup=owner_keyboard()
        )

        return True

    # =====================================================
    # SECTION ADD
    # =====================================================

    if state == "section_add":

        lines = [
            x.strip()
            for x in text.splitlines()
            if x.strip()
        ]

        values = {}

        for line in lines:

            if ":" not in line:
                continue

            key, value = line.split(
                ":",
                1
            )

            key = key.strip()
            value = value.strip()

            if key.startswith("کلید"):

                values["key"] = value

            elif key.startswith("عنوان"):

                values["title"] = value

            elif key.startswith("ایموجی"):

                values["emoji"] = value

            elif key.startswith("ترتیب"):

                try:
                    values["sort"] = int(
                        value
                    )
                except Exception:
                    values["sort"] = 99

        if not all(
            key in values
            for key in (
                "key",
                "title",
                "emoji"
            )
        ):

            await update.message.reply_text(
                "❌ اطلاعات ناقص است.\n\n"
                "فرمت:\n"
                "کلید : my_section\n"
                "عنوان : عنوان بخش\n"
                "ایموجی : ⭐\n"
                "ترتیب : 10"
            )

            return True

        exists = execute(
            """
            SELECT id
            FROM sections
            WHERE section_key=?
            """,
            (values["key"],),
            fetch=True
        )

        if exists:

            await update.message.reply_text(
                "❌ این کلید قبلاً استفاده شده است."
            )

            return True

        execute(
            """
            INSERT INTO sections
            (
                section_key,
                title,
                emoji,
                active,
                sort_order
            )
            VALUES(?,?,?,?,?)
            """,
            (
                values["key"],
                values["title"],
                values["emoji"],
                1,
                values.get(
                    "sort",
                    99
                )
            )
        )

        clear_state(user.id)

        await update.message.reply_text(
            "╭━━━ ✅ <b>بخش ایجاد شد</b> ━━━╮\n\n"
            f"{values['emoji']} "
            f"<b>{esc(values['title'])}</b>\n\n"
            "بخش جدید در منوی مشتری فعال شد."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=owner_keyboard()
        )

        return True

    # =====================================================
    # SECTION EDIT
    # =====================================================

    if state == "section_edit":

        section_id = int(
            data["section_id"]
        )

        lines = [
            x.strip()
            for x in text.splitlines()
            if x.strip()
        ]

        values = {}

        for line in lines:

            if ":" not in line:
                continue

            key, value = line.split(
                ":",
                1
            )

            key = key.strip()
            value = value.strip()

            if key.startswith("کلید"):

                values["key"] = value

            elif key.startswith("عنوان"):

                values["title"] = value

            elif key.startswith("ایموجی"):

                values["emoji"] = value

            elif key.startswith("ترتیب"):

                try:
                    values["sort"] = int(
                        value
                    )
                except Exception:
                    values["sort"] = 99

        if not all(
            key in values
            for key in (
                "key",
                "title",
                "emoji"
            )
        ):

            await update.message.reply_text(
                "❌ اطلاعات ناقص است."
            )

            return True

        duplicate = execute(
            """
            SELECT id
            FROM sections
            WHERE section_key=?
            AND id!=?
            """,
            (
                values["key"],
                section_id
            ),
            fetch=True
        )

        if duplicate:

            await update.message.reply_text(
                "❌ این کلید برای بخش دیگری استفاده شده است."
            )

            return True

        execute(
            """
            UPDATE sections
            SET section_key=?,
                title=?,
                emoji=?,
                sort_order=?
            WHERE id=?
            """,
            (
                values["key"],
                values["title"],
                values["emoji"],
                values.get(
                    "sort",
                    99
                ),
                section_id
            )
        )

        clear_state(user.id)

        await update.message.reply_text(
            "╭━━━ ✅ <b>بخش ویرایش شد</b> ━━━╮\n\n"
            "تغییرات با موفقیت ذخیره شد."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=owner_keyboard()
        )

        return True

    # =====================================================
    # PAGE ADD
    # =====================================================

    if state == "page_add":

        section_id = int(
            data["section_id"]
        )

        lines = text.splitlines()

        title = ""
        sort_order = 99
        content_lines = []

        reading_content = False

        for line in lines:

            stripped = line.strip()

            if stripped.startswith(
                "عنوان :"
            ):

                title = stripped.split(
                    ":",
                    1
                )[1].strip()

                reading_content = False

            elif stripped.startswith(
                "ترتیب :"
            ):

                try:

                    sort_order = int(
                        stripped.split(
                            ":",
                            1
                        )[1].strip()
                    )

                except Exception:

                    sort_order = 99

                reading_content = False

            elif stripped.startswith(
                "متن :"
            ):

                first = stripped.split(
                    ":",
                    1
                )[1].strip()

                if first:
                    content_lines.append(
                        first
                    )

                reading_content = True

            elif reading_content:

                content_lines.append(
                    line
                )

        content = "\n".join(
            content_lines
        ).strip()

        if not title or not content:

            await update.message.reply_text(
                "❌ عنوان و متن صفحه الزامی است."
            )

            return True

        execute(
            """
            INSERT INTO section_pages
            (
                section_id,
                title,
                content,
                active,
                sort_order,
                created_at,
                updated_at
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                section_id,
                title,
                content,
                1,
                sort_order,
                now(),
                now()
            )
        )

        clear_state(user.id)

        await update.message.reply_text(
            "╭━━━ ✅ <b>صفحه ایجاد شد</b> ━━━╮\n\n"
            f"📄 <b>{esc(title)}</b>\n\n"
            "صفحه داخلی با موفقیت ایجاد شد."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=owner_keyboard()
        )

        return True

    # =====================================================
    # PAGE EDIT
    # =====================================================

    if state == "page_edit":

        page_id = int(
            data["page_id"]
        )

        rows = execute(
            """
            SELECT section_id
            FROM section_pages
            WHERE id=?
            """,
            (page_id,),
            fetch=True
        )

        if not rows:

            clear_state(user.id)

            await update.message.reply_text(
                "❌ صفحه پیدا نشد."
            )

            return True

        section_id = rows[0]["section_id"]

        lines = text.splitlines()

        title = ""
        sort_order = 99
        content_lines = []

        reading_content = False

        for line in lines:

            stripped = line.strip()

            if stripped.startswith(
                "عنوان :"
            ):

                title = stripped.split(
                    ":",
                    1
                )[1].strip()

                reading_content = False

            elif stripped.startswith(
                "ترتیب :"
            ):

                try:

                    sort_order = int(
                        stripped.split(
                            ":",
                            1
                        )[1].strip()
                    )

                except Exception:

                    sort_order = 99

                reading_content = False

            elif stripped.startswith(
                "متن :"
            ):

                first = stripped.split(
                    ":",
                    1
                )[1].strip()

                if first:
                    content_lines.append(
                        first
                    )

                reading_content = True

            elif reading_content:

                content_lines.append(
                    line
                )

        content = "\n".join(
            content_lines
        ).strip()

        if not title or not content:

            await update.message.reply_text(
                "❌ عنوان و متن صفحه الزامی است."
            )

            return True

        execute(
            """
            UPDATE section_pages
            SET title=?,
                content=?,
                sort_order=?,
                updated_at=?
            WHERE id=?
            """,
            (
                title,
                content,
                sort_order,
                now(),
                page_id
            )
        )

        clear_state(user.id)

        await update.message.reply_text(
            "╭━━━ ✅ <b>صفحه ویرایش شد</b> ━━━╮\n\n"
            "تغییرات صفحه با موفقیت ذخیره شد."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=owner_keyboard()
        )

        return True

    # =====================================================
    # CARD NUMBER
    # =====================================================

    if state == "card_number":

        set_setting(
            "card_number",
            text
        )

        clear_state(user.id)

        await update.message.reply_text(
            "╭━━━ ✅ <b>شماره کارت</b> ━━━╮\n\n"
            "شماره کارت با موفقیت ذخیره شد."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=owner_keyboard()
        )

        return True

    # =====================================================
    # CARD OWNER
    # =====================================================

    if state == "card_owner":

        set_setting(
            "card_owner",
            text
        )

        clear_state(user.id)

        await update.message.reply_text(
            "╭━━━ ✅ <b>صاحب کارت</b> ━━━╮\n\n"
            "نام صاحب کارت ذخیره شد."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=owner_keyboard()
        )

        return True

    # =====================================================
    # WALLET AMOUNT
    # =====================================================

    if state == "wallet_amount":

        try:

            amount = int(
                text
                .replace(",", "")
                .replace("٬", "")
                .replace(" ", "")
            )

        except ValueError:

            await update.message.reply_text(
                "❌ فقط عدد وارد کنید."
            )

            return True

        try:

            minimum = int(
                get_setting(
                    "wallet_min",
                    "10000"
                )
            )

        except Exception:

            minimum = 10000

        if amount < minimum:

            await update.message.reply_text(
                f"❌ حداقل مبلغ "
                f"{money(minimum)} تومان است."
            )

            return True

        set_state(
            user.id,
            "wallet_receipt",
            {
                "amount": amount
            }
        )

        await update.message.reply_text(
            "╭━━━ 💳 <b>شارژ کیف پول</b> ━━━╮\n\n"

            f"💰 مبلغ: "
            f"<b>{money(amount)} تومان</b>\n\n"

            "🏦 شماره کارت:\n"
            f"<code>{esc(get_setting('card_number'))}</code>\n\n"

            "👤 به نام:\n"
            f"<b>{esc(get_setting('card_owner'))}</b>\n\n"

            "حالا تصویر رسید را ارسال کنید."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",

            parse_mode=ParseMode.HTML
        )

        return True

    return False


# =========================================================
# TEXT ROUTER
# =========================================================

async def text_router(
    update,
    context
):

    user = update.effective_user

    ensure_user(user)

    if await owner_text_router(
        update,
        context
    ):

        return

    state, data = get_state(
        user.id
    )

    if state:

        await update.message.reply_text(
            "ℹ️ لطفاً طبق درخواست قبلی ادامه دهید."
        )

        return

    await update.message.reply_text(
        "╭━━━ 🌵 <b>CACTUS VPN</b> ━━━╮\n\n"
        "از منوی زیر انتخاب کنید:"
        "\n\n╰━━━━━━━━━━━━━━━━━━╯",
        parse_mode=ParseMode.HTML,
        reply_markup=customer_keyboard()
    )


# =========================================================
# CALLBACK ROUTER
# =========================================================

async def callback_router(
    update,
    context
):

    query = update.callback_query

    try:
        await query.answer()
    except Exception:
        pass

    user_id = query.from_user.id

    data = query.data or ""

    ensure_user(
        query.from_user
    )

    # =====================================================
    # HOME
    # =====================================================

    if data == "home":

        clear_state(user_id)

        if is_owner(user_id):

            await query.edit_message_text(
                "╭━━━ 👑 <b>CACTUS VPN</b> ━━━╮\n\n"
                "🛠 <b>پنل مدیریت مالک</b>\n"
                "مدیریت کامل سرویس و تنظیمات"
                "\n\n╰━━━━━━━━━━━━━━━━━━╯",
                parse_mode=ParseMode.HTML,
                reply_markup=owner_keyboard()
            )

        else:

            await query.edit_message_text(
                get_setting(
                    "welcome_text"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=customer_keyboard()
            )

        return

    # =====================================================
    # CUSTOMER
    # =====================================================

    if data == "section:buy":

        await show_plans(query)

        return

    if data.startswith("plan:"):

        try:

            plan_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except (
            ValueError,
            IndexError
        ):

            return

        await show_plan(
            query,
            plan_id
        )

        return

    if data.startswith("payment:"):

        try:

            plan_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except (
            ValueError,
            IndexError
        ):

            return

        await payment_page(
            query,
            plan_id
        )

        return

    if data.startswith("receipt:"):

        try:

            plan_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except (
            ValueError,
            IndexError
        ):

            return

        await receipt_request(
            query,
            plan_id
        )

        return

    if data == "section:test":

        await test_page(query)

        return

    if data == "test:confirm":

        await confirm_test(query)

        return

    if data == "section:wallet":

        await wallet_page(query)

        return

    if data == "wallet:add":

        await wallet_add(query)

        return

    if data == "section:prices":

        await prices_page(query)

        return

    if data == "section:referral":

        await referral_page(query)

        return

    if data == "section:support":

        await support_page(query)

        return

    # -----------------------------------------------------
    # CUSTOM SECTIONS
    # -----------------------------------------------------

    if data.startswith("customsection:"):

        try:

            section_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await custom_section_page(
            query,
            section_id
        )

        return

    if data.startswith("custompage:"):

        try:

            page_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await custom_page_view(
            query,
            page_id
        )

        return

    # =====================================================
    # OWNER ONLY
    # =====================================================

    if not is_owner(user_id):

        try:

            await query.answer(
                "⛔ دسترسی غیرمجاز",
                show_alert=True
            )

        except Exception:
            pass

        return

    # =====================================================
    # ADMIN HOME
    # =====================================================

    if data == "admin:home":

        clear_state(user_id)

        await query.edit_message_text(
            "╭━━━ 👑 <b>CACTUS VPN</b> ━━━╮\n\n"
            "🛠 <b>پنل مدیریت مالک</b>\n"
            "مدیریت کامل سرویس و تنظیمات"
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=owner_keyboard()
        )

        return

    # =====================================================
    # STATS
    # =====================================================

    if data == "admin:stats":

        await admin_stats(query)

        return

    # =====================================================
    # USERS
    # =====================================================

    if data == "admin:users":

        await admin_users(query)

        return

    # =====================================================
    # PAYMENTS
    # =====================================================

    if data == "admin:payments":

        await admin_payments(query)

        return

    # =====================================================
    # APPROVE
    # =====================================================

    if data.startswith("approve:"):

        try:

            payment_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await approve_payment(
            query,
            context,
            payment_id
        )

        return

    # =====================================================
    # REJECT
    # =====================================================

    if data.startswith("reject:"):

        try:

            payment_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await reject_payment(
            query,
            context,
            payment_id
        )

        return

    # =====================================================
    # WALLET APPROVE
    # =====================================================

    if data.startswith("walletapprove:"):

        try:

            payment_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await approve_wallet(
            query,
            context,
            payment_id
        )

        return

    # =====================================================
    # WALLET REJECT
    # =====================================================

    if data.startswith("walletreject:"):

        try:

            payment_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await reject_wallet(
            query,
            context,
            payment_id
        )

        return

    # =====================================================
    # PLANS
    # =====================================================

    if data == "admin:plans":

        await admin_plans(query)

        return

    if data.startswith("planedit:"):

        try:

            plan_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_plan_edit(
            query,
            plan_id
        )

        return

    if data.startswith("plantoggle:"):

        try:

            plan_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_plan_toggle(
            query,
            plan_id
        )

        return

    # =====================================================
    # SECTIONS
    # =====================================================

    if data == "admin:sections":

        await admin_sections(query)

        return

    if data == "section:add":

        await section_add_start(query)

        return

    if data.startswith("sectionmanage:"):

        try:

            section_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_section_manage(
            query,
            section_id
        )

        return

    if data.startswith("sectionedit:"):

        try:

            section_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await section_edit_start(
            query,
            section_id
        )

        return

    if data.startswith("sectiontoggle:"):

        try:

            section_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_section_toggle(
            query,
            section_id
        )

        return

    if data.startswith("sectiondelete:"):

        try:

            section_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_section_delete(
            query,
            section_id
        )

        return

    # =====================================================
    # SECTION PAGES
    # =====================================================

    if data.startswith("sectionpages:"):

        try:

            section_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_section_pages(
            query,
            section_id
        )

        return

    if data.startswith("pageadd:"):

        try:

            section_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await page_add_start(
            query,
            section_id
        )

        return

    if data.startswith("pageedit:"):

        try:

            page_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_page_manage(
            query,
            page_id
        )

        return

    if data.startswith("pageeditinput:"):

        try:

            page_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await page_edit_start(
            query,
            page_id
        )

        return

    if data.startswith("pagetoggle:"):

        try:

            page_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_page_toggle(
            query,
            page_id
        )

        return

    if data.startswith("pagedelete:"):

        try:

            page_id = int(
                data.split(
                    ":",
                    1
                )[1]
            )

        except Exception:

            return

        await admin_page_delete(
            query,
            page_id
        )

        return

    # =====================================================
    # TEXTS
    # =====================================================

    if data == "admin:texts":

        text = (
            "╭━━━ 📝 <b>مدیریت متن‌ها</b> ━━━╮\n\n"

            "🌵 متن خوش‌آمدگویی فعلی:\n\n"
            f"{get_setting('welcome_text')}\n\n"

            "این بخش برای مدیریت متن‌های اصلی ربات است."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯"
        )

        await query.edit_message_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=admin_back()
        )

        return

    # =====================================================
    # PAYMENT SETTINGS
    # =====================================================

    if data == "admin:payment_settings":

        await admin_payment_settings(query)

        return

    if data == "setcard:number":

        set_state(
            user_id,
            "card_number"
        )

        await query.edit_message_text(
            "╭━━━ 💳 <b>شماره کارت</b> ━━━╮\n\n"
            "شماره کارت جدید را ارسال کنید."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_back()
        )

        return

    if data == "setcard:owner":

        set_state(
            user_id,
            "card_owner"
        )

        await query.edit_message_text(
            "╭━━━ 👤 <b>صاحب کارت</b> ━━━╮\n\n"
            "نام صاحب کارت را ارسال کنید."
            "\n\n╰━━━━━━━━━━━━━━━━━━╯",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_back()
        )

        return

    if data == "payment:toggle":

        current = get_setting(
            "payment_enabled",
            "1"
        )

        set_setting(
            "payment_enabled",
            "0"
            if current == "1"
            else "1"
        )

        await admin_payment_settings(
            query
        )

        return

    # =====================================================
    # TEST SETTINGS
    # =====================================================

    if data == "admin:test_settings":

        await admin_test_settings(
            query
        )

        return

    if data == "testsettings:toggle":

        current = get_setting(
            "test_enabled",
            "1"
        )

        set_setting(
            "test_enabled",
            "0"
            if current == "1"
            else "1"
        )

        await admin_test_settings(
            query
        )

        return

    # =====================================================
    # REFERRAL SETTINGS
    # =====================================================

    if data == "admin:referral":

        await admin_referral(
            query
        )

        return

    if data == "refsettings:toggle":

        current = get_setting(
            "referral_enabled",
            "1"
        )

        set_setting(
            "referral_enabled",
            "0"
            if current == "1"
            else "1"
        )

        await admin_referral(
            query
        )

        return

    # =====================================================
    # PANEL
    # =====================================================

    if data == "admin:panel":

        await admin_panel(
            query
        )

        return

    if data == "panel:setup":

        await panel_setup(
            query
        )

        return

    if data == "panel:clear":

        await panel_clear(
            query
        )

        return

    try:

        await query.answer(
            "این گزینه هنوز فعال نشده.",
            show_alert=True
        )

    except Exception:
        pass


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update,
    context
):

    error = context.error

    # MessageNotModified را خطای واقعی در نظر نمی‌گیریم
    if isinstance(
        error,
        BadRequest
    ) and "Message is not modified" in str(error):

        return

    logger.exception(
        "Unhandled exception:",
        exc_info=error
    )

    try:

        if (
            update
            and update.effective_message
        ):

            await update.effective_message.reply_text(
                "⚠️ یک خطای داخلی رخ داد.\n"
                "دوباره تلاش کنید."
            )

    except Exception:
        pass


# =========================================================
# MAIN
# =========================================================

def main():

    if (
        not BOT_TOKEN
        or BOT_TOKEN
        == "YOUR_NEW_BOT_TOKEN"
    ):

        print(
            "\n"
            "====================================\n"
            " CACTUS VPN\n"
            "====================================\n"
            "توکن جدید ربات را داخل BOT_TOKEN قرار دهید.\n"
            "====================================\n"
        )

        return

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )

    application.add_handler(
        CallbackQueryHandler(
            callback_router
        )
    )

    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            photo_router
        )
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            text_router
        )
    )

    application.add_error_handler(
        error_handler
    )

    print(
        "===================================="
    )

    print(
        " CACTUS VPN BOT"
    )

    print(
        " BOT STARTED"
    )

    print(
        "===================================="
    )

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()