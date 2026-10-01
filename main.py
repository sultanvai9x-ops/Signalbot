import asyncio
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import httpx
from telegram import Update, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

# ================= Configuration =================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8848552433:AAH-BqtoSxtS94oPm5qwexltTjDaJaPnwFM")
CHANNEL_IDS = ['-1002125064310']
API_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_1M/GetHistoryIssuePage.json"
API_TIMEOUT = 10
TIMEZONE = ZoneInfo('Asia/Dhaka')
DATA_FILE = "bot_data.json"

LOSS_STREAK_MESSAGE = "💥 <b>সবাই অবশ্যই ৭ স্টেপ ফান্ড মেনটেন করবেন!</b> 🚨"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation States
CHOOSING_STICKER = 1
WAITING_FOR_TIME_1, WAITING_FOR_TIME_2, WAITING_FOR_TIME_3 = 2, 3, 4
WAITING_FOR_TIME_4, WAITING_FOR_TIME_5, WAITING_FOR_TIME_6 = 5, 6, 7

WAITING_TRADING_VIDEO = 10
WAITING_ACCOUNT_VIDEO = 11
WAITING_FORWARD_MSG = 12
WAITING_VOICE_MSG = 13

STICKER_STATES = {
    '🏆 উইন স্টিকার': 'win',
    '💔 লস স্টিকার': 'loss',
    '🚀 সিগন্যাল শুরু স্টিকার': 'start',
    '🏁 সিগন্যাল শেষ স্টিকার': 'end'
}

class BotState:
    def __init__(self):
        self.is_running = False
        self.win_count = 0
        self.last_period = ""
        self.last_prediction = ""
        self.current_trade_amount = 50
        
        self.win_sticker_id = None
        self.loss_sticker_id = None
        self.start_sticker_id = None
        self.end_sticker_id = None
        
        self.forward_msg_id = None
        self.forward_chat_id = None
        self.voice_msg_id = None
        self.voice_chat_id = None
        
        self.trading_video_msg_id = None
        self.trading_video_chat_id = None
        self.account_video_msg_id = None
        self.account_video_chat_id = None
        
        self.consecutive_losses = 0
        self.waiting_for_result = False
        self.cooldown_end_time = 0
        self.current_strategy_index = 0
        
        self.scheduled_times = {
            1: {"time_str": None, "next_dt_iso": None, "alert_sent_10": False, "alert_sent_5": False},
            2: {"time_str": None, "next_dt_iso": None, "alert_sent_10": False, "alert_sent_5": False},
            3: {"time_str": None, "next_dt_iso": None, "alert_sent_10": False, "alert_sent_5": False},
            4: {"time_str": None, "next_dt_iso": None, "alert_sent_10": False, "alert_sent_5": False},
            5: {"time_str": None, "next_dt_iso": None, "alert_sent_10": False, "alert_sent_5": False},
            6: {"time_str": None, "next_dt_iso": None, "alert_sent_10": False, "alert_sent_5": False}
        }
        self.load_data()

    def save_data(self):
        data = {
            "win_sticker_id": self.win_sticker_id,
            "loss_sticker_id": self.loss_sticker_id,
            "start_sticker_id": self.start_sticker_id,
            "end_sticker_id": self.end_sticker_id,
            "forward_msg_id": self.forward_msg_id,
            "forward_chat_id": self.forward_chat_id,
            "voice_msg_id": self.voice_msg_id,
            "voice_chat_id": self.voice_chat_id,
            "trading_video_msg_id": self.trading_video_msg_id,
            "trading_video_chat_id": self.trading_video_chat_id,
            "account_video_msg_id": self.account_video_msg_id,
            "account_video_chat_id": self.account_video_chat_id,
            "scheduled_times": self.scheduled_times
        }
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"ডাটা সেভ করতে সমস্যা: {e}")

    def load_data(self):
        if not os.path.exists(DATA_FILE):
            return
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.win_sticker_id = data.get("win_sticker_id")
                self.loss_sticker_id = data.get("loss_sticker_id")
                self.start_sticker_id = data.get("start_sticker_id")
                self.end_sticker_id = data.get("end_sticker_id")
                self.forward_msg_id = data.get("forward_msg_id")
                self.forward_chat_id = data.get("forward_chat_id")
                self.voice_msg_id = data.get("voice_msg_id")
                self.voice_chat_id = data.get("voice_chat_id")
                self.trading_video_msg_id = data.get("trading_video_msg_id")
                self.trading_video_chat_id = data.get("trading_video_chat_id")
                self.account_video_msg_id = data.get("account_video_msg_id")
                self.account_video_chat_id = data.get("account_video_chat_id")
                
                saved_times = data.get("scheduled_times", {})
                for k, v in saved_times.items():
                    self.scheduled_times[int(k)] = v
        except Exception as e:
            logger.error(f"ডাটা লোড করতে সমস্যা: {e}")

