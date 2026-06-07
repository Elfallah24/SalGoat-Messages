import base64
import os
import random
import aiohttp
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

INTRO_STYLES = [
    "🔥 بيت ديال نهار 🔥",
    "⚽ تحليل اليوم ⚽",
    "💥 خيار مضمون 💥",
    "🎯 بيت ديال ليلة 🎯",
    "🚀 فرصة اليوم 🚀",
]

CALL_TO_ACTION = [
    "📲 سجل دابا وكول بيتك!",
    "🏆 انضم وكسب معانا!",
    "💸 ماتفوتش الفرصة!",
    "✅ جرب حظك دابا!",
]

PROMPT_TEMPLATE = """أنت خبير في تحليل أوراق المراهنات الرياضية.

مهمتك: حلل هذه الصورة ديال ورقة البيت واكتب caption بالدارجة المغربية جاهز للنشر في قناة تيليغرام.

استخرج من الصورة:
- أسماء الفرق
- البطولة / الدوري
- نوع الرهان (Double Chance / BTTS / 1X / X2 / إلخ)
- الكوتا (المعامل)
- إذا كان فيه أكثر من مباراة، ذكرهم كلهم

اكتب الـ Caption بهاد الشكل:

{intro}

⚽ [فريق1] 🆚 [فريق2]
🏆 [البطولة]
🎯 النوع: [نوع الرهان بالدارجة]
💰 الكوتا: [الكوتا]

قواعد: الدارجة فقط، بدون markdown، بدون شرح إضافي"""


async def analyze_bet_image(image_bytes: bytes, promo_code: str, reg_link: str) -> str:
    intro  = random.choice(INTRO_STYLES)
    cta    = random.choice(CALL_TO_ACTION)
    prompt = PROMPT_TEMPLATE.format(intro=intro)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "model": "openrouter/auto",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
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
            bet_section = data["choices"][0]["message"]["content"].strip()

    footer = (
        f"\n━━━━━━━━━━━━━━━\n"
        f"{cta}\n"
        f'🔗 <a href="{reg_link}">سجل من هنا</a>\n'
        f"🎁 كود البرومو: <code>{promo_code}</code>"
    )
    return bet_section + footer