"""
main.py - النسخة المحدثة
Workflow:
  صورة → معاينة → [New Post / GAIN / تعديل / إلغاء]
  New Post → كود الورقة → [نشر دابا / جدولة]
  GAIN     → ينشر نفس الصورة مع description الفوز تلقائياً
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton,
    InlineKeyboardMarkup, Message, PhotoSize,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from ai_service import (
    analyze_bet_image, generate_win_description,
    build_post_caption, build_win_caption
)

# ===================================================
# إعداد اللوغ
# ===================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# ===================================================
# تحميل الإعدادات
# ===================================================
load_dotenv()

BOT_TOKEN    = os.getenv("BOT_TOKEN")
ADMIN_ID     = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID   = os.getenv("CHANNEL_ID")
PROMO_CODE   = os.getenv("PROMO_CODE",  "WINO27")
REG_LINK     = os.getenv("REG_LINK",    "https://marocco.bonus-linebet.com/wino27")
ANDROID_LINK = os.getenv("ANDROID_LINK", "")
IPHONE_LINK  = os.getenv("IPHONE_LINK",  "")
VIDEO_LINK   = os.getenv("VIDEO_LINK",   "")

# ===================================================
# تهيئة البوت
# ===================================================
bot       = Bot(token=BOT_TOKEN)
dp        = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone="Africa/Casablanca")

# { post_id: { file_id, ai_description, full_caption, channel_message_id, bet_code } }
pending_posts: Dict[str, dict] = {}


# ===================================================
# حالات FSM
# ===================================================
class BetStates(StatesGroup):
    waiting_for_bet_code      = State()
    waiting_for_schedule_time = State()
    waiting_for_caption_edit  = State()


# ===================================================
# لوحات الأزرار
# ===================================================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def kb_preview(post_id: str) -> InlineKeyboardMarkup:
    """4 أزرار المعاينة"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ New Post", callback_data=f"new_post:{post_id}"),
            InlineKeyboardButton(text="🏆 GAIN",     callback_data=f"gain:{post_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ تعديل",   callback_data=f"edit:{post_id}"),
            InlineKeyboardButton(text="❌ إلغاء",   callback_data=f"cancel:{post_id}"),
        ],
    ])