bot_state = BotState()

# AI Prediction Logic
def predict_ai_sure_shot(history_list: list, strategy_mode: int):
    if not history_list or len(history_list) < 5:
        return "BIG"

    numbers = []
    results = []
    for item in history_list[:15]:
        num = int(item.get('number', 0))
        numbers.append(num)
        results.append("BIG" if num >= 5 else "SMALL")

    last_res = results[0]

    if strategy_mode % 4 == 0:
        if len(results) >= 2 and results[0] == results[1]:
            return "SMALL" if last_res == "BIG" else "BIG"
        return "BIG" if last_res == "SMALL" else "SMALL"

    elif strategy_mode % 4 == 1:
        recent_numbers = numbers[:4]
        avg_val = sum(recent_numbers) / len(recent_numbers)
        return "SMALL" if avg_val >= 5.0 else "BIG"

    elif strategy_mode % 4 == 2:
        if len(results) >= 3 and results[0] != results[1] and results[1] != results[2]:
            return "SMALL" if last_res == "BIG" else "BIG"
        return "SMALL" if last_res == "BIG" else "BIG"

    elif strategy_mode % 4 == 3:
        recent_10 = results[:10]
        return "SMALL" if recent_10.count("BIG") >= 6 else "BIG"

    return "BIG" if last_res == "SMALL" else "SMALL"

# ================= Advanced Time Parsing System =================
def parse_bengali_time(time_str: str):
    try:
        raw_input = time_str
        bangla_nums = {'০':'0', '১':'1', '২':'2', '৩':'3', '৪':'4', '৫':'5', '৬':'6', '৭':'7', '৮':'8', '৯':'9'}
        for b, e in bangla_nums.items():
            time_str = time_str.replace(b, e)
            
        time_str_clean = time_str.lower().strip()
        match = re.search(r'(\d{1,2})(?::(\d{2}))?', time_str_clean)
        if not match:
            return None, None
            
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        
        if any(keyword in time_str_clean for keyword in ['বিকেল', 'বিকাল', 'সন্ধ্যা', 'রাত', 'pm']) and hour < 12:
            hour += 12
        elif any(keyword in time_str_clean for keyword in ['সকাল', 'ভোর', 'am']) and hour == 12:
            hour = 0

        now = datetime.now(TIMEZONE)
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if target_time <= now:
            target_time += timedelta(days=1)
            
        return target_time, raw_input
    except Exception as e:
        logger.error(f"টাইম পার্সিং ত্রুটি: {e}")
        return None, None

def get_bangla_period_name(dt: datetime) -> str:
    hour = dt.hour
    if 5 <= hour < 12:
        return "সকালের সিগন্যাল"
    elif 12 <= hour < 15:
        return "দুপুরের সিগন্যাল"
    elif 15 <= hour < 18:
        return "বিকালের সিগন্যাল"
    elif 18 <= hour < 20:
        return "সংধ্যার সিগন্যাল"
    else:
        return "রাতের সিগন্যাল"

