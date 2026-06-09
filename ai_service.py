"""
ai_service.py
-------------
كل شي متعلق بالـ AI — تحليل الورقة + رسالة الفوز
"""

import base64
import os
import random
import aiohttp
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ===================================================
# ستايلات متنوعة للـ description (تتغير كل بوست)
# ===================================================
INTROS = [
    "❤️‍🔥 Cote اليوم خدامة بثقة حسب التحليل والمعطيات اللي عندي 🧠",
    "🔥 ورقة مخدومة على البارد، ماشي عشوائية والله!",
    "💥 التحليل والأرقام كيقولو هاد البيت رابح إن شاء الله",
    "🚀 هاد الفرصة ماتفوتش، les données كتهضر علينا",
    "🎯 analyse complète دارتلنا الكوتا اليوم واضحة",
    "💡 confiance كبيرة فهاد البيت، le travail تم sur le froid",
]

OUTROS = [
    "ماشي عشوائية، راه ورقة مخدومة على البارد 💵 اللي متبع عارف بلي النتائج كتهضر علينا!",
    "les données ماكذبوش، هاد البيت solide بزاف 💪",
    "تحليل بالمنطق والأرقام، مشي بالحظ العمى 🧠",
    "والله اللي متبع عارف بلي كنخدمو على البارد دايما 🔥",
    "le boulot داروه les experts، باقي غير تتبعنا 💸",
]

WIN_INTROS = [
    "نيك ماه ربحناها 🔥🔥🔥",
    "قلنالكم والله! la cote خدمات 🎉",
    "هاك النتيجة، le gain في جيبنا 💰",
    "تحليلنا ما كذبش كما العادة 🏆",
    "والله ما خيبنا الضن، ربحنا مرة أخرى 🔥",
    "على البارد كيما قلنا، la victoire حاضرة 🎊",
]

# ===================================================
# البرومبت ديال تحليل الورقة (قبل الماتش)
# ===================================================
BET_PROMPT = """أنت محلل مراهنات رياضي خبير.

حلل هذه الصورة ديال ورقة البيت واكتب وصف بالدارجة الجزائرية.
الدارجة الجزائرية = مزيج طبيعي من العربية والفرنسية (مثل: "le match", "la cote", "confiance").

ابدأ بـ: {intro}

ثم اكتب:
⚽ [فريق1] 🆚 [فريق2]
🏆 [البطولة]
🎯 النوع: [نوع الرهان]
💰 la cote: [الكوتا]

ثم اختم بـ: {outro}

قواعد صارمة:
- الدارجة الجزائرية فقط (مزيج عربي-فرنسي)
- لا تكتب أي شرح قبل أو بعد النص
- لا markdown، فقط نص عادي وإيموجيات
- إذا ما قدرتيش تقرأ شي اكتب ❓"""

# ===================================================
# البرومبت ديال رسالة الفوز (بعد الماتش)
# ===================================================
WIN_PROMPT = """أنت محلل مراهنات رياضي.

هذه الصورة تبين ورقة بيت رابحة (GAGNE ✅).

اكتب رسالة فرحة قصيرة بالدارجة الجزائرية (مزيج عربي-فرنسي).

ابدأ بـ: {win_intro}

ثم اكتب جملتين فيهم:
- فرحة بالفوز
- تذكير للمتابعين باش يسجلوا ويكسبوا معانا

قواعد:
- الدارجة الجزائرية (مزيج عربي-فرنسي)
- قصير: 4-5 أسطر فقط
- لا markdown، نص عادي وإيموجيات
- لا تكتب أي شرح قبل أو بعد"""


# ===================================================
# دالة مساعدة — الاتصال بـ OpenRouter
# ===================================================
async def _call_ai(prompt: str, image_bytes: bytes) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "model": "openrouter/auto",
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": prompt}
            ]
        }]
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/betbot",
        "X-Title": "Bet Channel Bot"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                raise Exception(f"OpenRouter error: {data}")
            return data["choices"][0]["message"]["content"].strip()


# ===================================================
# الدوال الرئيسية
# ===================================================
async def analyze_bet_image(image_bytes: bytes) -> str:
    """تحليل صورة الورقة وإرجاع description فقط (بدون كود أو روابط)"""
    prompt = BET_PROMPT.format(
        intro=random.choice(INTROS),
        outro=random.choice(OUTROS)
    )
    return await _call_ai(prompt, image_bytes)


async def generate_win_description(image_bytes: bytes) -> str:
    """توليد رسالة الفوز"""
    prompt = WIN_PROMPT.format(win_intro=random.choice(WIN_INTROS))
    return await _call_ai(prompt, image_bytes)


# ===================================================
# بناء الكابشن الكامل
# ===================================================
def build_post_caption(ai_description: str, bet_code: str, promo_code: str,
                        reg_link: str, android_link: str,
                        iphone_link: str, video_link: str) -> str:
    """بناء الكابشن الكامل لبوست جديد"""

    # روابط — تتضاف فقط إذا كانت محددة
    links = [f'🔗 <a href="{reg_link}">رابط خاص بالمغاربة</a>']

    if android_link:
        links.append(f'🔗 <a href="{android_link}">رابط التطبيق للأندرويد من هنا</a>')

    if iphone_link:
        links.append(f'📱🔗 <a href="{iphone_link}">رابط التطبيق للآيفون من هنا</a>')

    if video_link:
        links.append(f'📱 <a href="{video_link}">فيديو لطريقة التسجيل معانا فموقع LINEBET</a>')

    return (
        f"CODE : {bet_code}\n\n"
        f"{ai_description}\n\n"
        f"إلا كنت باغي تستافد بحالك بحال الناس اللي كتربح معانا، "
        f"✅ سجّل معانا ودير كود البرومو <code>{promo_code}</code> "
        f"باش تاخذ البونيس ديالك ⭐️⭐️ "
        f"الفرص كاينة، وخاصك غير تدير الخطوة الأولى 👇\n\n"
        f"#ورقة_اليوم #تحليل_بالمنطق #ربح_معقول\n"
        + "\n".join(links)
    )


def build_win_caption(win_description: str, reg_link: str) -> str:
    """بناء كابشن الفوز"""
    return (
        f"{win_description}\n\n"
        f'🔗 <a href="{reg_link}">رابط خاص بالمغاربة</a>'
    )
