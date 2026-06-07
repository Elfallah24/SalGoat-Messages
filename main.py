"""
main.py
-------
البوت الرئيسي لقناة البيتات
- استقبال صور أوراق البيت
- تحليل بجيميني
- معاينة مع أزرار
- نشر فوري أو مجدول
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
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    PhotoSize,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from gemini_service import analyze_bet_image

# ===================================================
# إعداد اللوغ
# ===================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ===================================================
# تحميل الإعدادات من .env
# ===================================================
load_dotenv()

BOT_TOKEN   = os.getenv("BOT_TOKEN")
ADMIN_ID    = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID  = os.getenv("CHANNEL_ID")        # مثال: @mychannel
PROMO_CODE  = os.getenv("PROMO_CODE", "PROMO2024")
REG_LINK    = os.getenv("REG_LINK", "https://linebet.com/register")

# ===================================================
# تهيئة البوت
# ===================================================
bot       = Bot(token=BOT_TOKEN)
dp        = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone="Africa/Casablanca")

# تخزين البوستات المعلقة في الذاكرة
# { post_id: { file_id, caption } }
pending_posts: Dict[str, dict] = {}


# ===================================================
# حالات FSM (مراحل المحادثة)
# ===================================================
class BetStates(StatesGroup):
    waiting_for_caption_edit  = State()   # انتظار نص تعديل الكابشن
    waiting_for_schedule_time = State()   # انتظار وقت الجدولة


# ===================================================
# دوال مساعدة
# ===================================================
def main_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """الأزرار الرئيسية للمعاينة"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ نشر دابا",  callback_data=f"post_now:{post_id}"),
            InlineKeyboardButton(text="🕐 جدولة",    callback_data=f"schedule:{post_id}"),
        ],
        [
            InlineKeyboardButton(text="✏️ تعديل",    callback_data=f"edit:{post_id}"),
            InlineKeyboardButton(text="❌ إلغاء",    callback_data=f"cancel:{post_id}"),
        ],
    ])


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ===================================================
# أوامر الإدارة
# ===================================================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        "👋 <b>مرحبا!</b>\n\n"
        "📸 بعتلي صورة ديال ورقة البيت\n"
        "وأنا نولد ليك caption بالدارجة 🇲🇦\n\n"
        "📋 <b>الأوامر:</b>\n"
        "/setpromo [كود] — تبديل كود البرومو\n"
        "/setlink [لينك] — تبديل لينك التسجيل\n"
        "/info — معلومات الإعدادات الحالية",
        parse_mode="HTML"
    )


@dp.message(Command("info"))
async def cmd_info(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        f"📋 <b>الإعدادات الحالية:</b>\n\n"
        f"🎁 كود البرومو: <code>{PROMO_CODE}</code>\n"
        f"🔗 لينك التسجيل: <code>{REG_LINK}</code>\n"
        f"📢 الشانيل: <code>{CHANNEL_ID}</code>",
        parse_mode="HTML"
    )


@dp.message(Command("setpromo"))
async def cmd_set_promo(message: Message):
    if not is_admin(message.from_user.id):
        return
    global PROMO_CODE
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ كتب هكا: <code>/setpromo YOURCODE</code>", parse_mode="HTML")
        return
    PROMO_CODE = parts[1].strip()
    await message.answer(
        f"✅ كود البرومو تبدل لـ: <code>{PROMO_CODE}</code>",
        parse_mode="HTML"
    )


@dp.message(Command("setlink"))
async def cmd_set_link(message: Message):
    if not is_admin(message.from_user.id):
        return
    global REG_LINK
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("❌ كتب هكا: <code>/setlink https://...</code>", parse_mode="HTML")
        return
    REG_LINK = parts[1].strip()
    await message.answer(f"✅ لينك التسجيل تبدل! ✓", parse_mode="HTML")