def format_bangla_time_digits(dt: datetime) -> str:
    time_str = dt.strftime("%I:%M")
    bangla_nums = {'0':'০', '1':'১', '2':'২', '3':'৩', '4':'৪', '5':'৫', '6':'৬', '7':'৭', '8':'৮', '9':'৯'}
    for e, b in bangla_nums.items():
        time_str = time_str.replace(e, b)
    return time_str

def get_next_scheduled_info() -> str:
    now = datetime.now(TIMEZONE)
    upcoming_times = []
    
    for timer_id, timer_data in bot_state.scheduled_times.items():
        iso_str = timer_data.get("next_dt_iso")
        if iso_str:
            dt = datetime.fromisoformat(iso_str)
            if dt > now:
                upcoming_times.append(dt)
            
    if upcoming_times:
        next_dt = min(upcoming_times)
        period_name = get_bangla_period_name(next_dt)
        time_digits = format_bangla_time_digits(next_dt)
        return f"{period_name} ({time_digits} টা)"
    return None

def create_prediction_message(period: str, prediction: str, amount: int) -> str:
    result_emoji = "🟢" if prediction == "BIG" else "🔴"
    return (
        "🔥 <b>VIP VIP VIP SIGNAL</b> 🔥\n"
        "⚡ <i>১ মিনিটের ট্রেড করুন</i> ⚡\n\n"
        f"➡️ <b>পিরিয়ড:</b> <code>{period}</code>\n"
        f"{result_emoji} <b>প্রেডিকশন:</b> <b>{prediction}</b>\n"
        f"💰 <b>ইনভেস্টমেন্ট:</b> ৳{amount}\n\n"
        "⚠️ <b>অবশ্যই ৭ স্টেপ ফান্ড মেনটেন করে ট্রেড করবেন!</b> 🚀"
    )

