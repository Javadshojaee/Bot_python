import os
import logging
import threading
import uuid

import arabic_reshaper
from bidi.algorithm import get_display
from dotenv import load_dotenv
from flask import Flask
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# بارگذاری تنظیمات از فایل .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# کد فعال‌سازی اختصاصی خریداران (Jam87D)
SECRET_ACTIVATION_CODE = "Jam87D"

# تنظیم لاگ
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# مراحل مکالمه: بررسی کد، گرفتن عکس، گرفتن متن، گرفتن رنگ
CHECK_CODE, GET_PHOTO, GET_TEXT, GET_COLOR = range(4)
RESTART_TEXT = "🔄 شروع مجدد / لغو"

REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [[RESTART_TEXT]],
    resize_keyboard=True,
)


def get_font(size: int):
    """پیدا کردن فونت وزیر بولد کنار فایل main.py."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_names = [
        "Vazirmatn-Bold.ttf",
        "Vazir-Bold.ttf",
        "Vazirmatn_Bold.ttf",
        "Vazir.ttf",
    ]

    for name in font_names:
        font_path = os.path.join(base_dir, name)
        if os.path.isfile(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except OSError:
                logger.exception("فونت پیدا شد اما بارگذاری نشد: %s", font_path)

    logger.warning("فونت وزیر پیدا نشد؛ از فونت پیش‌فرض استفاده می‌شود.")
    return ImageFont.load_default()


def get_user_paths(update: Update):
    """ساخت مسیر فایل‌های موقت مخصوص هر کاربر."""
    user_id = update.effective_user.id
    unique_id = uuid.uuid4().hex[:8]
    photo_path = f"temp_{user_id}_{unique_id}.jpg"
    output_path = f"sticker_{user_id}_{unique_id}.webp"
    return photo_path, output_path


def fix_persian_text(text: str) -> str:
    """اصلاح تخصصی حروف فارسی برای چاپ دقیق و درست روی عکس با Pillow."""
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text[::-1]
    except Exception:
        logger.exception("خطا در پردازش متن فارسی برای عکس")
        return text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """شروع ربات و درخواست کد فعال‌سازی از خریدار."""
    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "سلام! 👋 به ربات ساخت استیکر «بات مارکت» خوش آمدید.\n\n"
            "لطفاً **کد فعال‌سازی** دریافتی پس از خرید از سایت را وارد کنید: 🔑",
            reply_markup=REPLY_KEYBOARD,
        )
    return CHECK_CODE


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """لغو فرایند فعلی و بازگشت به مرحله بررسی کد."""
    context.user_data.clear()
    if update.message:
        await update.message.reply_text(
            "فرایند لغو شد. برای ورود مجدد، لطفاً کد فعال‌سازی را بفرستید:",
            reply_markup=REPLY_KEYBOARD,
        )
    return CHECK_CODE


async def check_activation_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بررسی صحت کد فعال‌سازی وارد شده توسط کاربر."""
    if not update.message or not update.message.text:
        return CHECK_CODE

    user_input = update.message.text.strip()

    if user_input == RESTART_TEXT:
        return await cancel(update, context)

    # مقایسه کد وارد شده با کد مخفی Jam87D
    if user_input == SECRET_ACTIVATION_CODE:
        context.user_data["is_activated"] = True
        await update.message.reply_text(
            "✅ کد فعال‌سازی با موفقیت تأیید شد!\n\n"
            "حالا عکسی را که می‌خواهی به استیکر تبدیل شود بفرست 📷",
            reply_markup=REPLY_KEYBOARD,
        )
        return GET_PHOTO
    else:
        await update.message.reply_text(
            "❌ کد فعال‌سازی اشتباه است!\n"
            "لطفاً کد درستی را که پس از خرید از سایت دریافت کرده‌اید دوباره وارد کنید:",
            reply_markup=REPLY_KEYBOARD,
        )
        return CHECK_CODE


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت عکس."""
    if not update.message:
        return GET_PHOTO

    if update.message.text and update.message.text.strip() == RESTART_TEXT:
        return await cancel(update, context)

    if not context.user_data.get("is_activated"):
        return await start(update, context)

    if not update.message.photo:
        await update.message.reply_text("لطفاً یک تصویر ارسال کنید.", reply_markup=REPLY_KEYBOARD)
        return GET_PHOTO

    photo_path, output_path = get_user_paths(update)
    photo_file = await update.message.photo[-1].get_file()
    await photo_file.download_to_drive(photo_path)

    context.user_data["photo_path"] = photo_path
    context.user_data["output_path"] = output_path

    await update.message.reply_text(
        "📷 عکس دریافت شد!\nحالا متنی را که می‌خواهی روی عکس باشد بفرست.",
        reply_markup=REPLY_KEYBOARD,
    )
    return GET_TEXT


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دریافت متن."""
    if not update.message or not update.message.text:
        return GET_TEXT

    user_text = update.message.text.strip()

    if user_text == RESTART_TEXT:
        return await cancel(update, context)

    if not context.user_data.get("photo_path"):
        await update.message.reply_text("اول عکس را بفرست.", reply_markup=REPLY_KEYBOARD)
        return GET_PHOTO

    processed_text = fix_persian_text(user_text)
    context.user_data["text"] = processed_text

    await update.message.reply_text(
        "✍️ متن ثبت شد!\n"
        "حالا رنگ متن را بفرست؛ مثلاً «آبی»، «قرمز»، «سفید» یا کد HEX مثل `#FF0000`.",
        reply_markup=REPLY_KEYBOARD,
    )
    return GET_COLOR