# ===================================================
# معالجة الصور (الوظيفة الأساسية)
# ===================================================
@dp.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    # رسالة "جاري التحليل..."
    processing_msg = await message.answer("⏳ كنحلل الورقة... صبر شوية 🔍")

    try:
        # تحميل أعلى جودة للصورة
        photo: PhotoSize = message.photo[-1]
        buffer = BytesIO()
        await bot.download(photo, destination=buffer)
        image_bytes = buffer.getvalue()

        # تحليل بجيميني
        caption = await analyze_bet_image(image_bytes, PROMO_CODE, REG_LINK)

        # حفظ البوست في الذاكرة
        post_id = str(message.message_id)
        pending_posts[post_id] = {
            "file_id": photo.file_id,
            "caption": caption,
        }

        await processing_msg.delete()

        # إرسال المعاينة مع الأزرار
        await message.answer_photo(
            photo=photo.file_id,
            caption=f"👁 <b>معاينة البوست:</b>\n\n{caption}",
            reply_markup=main_keyboard(post_id),
            parse_mode="HTML",
        )

        await state.update_data(current_post_id=post_id)

    except Exception as e:
        logger.error(f"خطأ في معالجة الصورة: {e}")
        await processing_msg.edit_text(
            f"❌ وقع خطأ، حاول مرة أخرى\n\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )


# ===================================================
# زر "نشر دابا"
# ===================================================
@dp.callback_query(F.data.startswith("post_now:"))
async def cb_post_now(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    post_id   = callback.data.split(":", 1)[1]
    post_data = pending_posts.get(post_id)

    if not post_data:
        await callback.answer("❌ البوست مكيلقاش، بعت الصورة من جديد", show_alert=True)
        return

    try:
        # النشر في الشانيل
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=post_data["file_id"],
            caption=post_data["caption"],
            parse_mode="HTML",
        )

        # تحديث رسالة المعاينة
        await callback.message.edit_caption(
            caption="✅ <b>تم النشر بنجاح!</b> 🎉",
            reply_markup=None,
            parse_mode="HTML",
        )

        del pending_posts[post_id]
        await callback.answer("✅ نشرنا!")

    except Exception as e:
        logger.error(f"خطأ في النشر: {e}")
        await callback.answer(f"❌ خطأ: {str(e)}", show_alert=True)


# ===================================================
# زر "جدولة"
# ===================================================
@dp.callback_query(F.data.startswith("schedule:"))
async def cb_schedule(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    post_id = callback.data.split(":", 1)[1]
    await state.update_data(current_post_id=post_id)
    await state.set_state(BetStates.waiting_for_schedule_time)

    now = datetime.now()
    await callback.message.answer(
        f"🕐 <b>متى تنشر؟</b>\n\n"
        f"كتب الوقت بهاد الشكل: <code>HH:MM</code>\n"
        f"مثال: <code>{(now.hour + 1) % 24:02d}:00</code>\n\n"
        f"⏰ الوقت الحالي: <b>{now.strftime('%H:%M')}</b>",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(BetStates.waiting_for_schedule_time)
async def handle_schedule_time(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        # تحقق من الصيغة
        hour, minute = map(int, message.text.strip().split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError

        data    = await state.get_data()
        post_id = data.get("current_post_id")
        post_data = pending_posts.get(post_id)

        if not post_data:
            await message.answer("❌ البوست مكيلقاش، بعت الصورة من جديد")
            await state.clear()
            return

        # احسب التاريخ والوقت
        now            = datetime.now()
        scheduled_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled_time <= now:
            scheduled_time += timedelta(days=1)

        # جدولة في APScheduler
        scheduler.add_job(
            post_to_channel,
            trigger="date",
            run_date=scheduled_time,
            args=[post_data["file_id"], post_data["caption"], post_id, message.chat.id],
            id=f"post_{post_id}",
            replace_existing=True,
        )

        day_str = "غدا" if scheduled_time.date() > now.date() else "اليوم"
        await message.answer(
            f"✅ <b>تمت الجدولة!</b>\n"
            f"⏰ النشر {day_str} في الساعة: <code>{scheduled_time.strftime('%H:%M')}</code>",
            parse_mode="HTML"
        )

        await state.clear()

    except (ValueError, AttributeError):
        await message.answer(
            "❌ الصيغة خاطئة!\n"
            "كتب هكا: <code>18:30</code>",
            parse_mode="HTML"
        )


# ===================================================
# زر "تعديل"
# ===================================================
@dp.callback_query(F.data.startswith("edit:"))
async def cb_edit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    post_id   = callback.data.split(":", 1)[1]
    post_data = pending_posts.get(post_id)

    if not post_data:
        await callback.answer("❌ البوست مكيلقاش", show_alert=True)
        return

    await state.update_data(current_post_id=post_id)
    await state.set_state(BetStates.waiting_for_caption_edit)

    await callback.message.answer(
        f"✏️ <b>النص الحالي:</b>\n\n"
        f"<blockquote>{post_data['caption']}</blockquote>\n\n"
        f"📝 أرسل النص الجديد:",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message(BetStates.waiting_for_caption_edit)
async def handle_caption_edit(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data    = await state.get_data()
    post_id = data.get("current_post_id")

    if post_id not in pending_posts:
        await message.answer("❌ البوست مكيلقاش")
        await state.clear()
        return

    # تحديث الكابشن
    pending_posts[post_id]["caption"] = message.text

    # إرسال معاينة جديدة
    await message.answer_photo(
        photo=pending_posts[post_id]["file_id"],
        caption=f"👁 <b>معاينة محدثة:</b>\n\n{message.text}",
        reply_markup=main_keyboard(post_id),
        parse_mode="HTML",
    )

    await state.clear()


# ===================================================
# زر "إلغاء"
# ===================================================
@dp.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    post_id = callback.data.split(":", 1)[1]
    if post_id in pending_posts:
        del pending_posts[post_id]

    await callback.message.edit_caption(
        caption="❌ تم إلغاء البوست",
        reply_markup=None,
    )
    await state.clear()
    await callback.answer("تم الإلغاء")


# ===================================================
# دالة النشر المجدول (كيتعيط بـ APScheduler)
# ===================================================
async def post_to_channel(file_id: str, caption: str, post_id: str, admin_chat_id: int):
    """تنشر في الشانيل في الوقت المحدد"""
    try:
        await bot.send_photo(
            chat_id=CHANNEL_ID,
            photo=file_id,
            caption=caption,
            parse_mode="HTML",
        )
        # إخبار الأدمين
        await bot.send_message(
            chat_id=admin_chat_id,
            text="✅ <b>تم النشر المجدول بنجاح!</b> 🎉",
            parse_mode="HTML",
        )
        if post_id in pending_posts:
            del pending_posts[post_id]

        logger.info(f"Post {post_id} published successfully")

    except Exception as e:
        logger.error(f"Error in scheduled post {post_id}: {e}")
        await bot.send_message(
            chat_id=admin_chat_id,
            text=f"❌ فشل النشر المجدول:\n<code>{str(e)}</code>",
            parse_mode="HTML",
        )


# ===================================================
# تشغيل البوت
# ===================================================
async def main():
    scheduler.start()
    logger.info("🤖 Bot started successfully!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