def create_10min_alert_message() -> str:
    return (
        "💎 <b>গুরুত্বপূর্ণ নোটিশ & সতর্কতা</b> 💎\n\n"
        "📌 <i>আপনার একাউন্টে ব্যালেন্স রাখুন <b>৬৫০০৳</b> এবং আমাদের দেখানো অনুযায়ী সিগন্যাল ফলো করুন, তাহলে কখনো লস হবে না।</i>\n\n"
        "🎯 <b>সিগন্যালে যত টাকা অ্যামাউন্টের ট্রেড নিতে বলা হবে, ঠিক তত টাকা অ্যামাউন্টের ট্রেডই নিবেন।</b> 🚀"
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    kb = [
        ['🟢 ম্যানুয়াল সিগন্যাল শুরু', '🔴 সিগন্যাল অফ'],
        ['⏰ টাইমার ১', '⏰ টাইমার ২', '⏰ টাইমার ৩'],
        ['⏰ টাইমার ৪', '⏰ টাইমার ৫', '⏰ টাইমার ৬'],
        ['🏆 উইন স্টিকার', '💔 লস স্টিকার'],
        ['🚀 সিগন্যাল শুরু স্টিকার', '🏁 সিগন্যাল শেষ স্টিকার'],
        ['📩 ফরওয়ার্ড মেসেজ সেট', '🎙️ ভয়েস ফরওয়ার্ড'],
        ['🎬 কালার ট্রেডিং ভিডিও', '📝 একাউন্ট ক্রিয়েট ভিডিও']
    ]
    
    status_msg = "🤖 <b>বট কন্ট্রোল প্যানেল</b>\n\n"
    status_msg += "📌 <b>বর্তমান শেডিউল করা টাইমারসমূহ:</b>\n"
    for i in range(1, 7):
        t_data = bot_state.scheduled_times[i]
        iso_str = t_data.get("next_dt_iso")
        if iso_str:
            dt = datetime.fromisoformat(iso_str)
            period = get_bangla_period_name(dt)
            digits = format_bangla_time_digits(dt)
            status_msg += f"• টাইমার {i}: {period} ({digits} টা)\n"
        else:
            status_msg += f"• টাইমার {i}: সেট করা নেই\n"

    status_msg += "\n💡 <i>টাইমার সেট করতে নিচের টাইমার বাটনে চাপুন।</i>"

    await update.message.reply_text(
        status_msg,
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
        parse_mode=ParseMode.HTML
    )

async def start_manual_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_state.is_running = True
    bot_state.win_count = 0
    bot_state.consecutive_losses = 0
    bot_state.current_trade_amount = 50
    bot_state.waiting_for_result = False
    bot_state.cooldown_end_time = 0
    bot_state.current_strategy_index = 0

    if bot_state.start_sticker_id:
        for chat_id in CHANNEL_IDS:
            try:
                await context.bot.send_sticker(chat_id=chat_id, sticker=bot_state.start_sticker_id)
            except Exception as e:
                logger.error(f"স্টার্ট স্টিকার পাঠাতে সমস্যা: {e}")

    await update.message.reply_text("✅ ম্যানুয়ালি সিগন্যাল সেশন শুরু হয়েছে!")

async def stop_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_state.is_running = False
    bot_state.waiting_for_result = False
    bot_state.cooldown_end_time = 0
    await update.message.reply_text("🛑 সিগন্যাল ম্যানুয়ালি বন্ধ করা হয়েছে।")

# Sticker Processors
async def ask_for_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sticker_type = STICKER_STATES.get(update.message.text)
    if sticker_type:
        context.user_data['sticker_state'] = sticker_type
        await update.message.reply_text(f"দয়া করে {update.message.text} এর জন্য একটি স্টিকার পাঠান:")
        return CHOOSING_STICKER
    return ConversationHandler.END

async def save_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.sticker:
        await update.message.reply_text("❌ দয়া করে একটি স্টিকার পাঠান!")
        return CHOOSING_STICKER
    
    file_id = update.message.sticker.file_id
    state = context.user_data.get('sticker_state')
    
    if state == 'win':
        bot_state.win_sticker_id = file_id
    elif state == 'loss':
        bot_state.loss_sticker_id = file_id
    elif state == 'start':
        bot_state.start_sticker_id = file_id
    elif state == 'end':
        bot_state.end_sticker_id = file_id
    
    bot_state.save_data()
    await update.message.reply_text("✅ স্টিকার সফলভাবে সেভ হয়েছে!")
    return ConversationHandler.END

# Forward & Voice Processors
async def ask_forward_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📩 দয়া করে ফরওয়ার্ড করার জন্য টেক্সট/মেসেজটি এখানে লিখুন অথবা ফরওয়ার্ড করুন:")
    return WAITING_FORWARD_MSG

async def save_forward_msg(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot_state.forward_msg_id = update.message.message_id
    bot_state.forward_chat_id = update.message.chat_id
    bot_state.save_data()
    await update.message.reply_text("✅ ফরওয়ার্ড মেসেজ সফলভাবে সেভ হয়েছে!")
    return ConversationHandler.END

async def ask_for_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🎙️ দয়া করে আপনার ভয়েস মেসেজটি এখানে রেকর্ড করে অথবা অন্য চ্যাট থেকে ফরওয়ার্ড করে পাঠান:")
    return WAITING_VOICE_MSG

async def save_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.voice or update.message.audio:
        bot_state.voice_msg_id = update.message.message_id
        bot_state.voice_chat_id = update.message.chat_id
        bot_state.save_data()
        await update.message.reply_text("✅ ভয়েস মেসেজ সফলভাবে সেভ হয়েছে!")
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ এটি ভয়েস মেসেজ নয়! অনুগ্রহ করে সঠিক ভয়েস ফাইল পাঠান।")
        return WAITING_VOICE_MSG

# Video Processors
async def ask_trading_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("🎬 কালার ট্রেডিং ভিডিও এর মেসেজটি পোস্ট বা ফরওয়ার্ড করুন:")
    return WAITING_TRADING_VIDEO

async def save_trading_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot_state.trading_video_msg_id = update.message.message_id
    bot_state.trading_video_chat_id = update.message.chat_id
    bot_state.save_data()
    await update.message.reply_text("✅ কালার ট্রেডিং ভিডিও মেসেজ সেভ হয়েছে!")
    return ConversationHandler.END

async def ask_account_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("📝 একাউন্ট ক্রিয়েট ভিডিও এর মেসেজটি পোস্ট বা ফরওয়ার্ড করুন:")
    return WAITING_ACCOUNT_VIDEO

async def save_account_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot_state.account_video_msg_id = update.message.message_id
    bot_state.account_video_chat_id = update.message.chat_id
    bot_state.save_data()
    await update.message.reply_text("✅ একাউন্ট ক্রিয়েট ভিডিও মেসেজ সেভ হয়েছে!")
    return ConversationHandler.END

# Timers Set Execution
async def handle_timer_set(update: Update, timer_num: int, time_text: str) -> int:
    dt, raw_text = parse_bengali_time(time_text)
    if not dt:
        await update.message.reply_text("❌ সময় ঠিকমতো গ্রহণ করা সম্ভব হয়নি! আবার টাইমার বাটনে চাপুন এবং সঠিক ফরমেটে লিখুন (যেমন: ১০:০০ বা 10:00 AM বা রাত ৮:৩০)।")
        return ConversationHandler.END
    
    bot_state.scheduled_times[timer_num] = {
        "time_str": raw_text,
        "next_dt_iso": dt.isoformat(),
        "alert_sent_10": False,
        "alert_sent_5": False
    }
    bot_state.save_data()
    
    period_name = get_bangla_period_name(dt)
    time_digits = format_bangla_time_digits(dt)
    await update.message.reply_text(
        f"✅ <b>টাইমার {timer_num} সফলভাবে সেভ হয়েছে!</b>\n📅 {period_name} ({time_digits} টা)",
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

async def ask_t1(u, c): await u.message.reply_text("⏰ <b>১ম সিগন্যাল টাইম লিখে দিন:</b>\n(যেমন: <code>১০:০০</code> বা <code>10:00 AM</code>)", parse_mode=ParseMode.HTML); return WAITING_FOR_TIME_1
async def set_t1(u, c): return await handle_timer_set(u, 1, u.message.text)
async def ask_t2(u, c): await u.message.reply_text("⏰ <b>২য় সিগন্যাল টাইম লিখে দিন:</b>\n(যেমন: <code>১২:০০</code> বা <code>12:00 PM</code>)", parse_mode=ParseMode.HTML); return WAITING_FOR_TIME_2
async def set_t2(u, c): return await handle_timer_set(u, 2, u.message.text)
async def ask_t3(u, c): await u.message.reply_text("⏰ <b>৩য় সিগন্যাল টাইম লিখে দিন:</b>\n(যেমন: <code>৩:০০</code> বা <code>3:00 PM</code>)", parse_mode=ParseMode.HTML); return WAITING_FOR_TIME_3
async def set_t3(u, c): return await handle_timer_set(u, 3, u.message.text)
async def ask_t4(u, c): await u.message.reply_text("⏰ <b>৪র্থ সিগন্যাল টাইম লিখে দিন:</b>\n(যেমন: <code>৫:০০</code> বা <code>5:00 PM</code>)", parse_mode=ParseMode.HTML); return WAITING_FOR_TIME_4
async def set_t4(u, c): return await handle_timer_set(u, 4, u.message.text)
async def ask_t5(u, c): await u.message.reply_text("⏰ <b>৫ম সিগন্যাল টাইম লিখে দিন:</b>\n(যেমন: <code>৭:০০</code> বা <code>7:00 PM</code>)", parse_mode=ParseMode.HTML); return WAITING_FOR_TIME_5
async def set_t5(u, c): return await handle_timer_set(u, 5, u.message.text)
async def ask_t6(u, c): await u.message.reply_text("⏰ <b>৬ষ্ঠ সিগন্যাল টাইম লিখে দিন:</b>\n(যেমন: <code>৯:০০</code> বা <code>9:00 PM</code>)", parse_mode=ParseMode.HTML); return WAITING_FOR_TIME_6
async def set_t6(u, c): return await handle_timer_set(u, 6, u.message.text)

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("বাতিল করা হয়েছে।")
    return ConversationHandler.END

async def fetch_lottery_data(client: httpx.AsyncClient) -> list:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://draw.ar-lottery01.com/",
        "Origin": "https://draw.ar-lottery01.com",
        "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin"
    }
    try:
        response = await client.get(API_URL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get('data', {}).get('list', [])
        else:
            logger.error(f"API এরর স্ট্যাটাস: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"API ফেচ সমস্যা: {e}")
        return []

async def handle_session_end(app):
    bot_state.is_running = False
    bot_state.waiting_for_result = False
    bot_state.cooldown_end_time = 0
    bot_state.win_count = 0
    bot_state.current_trade_amount = 50

    if bot_state.end_sticker_id:
        for chat_id in CHANNEL_IDS:
            try:
                await app.bot.send_sticker(chat_id=chat_id, sticker=bot_state.end_sticker_id)
            except Exception as e:
                logger.error(f"এন্ড স্টিকার এরর: {e}")

    await asyncio.sleep(4)

    if bot_state.forward_msg_id and bot_state.forward_chat_id:
        for chat_id in CHANNEL_IDS:
            try:
                await app.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=bot_state.forward_chat_id,
                    message_id=bot_state.forward_msg_id
                )
            except Exception as e:
                logger.error(f"ফরওয়ার্ড মেসেজ এরর: {e}")

    await asyncio.sleep(4)

    if bot_state.voice_msg_id and bot_state.voice_chat_id:
        for chat_id in CHANNEL_IDS:
            try:
                await app.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=bot_state.voice_chat_id,
                    message_id=bot_state.voice_msg_id
                )
            except Exception as e:
                logger.error(f"ভয়েস মেসেজ এরর: {e}")

    await asyncio.sleep(4)

    next_time_str = get_next_scheduled_info()
    next_signal_msg = (
        f"💎 <b>পরবর্তী সিগন্যাল টাইম:</b> <b>{next_time_str}</b>\n🚀 <i>সবাই ব্যালেন্স রিচার্জ করে রেডি থাকুন!</i>"
        if next_time_str else
        "🎉 <b>আজকের সকল সিগন্যাল সেশন সম্পন্ন!</b>\n🚀 <i>পরবর্তী সেশনের জন্য প্রস্তুত থাকুন!</i>"
    )

    for chat_id in CHANNEL_IDS:
        try:
            await app.bot.send_message(chat_id=chat_id, text=next_signal_msg, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"নোটিশ এরর: {e}")

    if bot_state.account_video_msg_id and bot_state.account_video_chat_id:
        await asyncio.sleep(600)
        for chat_id in CHANNEL_IDS:
            try:
                await app.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=bot_state.account_video_chat_id,
                    message_id=bot_state.account_video_msg_id
                )
            except Exception as e:
                logger.error(f"একাউন্ট ভিডিও এরর: {e}")

    if bot_state.trading_video_msg_id and bot_state.trading_video_chat_id:
        await asyncio.sleep(300 if bot_state.account_video_msg_id else 900)
        for chat_id in CHANNEL_IDS:
            try:
                await app.bot.forward_message(
                    chat_id=chat_id,
                    from_chat_id=bot_state.trading_video_chat_id,
                    message_id=bot_state.trading_video_msg_id
                )
            except Exception as e:
                logger.error(f"কালার ট্রেডিং ভিডিও এরর: {e}")

# Signal Execution Loop
async def signal_loop(app) -> None:
    logger.info("ব্যাকগ্রাউন্ড সিগন্যাল লুপ রানিং...")
    last_checked_issue = ""
    
    async with httpx.AsyncClient(timeout=API_TIMEOUT, follow_redirects=True) as client:
        while True:
            try:
                now = datetime.now(TIMEZONE)

                if not bot_state.is_running:
                    for timer_id, timer_data in bot_state.scheduled_times.items():
                        iso_str = timer_data.get("next_dt_iso")
                        if iso_str:
                            target_time = datetime.fromisoformat(iso_str)
                            time_diff = (target_time - now).total_seconds()

                            if 300 < time_diff <= 600 and not timer_data.get("alert_sent_10"):
                                timer_data["alert_sent_10"] = True
                                bot_state.save_data()
                                alert_msg = create_10min_alert_message()
                                for chat_id in CHANNEL_IDS:
                                    try:
                                        await app.bot.send_message(chat_id=chat_id, text=alert_msg, parse_mode=ParseMode.HTML)
                                    except Exception as e:
                                        logger.error(f"১০ মিনিটের অ্যালার্ট সমস্যা: {e}")

                            if 0 < time_diff <= 300 and not timer_data.get("alert_sent_5"):
                                timer_data["alert_sent_5"] = True
                                bot_state.save_data()
                                period_name = get_bangla_period_name(target_time)
                                time_digits = format_bangla_time_digits(target_time)

                                alert_msg = (
                                    "⏰ <b>রেডি থাকুন!</b>\n"
                                    f"🚀 <b>{period_name} {time_digits} টায়</b> সিগন্যাল শুরু হবে!"
                                )
                                for chat_id in CHANNEL_IDS:
                                    try:
                                        await app.bot.send_message(chat_id=chat_id, text=alert_msg, parse_mode=ParseMode.HTML)
                                    except Exception as e:
                                        logger.error(f"৫ মিনিটের অ্যালার্ট সমস্যা: {e}")

                            if time_diff <= 0:
                                bot_state.is_running = True
                                bot_state.waiting_for_result = False
                                bot_state.cooldown_end_time = 0
                                bot_state.current_strategy_index = 0
                                
                                next_day_dt = target_time + timedelta(days=1)
                                timer_data["next_dt_iso"] = next_day_dt.isoformat()
                                timer_data["alert_sent_10"] = False
                                timer_data["alert_sent_5"] = False
                                bot_state.save_data()

                                bot_state.win_count = 0
                                bot_state.consecutive_losses = 0
                                bot_state.current_trade_amount = 50

                                if bot_state.start_sticker_id:
                                    for chat_id in CHANNEL_IDS:
                                        try:
                                            await app.bot.send_sticker(chat_id=chat_id, sticker=bot_state.start_sticker_id)
                                        except Exception as e:
                                            logger.error(f"স্টার্ট স্টিকার এরর: {e}")
                                break

                if bot_state.is_running:
                    data = await fetch_lottery_data(client)
                    if data:
                        current_issue = str(data[0].get('issueNumber'))

                        if current_issue != last_checked_issue:
                            last_checked_issue = current_issue

                            if bot_state.waiting_for_result and bot_state.last_period:
                                target_item = next((x for x in data if str(x.get('issueNumber')) == bot_state.last_period), None)
                                
                                if target_item:
                                    current_number = int(target_item.get('number', 0))
                                    current_result = "BIG" if current_number >= 5 else "SMALL"
                                    is_win = (bot_state.last_prediction == current_result)

                                    for chat_id in CHANNEL_IDS:
                                        try:
                                            if is_win and bot_state.win_sticker_id:
                                                await app.bot.send_sticker(chat_id=chat_id, sticker=bot_state.win_sticker_id)
                                            elif not is_win and bot_state.loss_sticker_id:
                                                await app.bot.send_sticker(chat_id=chat_id, sticker=bot_state.loss_sticker_id)
                                        except Exception as e:
                                            logger.error(f"স্টিকার পাঠাতে সমস্যা: {e}")

                                    if is_win:
                                        bot_state.win_count += 1
                                        bot_state.consecutive_losses = 0
                                        bot_state.current_trade_amount = 50

                                        if bot_state.win_count >= 5:
                                            bot_state.is_running = False
                                            bot_state.waiting_for_result = False
                                            asyncio.create_task(handle_session_end(app))
                                            continue
                                    else:
                                        bot_state.consecutive_losses += 1
                                        bot_state.current_trade_amount *= 2
                                        bot_state.current_strategy_index += 1 
                                        
                                        if bot_state.consecutive_losses % 3 == 0:
                                            for chat_id in CHANNEL_IDS:
                                                try:
                                                    await app.bot.send_message(chat_id=chat_id, text=LOSS_STREAK_MESSAGE, parse_mode=ParseMode.HTML)
                                                except Exception as e:
                                                    logger.error(f"রিমাইন্ডার এরর: {e}")

                                    bot_state.waiting_for_result = False
                                    bot_state.cooldown_end_time = time.time() + 10

                        if bot_state.is_running and not bot_state.waiting_for_result and time.time() >= bot_state.cooldown_end_time:
                            pred = predict_ai_sure_shot(data, bot_state.current_strategy_index)
                            if pred:
                                next_issue = str(int(current_issue) + 1)
                                msg = create_prediction_message(next_issue, pred, bot_state.current_trade_amount)
                                
                                for chat_id in CHANNEL_IDS:
                                    try:
                                        await app.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
                                    except Exception as e:
                                        logger.error(f"সিগন্যাল পাঠাতে ব্যর্থ: {e}")

                                bot_state.last_period = next_issue
                                bot_state.last_prediction = pred
                                bot_state.waiting_for_result = True

                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"লুপে অনাকাঙ্ক্ষিত ত্রুটি: {e}")
                await asyncio.sleep(2)

