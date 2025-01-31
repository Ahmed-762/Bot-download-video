import telebot
import yt_dlp
import os
import time
import threading
import validators
import subprocess
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
from keep_alive import keep_alive  # استيراد keep_alive.py

# إدخال رمز التوكن الخاص بالبوت
API_TOKEN = 'YOUR_BOT_TOKEN'

# إنشاء البوت
bot = telebot.TeleBot(API_TOKEN)

# إعداد تطبيق Flask
app = Flask(__name__)

# تخزين الروابط لتجنب مشاكل callback_data
user_links = {}

# دالة لتنزيل الفيديو والصوت
def download_media(url, format_type, resolution=None):
    try:
        ydl_opts = {
            'outtmpl': 'downloads/%(id)s.%(ext)s',
        }

        if format_type == "video":
            ydl_opts["format"] = f"bestvideo[height<={resolution}]+bestaudio/best"
        elif format_type == "audio":
            ydl_opts["format"] = "bestaudio"

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            file_ext = info_dict.get("ext", "unknown")
            file_path = f"downloads/{info_dict['id']}.{file_ext}"
        
        return file_path, info_dict['id'], file_ext
    except Exception as e:
        return None, None, None

# دالة لدمج الفيديو والصوت
def merge_video_audio(video_path, audio_path, output_path):
    try:
        command = [
            "ffmpeg", "-i", video_path, "-i", audio_path,
            "-c:v", "copy", "-c:a", "copy", output_path
        ]
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        return False
    return True

# دالة لمعالجة الرابط
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎥 أرسل رابط الفيديو الذي ترغب في تحميله:")
    bot.register_next_step_handler(message, handle_url)

# التحقق من صحة الرابط
def is_valid_url(url):
    return validators.url(url)

# دالة لاختيار نوع التنزيل (فيديو أو صوت)
def handle_url(message):
    url = message.text.strip()
    
    if not is_valid_url(url):
        bot.send_message(message.chat.id, "❌ الرابط غير صالح. يرجى إدخال رابط صالح.")
        bot.register_next_step_handler(message, handle_url)
        return
    
    user_links[message.chat.id] = url  # حفظ الرابط في القاموس
    
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("📹 فيديو", callback_data=f"video"),
        InlineKeyboardButton("🎵 صوت", callback_data=f"audio")
    )

    bot.send_message(message.chat.id, "🎵 اختر نوع التحميل:", reply_markup=markup)

# دالة لاستقبال الأوامر من الأزرار
@bot.callback_query_handler(func=lambda call: call.data in ["video", "audio"])
def callback_handler(call):
    chat_id = call.message.chat.id
    url = user_links.get(chat_id)

    if not url:
        bot.send_message(chat_id, "❌ حدث خطأ! يرجى إرسال الرابط مجددًا.")
        return

    if call.data == "video":
        markup = InlineKeyboardMarkup()
        quality_options = {
            "144p": 144, "240p": 240, "360p": 360,
            "480p": 480, "720p": 720, "1080p": 1080
        }
        
        for label, res in quality_options.items():
            markup.add(InlineKeyboardButton(f"📺 {label}", callback_data=f"quality_{res}"))

        bot.send_message(chat_id, "🔽 اختر دقة الفيديو:", reply_markup=markup)

    elif call.data == "audio":
        bot.send_message(chat_id, "🎧 جارٍ تحميل الصوت بأعلى جودة... ⏳")
        audio_path, video_id, audio_ext = download_media(url, "audio")
        
        if audio_path:
            bot.send_audio(chat_id, open(audio_path, 'rb'))
            time.sleep(3)
            os.remove(audio_path)
        else:
            bot.send_message(chat_id, "❌ حدث خطأ أثناء تحميل الصوت.")

# دالة لمعالجة اختيار الدقة للفيديو
@bot.callback_query_handler(func=lambda call: call.data.startswith("quality_"))
def handle_video_quality(call):
    chat_id = call.message.chat.id
    url = user_links.get(chat_id)

    if not url:
        bot.send_message(chat_id, "❌ حدث خطأ! يرجى إرسال الرابط مجددًا.")
        return

    resolution = int(call.data.split("_")[1])

    bot.send_message(chat_id, f"⏳ جارٍ تحميل الفيديو بدقة {resolution}p...")

    # تنزيل الفيديو والصوت
    video_path, video_id, video_ext = download_media(url, "video", resolution)
    audio_path, _, audio_ext = download_media(url, "audio")

    if not video_path or not audio_path:
        bot.send_message(chat_id, "❌ حدث خطأ أثناء تحميل الفيديو أو الصوت.")
        return

    # مسار الفيديو النهائي
    final_video_path = f"downloads/{video_id}_final.{video_ext}"

    # دمج الفيديو والصوت
    bot.send_message(chat_id, "🔄 جارٍ دمج الصوت مع الفيديو...")
    success = merge_video_audio(video_path, audio_path, final_video_path)

    if success:
        bot.send_video(chat_id, open(final_video_path, 'rb'), timeout=60)
        time.sleep(3)
        os.remove(video_path)
        os.remove(audio_path)
        os.remove(final_video_path)
    else:
        bot.send_message(chat_id, "❌ فشل في دمج الصوت مع الفيديو.")

# تشغيل البوت بشكل مستمر
def run_bot():
    bot.polling(none_stop=True)

# تشغيل Flask في خيط منفصل
if __name__ == "__main__":
    keep_alive()  # حافظ على تشغيل Flask
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
