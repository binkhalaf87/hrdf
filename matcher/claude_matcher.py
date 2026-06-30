from __future__ import annotations

import json
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """أنت نظام مطابقة أسماء موظفين دقيق ومتخصص في الأسماء العربية والمحولة للإنجليزية.

قواعد صارمة للتقييم:

✅ يُعدّ تطابقاً (نسبة 85-100) إذا:
- الأسماء متطابقة تماماً بعد تطبيع الهمزات والتاء المربوطة
- نفس الأسماء بترتيب مختلف (محمد أحمد علي = علي أحمد محمد)
- الاسم العربي محوّل للإنجليزية بنطق مطابق (عبدالله = Abdullah, محمد = Mohammed/Muhammad)
- اختلاف في كلمة "ال" التعريف فقط (الأحمد = أحمد)

⚠️ يُعدّ مشابهاً يحتاج مراجعة (نسبة 60-84) إذا:
- 3 من 4 أسماء متطابقة والرابع مختلف
- خطأ إملائي واضح في كلمة واحدة فقط
- النطق الإنجليزي قريب لكن ليس دقيقاً

❌ لا يُعدّ تطابقاً (نسبة 0-59) إذا:
- اختلاف في أكثر من اسم واحد دون مبرر
- أسماء مختلفة كلياً حتى لو بعض الأحرف متشابهة
- شخصان مختلفان واضحان

مبادئ التقييم:
1. كن متحفظاً — المطابقة الخاطئة أسوأ من عدم المطابقة
2. ركز على جوهر الاسم الثلاثي أو الرباعي وليس الكلمات الفردية
3. الأسماء العربية المحولة للإنجليزية: قارن بالنطق لا بالكتابة
4. ابحث في كل الكلمات — لا تكتفِ بالكلمة الأولى
5. أعطِ نفس النتيجة دائماً لنفس الأسماء (ثابت وحتمي)"""


def _build_prompt(pairs: list[tuple[str, str]]) -> str:
    lines = []
    for i, (arabic, bank) in enumerate(pairs):
        lines.append(f'{i + 1}. هدف: "{arabic}" ←→ بنك: "{bank}"')

    items = "\n".join(lines)
    return f"""قارن كل زوج من الأسماء وأعطِ نسبة تطابق دقيقة:

{items}

أجب بـ JSON فقط — لا تضف أي نص خارج JSON:
[
  {{"index": 1, "score": 95, "reason": "سبب موجز"}},
  ...
]

تأكد من وجود مدخل لكل رقم من 1 إلى {len(pairs)}."""


class ClaudeNameMatcher:
    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def match_pairs(
        self,
        pairs: list[tuple[str, str]],
        batch_size: int = 15,
    ) -> list[float]:
        scores: list[float] = [0.0] * len(pairs)

        for start in range(0, len(pairs), batch_size):
            batch = pairs[start: start + batch_size]
            batch_scores = self._call_claude(batch)
            for i, score in enumerate(batch_scores):
                scores[start + i] = score

        return scores

    def _call_claude(self, pairs: list[tuple[str, str]]) -> list[float]:
        prompt = _build_prompt(pairs)
        try:
            message = self._client.messages.create(
                model="claude-opus-4-8",
                max_tokens=2048,
                temperature=0,          # حتمي — نفس النتيجة في كل مرة
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()

            # Strip markdown code fences if present
            if "```" in raw:
                parts = raw.split("```")
                for part in parts:
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("["):
                        raw = part
                        break

            data = json.loads(raw)
            result = [0.0] * len(pairs)
            for item in data:
                idx = item["index"] - 1
                if 0 <= idx < len(pairs):
                    result[idx] = float(item.get("score", 0))

            logger.debug("Claude matched %d pairs", len(pairs))
            return result

        except Exception as exc:
            logger.warning("Claude name matching failed: %s", exc)
            return [0.0] * len(pairs)
