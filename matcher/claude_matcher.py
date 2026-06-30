from __future__ import annotations

import json
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__)


def _build_prompt(pairs: list[tuple[str, str]]) -> str:
    lines = []
    for i, (arabic, bank) in enumerate(pairs):
        lines.append(f'{i + 1}. الاسم في هدف: "{arabic}" | الاسم في البنك: "{bank}"')

    items = "\n".join(lines)
    return f"""أنت نظام مطابقة أسماء موظفين. مهمتك مقارنة أسماء من ملف هدف (عربية) مع أسماء من ملف البنك (قد تكون عربية أو إنجليزية).

قواعد المطابقة:
- تجاهل الاختلافات في الترتيب (محمد أحمد = أحمد محمد)
- تجاهل الأخطاء الإملائية الطفيفة
- تجاهل الفرق بين التذكير والتأنيث في البادئات (عبد/عبدال)
- إذا كان الاسم مترجماً من عربي لإنجليزي، تحقق من تشابه النطق
- أعطِ نسبة ثقة من 0 إلى 100

أسماء للمقارنة:
{items}

أجب بـ JSON فقط بالتنسيق التالي (مصفوفة بنفس ترتيب الأسماء):
[
  {{"index": 1, "score": 95, "reasoning": "نفس الاسم مع اختلاف بسيط في الترتيب"}},
  ...
]"""


class ClaudeNameMatcher:
    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def match_pairs(
        self,
        pairs: list[tuple[str, str]],
        batch_size: int = 20,
    ) -> list[float]:
        """
        Given a list of (hadaf_arabic_name, bank_name) pairs,
        returns a list of confidence scores (0–100) in the same order.
        """
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
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data = json.loads(raw)
            result = [0.0] * len(pairs)
            for item in data:
                idx = item["index"] - 1
                if 0 <= idx < len(pairs):
                    result[idx] = float(item.get("score", 0))
            return result
        except Exception as exc:
            logger.warning("Claude name matching failed: %s", exc)
            return [0.0] * len(pairs)
