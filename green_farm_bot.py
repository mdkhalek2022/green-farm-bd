import os
import sqlite3
import time
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

DB_PATH = os.getenv("DB_PATH", "green_farm.db")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# বাংলা গেমের ফসল: বীজের দাম, বেড়ে উঠতে সময় (সেকেন্ড), বিক্রির দাম
CROPS = {
    "rice": {"name": "ধান", "seed_price": 12, "grow": 300, "sell": 35, "emoji": "🌾"},
    "wheat": {"name": "গম", "seed_price": 10, "grow": 180, "sell": 28, "emoji": "🌿"},
    "corn": {"name": "ভুট্টা", "seed_price": 15, "grow": 240, "sell": 42, "emoji": "🌽"},
    "potato": {"name": "আলু", "seed_price": 14, "grow": 210, "sell": 38, "emoji": "🥔"},
}
FIELD_COUNT = 5
STARTING_COINS = 1000


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                coins INTEGER NOT NULL DEFAULT 1000,
                rice_seed INTEGER NOT NULL DEFAULT 3,
                wheat_seed INTEGER NOT NULL DEFAULT 3,
                corn_seed INTEGER NOT NULL DEFAULT 0,
                potato_seed INTEGER NOT NULL DEFAULT 0,
                joined_at INTEGER NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS fields (
                user_id INTEGER NOT NULL,
                field_no INTEGER NOT NULL,
                crop TEXT,
                planted_at INTEGER,
                PRIMARY KEY (user_id, field_no)
            )
        """)


def ensure_player(user):
    name = user.first_name or user.username or "কৃষক"
    with db() as con:
        con.execute(
            "INSERT OR IGNORE INTO players(user_id, username, coins, joined_at) VALUES(?,?,?,?)",
            (user.id, name, STARTING_COINS, int(time.time())),
        )
        con.execute("UPDATE players SET username=? WHERE user_id=?", (name, user.id))
        for n in range(1, FIELD_COUNT + 1):
            con.execute(
                "INSERT OR IGNORE INTO fields(user_id, field_no) VALUES(?,?)",
                (user.id, n),
            )


def get_player(user_id):
    with db() as con:
        return con.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()


def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌱 আমার জমি", callback_data="fields"),
         InlineKeyboardButton("🛒 বীজের দোকান", callback_data="shop")],
        [InlineKeyboardButton("👨‍🌾 আমার প্রোফাইল", callback_data="profile"),
         InlineKeyboardButton("🏆 সেরা কৃষক", callback_data="top")],
        [InlineKeyboardButton("ℹ️ খেলার নিয়ম", callback_data="help")],
    ])


def back_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏡 মূল মেনু", callback_data="home")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_player(update.effective_user)
    await update.message.reply_text(
        "🌾 স্বাগতম *গ্রিন ফার্মে!*\n\n"
        "এখানে তুমি নিজের খামার তৈরি করবে, বীজ কিনবে, ফসল ফলাবে এবং বিক্রি করে কয়েন জমাবে।\n\n"
        "🎁 নতুন কৃষক হিসেবে পেয়েছো ১,০০০ কয়েন, ৫টি জমি এবং ৩টি ধান ও ৩টি গমের বীজ।",
        reply_markup=main_menu(),
        parse_mode="Markdown",
    )


async def show_fields(query, user_id):
    with db() as con:
        rows = con.execute(
            "SELECT * FROM fields WHERE user_id=? ORDER BY field_no", (user_id,)
        ).fetchall()
    lines = ["🌱 *তোমার খামার — ৫টি জমি*", ""]
    buttons = []
    now = int(time.time())
    for row in rows:
        n = row["field_no"]
        crop = row["crop"]
        if not crop:
            lines.append(f"জমি {n}: 🟫 খালি")
            buttons.append([InlineKeyboardButton(f"🌱 জমি {n}-এ বীজ বপন", callback_data=f"plantmenu:{n}")])
        else:
            data = CROPS[crop]
            ready_at = row["planted_at"] + data["grow"]
            if now >= ready_at:
                lines.append(f"জমি {n}: {data['emoji']} {data['name']} — ✅ কাটার সময় হয়েছে!")
                buttons.append([InlineKeyboardButton(f"🌾 জমি {n} থেকে ফসল কাটো", callback_data=f"harvest:{n}")])
            else:
                left = ready_at - now
                mins, secs = divmod(left, 60)
                lines.append(f"জমি {n}: {data['emoji']} {data['name']} — ⏳ {mins} মিনিট {secs} সেকেন্ড বাকি")
    buttons.append([InlineKeyboardButton("🏡 মূল মেনু", callback_data="home")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def show_shop(query, user_id):
    player = get_player(user_id)
    lines = [f"🛒 *বীজের দোকান*\n\nতোমার কয়েন: 🪙 {player['coins']}\n"]
    buttons = []
    for key, crop in CROPS.items():
        stock = player[f"{key}_seed"]
        lines.append(f"{crop['emoji']} {crop['name']}: {crop['seed_price']} কয়েন/বীজ | তোমার আছে {stock}টি")
        buttons.append([InlineKeyboardButton(
            f"{crop['emoji']} {crop['name']} — {crop['seed_price']} কয়েন",
            callback_data=f"buy:{key}",
        )])
    buttons.append([InlineKeyboardButton("🏡 মূল মেনু", callback_data="home")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown")


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_player(query.from_user)
    data = query.data

    if data == "home":
        await query.edit_message_text("🌾 *গ্রিন ফার্ম — প্রধান মেনু*\n\nতোমার খামার পরিচালনা শুরু করো!", reply_markup=main_menu(), parse_mode="Markdown")
    elif data == "fields":
        await show_fields(query, user_id)
    elif data == "shop":
        await show_shop(query, user_id)
    elif data == "profile":
        p = get_player(user_id)
        await query.edit_message_text(
            f"👨‍🌾 *কৃষক প্রোফাইল*\n\nনাম: {p['username']}\n🪙 কয়েন: {p['coins']}\n"
            f"🌾 ধানের বীজ: {p['rice_seed']}\n🌿 গমের বীজ: {p['wheat_seed']}\n"
            f"🌽 ভুট্টার বীজ: {p['corn_seed']}\n🥔 আলুর বীজ: {p['potato_seed']}",
            reply_markup=back_menu(), parse_mode="Markdown"
        )
    elif data == "help":
        await query.edit_message_text(
            "ℹ️ *খেলার নিয়ম*\n\n১. বীজের দোকান থেকে বীজ কিনো।\n"
            "২. আমার জমি থেকে খালি জমি বেছে বীজ বপন করো।\n"
            "৩. ফসল বড় হওয়া পর্যন্ত অপেক্ষা করো।\n"
            "৪. ফসল পেকে গেলে কেটে কয়েন নাও।\n"
            "৫. কয়েন দিয়ে আরও বীজ কিনে খামার বড় করো।\n\n"
            "⏱️ বপনের পর বট বন্ধ থাকলেও ফসলের সময় গণনা চলবে।",
            reply_markup=back_menu(), parse_mode="Markdown"
        )
    elif data == "top":
        with db() as con:
            rows = con.execute("SELECT username, coins FROM players ORDER BY coins DESC LIMIT 10").fetchall()
        text = "🏆 *সেরা ১০ কৃষক*\n\n"
        if not rows:
            text += "এখনো কোনো কৃষক নেই।"
        else:
            text += "\n".join(f"{i}. {r['username']} — 🪙 {r['coins']}" for i, r in enumerate(rows, 1))
        await query.edit_message_text(text, reply_markup=back_menu(), parse_mode="Markdown")
    elif data.startswith("plantmenu:"):
        field_no = int(data.split(":")[1])
        p = get_player(user_id)
        buttons = []
        for key, crop in CROPS.items():
            if p[f"{key}_seed"] > 0:
                buttons.append([InlineKeyboardButton(
                    f"{crop['emoji']} {crop['name']} বপন ({p[f'{key}_seed']}টি বীজ আছে)",
                    callback_data=f"plant:{field_no}:{key}",
                )])
        buttons.append([InlineKeyboardButton("⬅️ জমিতে ফিরে যাও", callback_data="fields")])
        await query.edit_message_text(f"জমি {field_no}-এ কোন বীজ বপন করবে?", reply_markup=InlineKeyboardMarkup(buttons))
    elif data.startswith("buy:"):
        key = data.split(":")[1]
        crop = CROPS[key]
        with db() as con:
            p = con.execute("SELECT coins FROM players WHERE user_id=?", (user_id,)).fetchone()
            if p["coins"] < crop["seed_price"]:
                await query.answer("❌ পর্যাপ্ত কয়েন নেই!", show_alert=True)
                return
            con.execute(
                f"UPDATE players SET coins=coins-?, {key}_seed={key}_seed+1 WHERE user_id=?",
                (crop["seed_price"], user_id),
            )
        await query.answer(f"✅ ১টি {crop['name']} বীজ কিনেছো!")
        await show_shop(query, user_id)
    elif data.startswith("plant:"):
        _, field_text, key = data.split(":")
        field_no = int(field_text)
        crop = CROPS[key]
        with db() as con:
            field = con.execute(
                "SELECT crop FROM fields WHERE user_id=? AND field_no=?", (user_id, field_no)
            ).fetchone()
            p = con.execute(f"SELECT {key}_seed FROM players WHERE user_id=?", (user_id,)).fetchone()
            if field["crop"] is not None or p[f"{key}_seed"] < 1:
                await query.answer("এই জমি খালি নেই অথবা বীজ নেই।", show_alert=True)
                return
            con.execute(f"UPDATE players SET {key}_seed={key}_seed-1 WHERE user_id=?", (user_id,))
            con.execute(
                "UPDATE fields SET crop=?, planted_at=? WHERE user_id=? AND field_no=?",
                (key, int(time.time()), user_id, field_no),
            )
        await query.answer(f"🌱 {crop['name']} বপন সম্পন্ন!")
        await show_fields(query, user_id)
    elif data.startswith("harvest:"):
        field_no = int(data.split(":")[1])
        with db() as con:
            row = con.execute(
                "SELECT crop, planted_at FROM fields WHERE user_id=? AND field_no=?",
                (user_id, field_no),
            ).fetchone()
            if not row or not row["crop"]:
                await query.answer("এই জমিতে কোনো ফসল নেই।", show_alert=True)
                return
            crop = CROPS[row["crop"]]
            if int(time.time()) < row["planted_at"] + crop["grow"]:
                await query.answer("ফসল এখনো পাকেনি।", show_alert=True)
                return
            reward = crop["sell"]
            con.execute("UPDATE players SET coins=coins+? WHERE user_id=?", (reward, user_id))
            con.execute(
                "UPDATE fields SET crop=NULL, planted_at=NULL WHERE user_id=? AND field_no=?",
                (user_id, field_no),
            )
        await query.answer(f"🎉 {crop['name']} বিক্রি করে {reward} কয়েন পেয়েছো!")
        await show_fields(query, user_id)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN পরিবেশ ভেরিয়েবলে সেট করো। কোডে টোকেন লিখবে না।")
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_button))
    print("Green Farm Bot চালু হয়েছে...")
    app.run_polling()


if __name__ == "__main__":
    main()