def parse_color(color_input: str):
    """تبدیل نام رنگ فارسی یا کد HEX به رنگ قابل استفاده در Pillow."""
    normalized = color_input.strip().lower()
    persian_colors = {
        "سفید": "white",
        "مشکی": "black",
        "سیاه": "black",
        "قرمز": "red",
        "آبی": "blue",
        "سبز": "green",
        "زرد": "yellow",
        "نارنجی": "orange",
        "بنفش": "purple",
        "صورتی": "pink",
        "قهوه‌ای": "brown",
        "قهوه ای": "brown",
    }
    return persian_colors.get(normalized, color_input.strip())


async def handle_color(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """ساخت و ارسال فایل استیکر."""
    if not update.message or not update.message.text:
        return GET_COLOR

    color_input = update.message.text.strip()

    if color_input == RESTART_TEXT:
        return await cancel(update, context)

    photo_path = context.user_data.get("photo_path")
    output_path = context.user_data.get("output_path")
    text = context.user_data.get("text")

    if not photo_path or not output_path or not text:
        await update.message.reply_text(
            "اطلاعات منقضی شد. لطفاً دوباره از /start شروع کن.",
            reply_markup=REPLY_KEYBOARD,
        )
        return GET_PHOTO

    text_color = parse_color(color_input)

    try:
        Image.new("RGB", (1, 1), color=text_color)

        with Image.open(photo_path) as source_image:
            img = source_image.convert("RGBA")

        img.thumbnail((512, 512))
        draw = ImageDraw.Draw(img)

        font_size = 40
        font = get_font(font_size)

        max_text_width = max(20, img.width - 24)
        while font_size > 12:
            font = get_font(font_size)
            bbox = draw.textbbox((0, 0), text, font=font, stroke_width=0)
            if bbox[2] - bbox[0] <= max_text_width:
                break
            font_size -= 2

        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=0)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (img.width - text_width) / 2 - bbox[0]
        y = max(5, img.height - text_height - 20 - bbox[1])

        draw.text(
            (x, y),
            text,
            font=font,
            fill=text_color,
            stroke_width=2,
            stroke_fill="black",
        )

        img.save(output_path, format="WEBP", quality=95)

        await update.message.reply_text("⏳ دارم استیکرت را می‌سازم...")

        with open(output_path, "rb") as sticker_file:
            await update.message.reply_document(
                document=sticker_file,
                filename="sticker.webp",
                caption="✨ استیکرت آماده شد!",
                reply_markup=REPLY_KEYBOARD,
            )

    except (OSError, ValueError) as error:
        logger.exception("خطا هنگام ساخت استیکر")
        await update.message.reply_text(
            f"ساخت استیکر انجام نشد. رنگ را با نام ساده (مثل آبی) یا کد HEX بفرست.\nخطا: {error}",
            reply_markup=REPLY_KEYBOARD,
        )
        return GET_COLOR

    finally:
        for path in (photo_path, output_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    logger.warning("پاک‌کردن فایل موقت ناموفق بود: %s", path)

    context.user_data.clear()
    await update.message.reply_text(
        "برای ساخت استیکر جدید، لطفاً دوباره کد فعال‌سازی را وارد کنید:",
        reply_markup=REPLY_KEYBOARD,
    )
    return CHECK_CODE


# وب‌سرور Flask
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


def run_flask():
    app.run(host="0.0.0.0", port=8080, use_reloader=False)


def main():
    if not BOT_TOKEN:
        raise RuntimeError("توکن ربات پیدا نشد. لطفاً متغیر محیطی BOT_TOKEN را تنظیم کنید.")

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHECK_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, check_activation_code)
            ],
            GET_PHOTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_photo),
                MessageHandler(filters.PHOTO, handle_photo),
            ],
            GET_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                MessageHandler(filters.PHOTO, handle_photo),
            ],
            GET_COLOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_color),
                MessageHandler(filters.PHOTO, handle_photo),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
    )

    application.add_handler(conversation_handler)

    print("🤖 ربات روشن شد.")
    application.run_polling()


if __name__ == "__main__":
    main()