def kb_publish(post_id: str) -> InlineKeyboardMarkup:
    """زري النشر بعد إدخال الكود"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 نشر دابا", callback_data=f"post_now:{post_id}"),
            InlineKeyboardButton(text="🕐 جدولة",    callback_data=f"schedule:{post_id}"),
        ],
    ])


# ===================================================
# أوامر الإدارة
# ===================================================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer(
        "👋 <b>مرحبا!</b>\n\n"
        "📸 بعتلي صورة ديال ورقة البيت وأنا نتكفل بالباقي 🇲🇦\n\n"
        "<b>الأوامر:</b>\n"
        "/setpromo [كود] — كود البرومو\n"
        "/setlink [لينك] — لينك التسجيل\n"
        "/setandroid [لينك] — لينك Android\n"
        "/setios [لينك] — لينك iPhone\n"
        "/setvideo [لينك] — لينك الفيديو\n"
        "/info — الإعدادات الحالية",
        parse_mode="HTML"
    )


@dp.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message.from_user.id): return
    await message.answer(
        f"📋 <b>الإعدادات الحالية:</b>\n\n"
        f"🎁 كود البرومو: <code>{PROMO_CODE}</code>\n"
        f"🔗 لينك التسجيل: {REG_LINK}\n"
        f"📱 Android: {ANDROID_LINK or '❌ مازال ما تحددش'}\n"
        f"🍎 iPhone: {IPHONE_LINK or '❌ مازال ما تحددش'}\n"
        f"🎥 فيديو: {VIDEO_LINK or '❌ مازال ما تحددش'}\n"
        f"📢 الشانيل: <code>{CHANNEL_ID}</code>",
        parse_mode="HTML"
    )


@dp.message(Command("setpromo"))
async def cmd_set_promo(message: Message):
    if not is_admin(message.from_user.id): return
    global PROMO_CODE
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ كتب: <code>/setpromo WINO27</code>", parse_mode="HTML"); return
    PROMO_CODE = parts[1].strip()
    await message.answer(f"✅ كود البرومو: <code>{PROMO_CODE}</code>", parse_mode="HTML")


@dp.message(Command("setlink"))
async def cmd_set_link(message: Message):
    if not is_admin(message.from_user.id): return
    global REG_LINK
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ كتب: <code>/setlink https://...</code>", parse_mode="HTML"); return
    REG_LINK = parts[1].strip()
    await message.answer("✅ لينك التسجيل تبدل!")


@dp.message(Command("setandroid"))
async def cmd_set_android(message: Message):
    if not is_admin(message.from_user.id): return
    global ANDROID_LINK
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ كتب: <code>/setandroid https://...</code>", parse_mode="HTML"); return
    ANDROID_LINK = parts[1].strip()
    await message.answer("✅ لينك Android تبدل!")


@dp.message(Command("setios"))
async def cmd_set_ios(message: Message):
    if not is_admin(message.from_user.id): return
    global IPHONE_LINK
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ كتب: <code>/setios https://...</code>", parse_mode="HTML"); return
    IPHONE_LINK = parts[1].strip()
    await message.answer("✅ لينك iPhone تبدل!")


@dp.message(Command("setvideo"))
async def cmd_set_video(message: Message):
    if not is_admin(message.from_user.id): return
    global VIDEO_LINK
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ كتب: <code>/setvideo https://...</code>", parse_mode="HTML"); return
    VIDEO_LINK = parts[1].strip()
    await message.answer("✅ لينك الفيديو تبدل!")


# ===================================================
# استقبال الصورة
# ===================================================
@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return

    processing_msg = await message.answer("⏳ كنحلل الصورة... 🔍")

    try:
        photo: PhotoSize = message.photo[-1]
        buffer = BytesIO()
        await bot.download(photo, destination=buffer)
        image_bytes = buffer.getvalue()

        ai_description = await analyze_bet_image(image_bytes)

        post_id = str(message.message_id)
        pending_posts[post_id] = {
            "file_id":            photo.file_id,
            "ai_description":     ai_description,
            "full_caption":       None,
            "channel_message_id": None,
            "bet_code":           None,
        }

        await processing_msg.delete()

        await message.answer_photo(
            photo=photo.file_id,
            caption=(
                f"👁 <b>معاينة:</b>\n\n{ai_description}\n\n"
                f"<i>الكود والروابط غيتزادو بعد ما تضغط New Post</i>"
            ),
            reply_markup=kb_preview(post_id),
            parse_mode="HTML",
        )

        await state.update_data(current_post_id=post_id)

    except Exception as e:
        logger.error(f"handle_photo error: {e}")
        await processing_msg.edit_text(f"❌ وقع خطأ:\n<code>{str(e)}</code>", parse_mode="HTML")


# ===================================================
# زر NEW POST — يطلب كود الورقة
# ===================================================
@dp.callback_query(F.data.startswith("new_post:"))
async def cb_new_post(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return

    post_id = callback.data.split(":", 1)[1]
    await state.update_data(current_post_id=post_id)
    await state.set_state(BetStates.waiting_for_bet_code)

    await callback.message.answer(
        "🔑 شنو كود الورقة؟\n\nمثال: <code>CVF21</code>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(BetStates.waiting_for_bet_code)
async def handle_bet_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return

    bet_code = message.text.strip().upper()
    data     = await state.get_data()
    post_id  = data.get("current_post_id")

    if post_id not in pending_posts:
        await message.answer("❌ البوست مكيلقاش، بعت الصورة من جديد")
        await state.clear(); return

    full_caption = build_post_caption(
        ai_description=pending_posts[post_id]["ai_description"],
        bet_code=bet_code,
        promo_code=PROMO_CODE,
        reg_link=REG_LINK,
        android_link=ANDROID_LINK,
        iphone_link=IPHONE_LINK,
        video_link=VIDEO_LINK,
    )

    pending_posts[post_id]["full_caption"] = full_caption
    pending_posts[post_id]["bet_code"]     = bet_code

    await message.answer_photo(
        photo=pending_posts[post_id]["file_id"],
        caption=f"👁 <b>معاينة نهائية:</b>\n\n{full_caption}",
        reply_markup=kb_publish(post_id),
        parse_mode="HTML",
    )

    await state.clear()


# ===================================================
# زر نشر دابا
# ===================================================
@dp.callback_query(F.data.startswith("post_now:"))
async def cb_post_now(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return

    post_id   = callback.data.split(":", 1)[1]
    post_data = pending_posts.get(post_id)

    if not post_data or not post_data.get("full_caption"):
        await callback.answer("❌ البوست مكيلقاش", show_alert=True); return

    try:
        sent = await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=post_data["file_id"],
            caption=post_data["full_caption"],
            parse_mode="HTML",
        )
        pending_posts[post_id]["channel_message_id"] = sent.message_id

        await callback.message.edit_caption(
            caption="✅ <b>تم النشر!</b> 🎉",
            reply_markup=None,
            parse_mode="HTML",
        )
        await callback.answer("✅ نشرنا!")

    except Exception as e:
        logger.error(f"post_now error: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


# ===================================================
# زر جدولة
# ===================================================
@dp.callback_query(F.data.startswith("schedule:"))
async def cb_schedule(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return

    post_id = callback.data.split(":", 1)[1]
    await state.update_data(current_post_id=post_id)
    await state.set_state(BetStates.waiting_for_schedule_time)

    now = datetime.now()
    await callback.message.answer(
        f"🕐 أدخل وقت النشر: <code>HH:MM</code>\n"
        f"مثال: <code>{(now.hour+1)%24:02d}:00</code>\n"
        f"⏰ الوقت الحالي: <b>{now.strftime('%H:%M')}</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(BetStates.waiting_for_schedule_time)
async def handle_schedule_time(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return

    try:
        hour, minute = map(int, message.text.strip().split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59): raise ValueError

        data      = await state.get_data()
        post_id   = data.get("current_post_id")
        post_data = pending_posts.get(post_id)

        if not post_data:
            await message.answer("❌ البوست مكيلقاش")
            await state.clear(); return

        now    = datetime.now()
        run_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_at <= now:
            run_at += timedelta(days=1)

        scheduler.add_job(
            _scheduled_post,
            trigger="date",
            run_date=run_at,
            args=[post_id, message.chat.id],
            id=f"post_{post_id}",
            replace_existing=True,
        )

        day = "غدا" if run_at.date() > now.date() else "اليوم"
        await message.answer(
            f"✅ <b>تمت الجدولة!</b>\n⏰ النشر {day} في <code>{run_at.strftime('%H:%M')}</code>",
            parse_mode="HTML"
        )
        await state.clear()

    except ValueError:
        await message.answer("❌ الصيغة خاطئة، مثال: <code>20:30</code>", parse_mode="HTML")


async def _scheduled_post(post_id: str, admin_chat_id: int):
    post_data = pending_posts.get(post_id)
    if not post_data: return
    try:
        sent = await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=post_data["file_id"],
            caption=post_data["full_caption"],
            parse_mode="HTML",
        )
        pending_posts[post_id]["channel_message_id"] = sent.message_id
        await bot.send_message(admin_chat_id, "✅ <b>تم النشر المجدول!</b> 🎉", parse_mode="HTML")
    except Exception as e:
        await bot.send_message(admin_chat_id, f"❌ فشل النشر المجدول:\n<code>{str(e)}</code>", parse_mode="HTML")


# ===================================================
# زر GAIN — ينشر نفس الصورة مع description الفوز
# ===================================================
@dp.callback_query(F.data.startswith("gain:"))
async def cb_gain(callback: CallbackQuery):
    if not is_admin(callback.from_user.id): return

    post_id   = callback.data.split(":", 1)[1]
    post_data = pending_posts.get(post_id)

    if not post_data:
        await callback.answer("❌ البوست مكيلقاش", show_alert=True); return

    processing = await callback.message.answer("⏳ كنحضر رسالة الفوز... 🏆")

    try:
        buffer = BytesIO()
        await bot.download(post_data["file_id"], destination=buffer)
        image_bytes = buffer.getvalue()

        win_desc    = await generate_win_description(image_bytes)
        win_caption = build_win_caption(win_desc, REG_LINK)

        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=post_data["file_id"],
            caption=win_caption,
            parse_mode="HTML",
        )

        await processing.delete()
        await callback.message.answer("🏆 <b>تم نشر رسالة الفوز!</b> 🎉", parse_mode="HTML")
        del pending_posts[post_id]

    except Exception as e:
        logger.error(f"gain error: {e}")
        await processing.edit_text(f"❌ خطأ:\n<code>{str(e)}</code>", parse_mode="HTML")

    await callback.answer()


# ===================================================
# زر تعديل الكابشن
# ===================================================
@dp.callback_query(F.data.startswith("edit:"))
async def cb_edit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return

    post_id   = callback.data.split(":", 1)[1]
    post_data = pending_posts.get(post_id)

    if not post_data:
        await callback.answer("❌ البوست مكيلقاش", show_alert=True); return

    await state.update_data(current_post_id=post_id)
    await state.set_state(BetStates.waiting_for_caption_edit)

    current = post_data.get("full_caption") or post_data.get("ai_description") or ""
    await callback.message.answer(
        f"✏️ <b>النص الحالي:</b>\n\n<blockquote>{current[:400]}</blockquote>\n\n📝 أرسل النص الجديد:",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(BetStates.waiting_for_caption_edit)
async def handle_caption_edit(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return

    data    = await state.get_data()
    post_id = data.get("current_post_id")

    if post_id not in pending_posts:
        await message.answer("❌ البوست مكيلقاش")
        await state.clear(); return

    pending_posts[post_id]["full_caption"] = message.text

    await message.answer_photo(
        photo=pending_posts[post_id]["file_id"],
        caption=f"👁 <b>معاينة محدثة:</b>\n\n{message.text}",
        reply_markup=kb_preview(post_id),
        parse_mode="HTML",
    )
    await state.clear()


# ===================================================
# زر إلغاء
# ===================================================
@dp.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id): return

    post_id = callback.data.split(":", 1)[1]
    if post_id in pending_posts:
        del pending_posts[post_id]

    try:
        await callback.message.edit_caption(caption="❌ تم إلغاء البوست", reply_markup=None)
    except Exception:
        pass

    await state.clear()
    await callback.answer("تم الإلغاء")


# ===================================================
# تشغيل البوت
# ===================================================
async def main():
    scheduler.start()
    logger.info("🤖 Bot v2 started!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())