async def post_init(application) -> None:
    asyncio.create_task(signal_loop(application))

def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # 1. Timer Handlers
    for i in range(1, 7):
        conv = ConversationHandler(
            entry_points=[MessageHandler(filters.Regex(f'^⏰ টাইমার {i}$'), globals()[f"ask_t{i}"])],
            states={globals()[f"WAITING_FOR_TIME_{i}"]: [MessageHandler(filters.TEXT & ~filters.COMMAND, globals()[f"set_t{i}"])]},
            fallbacks=[CommandHandler("cancel", cancel_conv)],
            per_chat=True,
            per_user=True
        )
        app.add_handler(conv)

    # 2. Forward Message Handler
    forward_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📩 ফরওয়ার্ড মেসেজ সেট$'), ask_forward_msg)],
        states={WAITING_FORWARD_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, save_forward_msg)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )
    app.add_handler(forward_conv)

    # 3. Voice Message Handler
    voice_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🎙️ ভয়েস ফরওয়ার্ড$'), ask_for_voice)],
        states={WAITING_VOICE_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, save_voice)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )
    app.add_handler(voice_conv)

    # 4. Media Videos Handlers
    trading_video_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🎬 কালার ট্রেডিং ভিডিও$'), ask_trading_video)],
        states={WAITING_TRADING_VIDEO: [MessageHandler(filters.ALL & ~filters.COMMAND, save_trading_video)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )
    app.add_handler(trading_video_conv)

    account_video_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📝 একাউন্ট ক্রিয়েট ভিডিও$'), ask_account_video)],
        states={WAITING_ACCOUNT_VIDEO: [MessageHandler(filters.ALL & ~filters.COMMAND, save_account_video)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )
    app.add_handler(account_video_conv)

    # 5. Sticker Handler
    sticker_pattern = f"^({'|'.join(re.escape(k) for k in STICKER_STATES.keys())})$"
    sticker_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(sticker_pattern), ask_for_sticker)],
        states={CHOOSING_STICKER: [MessageHandler(filters.Sticker.ALL, save_sticker)]},
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )
    app.add_handler(sticker_conv)

    # 6. Basic Bot Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.Regex('^🟢 ম্যানুয়াল সিগন্যাল শুরু$'), start_manual_signal))
    app.add_handler(MessageHandler(filters.Regex('^🔴 সিগন্যাল অফ$'), stop_signal))

    app.run_polling()

if __name__ == '__main__':
    main()
