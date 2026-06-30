from __future__ import annotations

import json

from utils.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """أنت نظام تدقيق آيبانات بنكية صارم. مهمتك مقارنة آيبان من ملف هدف مع آيبان من ملف البنك للتأكد أنهما لنفس الحساب رغم أخطاء القراءة الضوئية (OCR).

الآيبان السعودي يتكون من: SA + رقمان للتحقق + 22 خانة (إجمالي 24 حرف/رقم).

قواعد التدقيق الصارمة:

✅ يُعدّ تطابقاً (match=true) فقط إذا:
- الآيبانان متطابقان حرفاً بحرف، أو
- الاختلاف الوحيد ناتج عن خطأ OCR شائع ومؤكد:
  • 0 ↔ O      • 1 ↔ I/l     • 5 ↔ S      • 8 ↔ B      • 6 ↔ G
  • 2 ↔ Z      • فراغات/مسافات زائدة

❌ لا يُعدّ تطابقاً (match=false) إذا:
- اختلاف في رقمين أو أكثر
- اختلاف في خانة لا يفسرها خطأ OCR معروف
- اختلاف في طول الآيبان (بعد إزالة الفراغات)
- أي شك — الأصل عدم المطابقة

مبادئ:
1. كن صارماً جداً — مطابقة آيبان خاطئة تعني تحويل مالي لشخص خاطئ
2. لا تطابق بناءً على التشابه العام، بل على خطأ OCR محدد ومبرر
3. أعطِ نفس النتيجة دائماً لنفس المدخلات (حتمي)"""


def _build_prompt(pairs: list[tuple[str, str]]) -> str:
    lines = []
    for i, (hadaf_iban, bank_iban) in enumerate(pairs):
        lines.append(f'{i + 1}. هدف: "{hadaf_iban}" ←→ بنك: "{bank_iban}"')

    items = "\n".join(lines)
    return f"""دقّق كل زوج من الآيبانات وحدّد هل هما لنفس الحساب:

{items}

أجب بـ JSON فقط — لا نص خارج JSON:
[
  {{"index": 1, "match": true, "reason": "تطابق تام"}},
  {{"index": 2, "match": false, "reason": "اختلاف في 3 خانات"}}
]

تأكد من وجود مدخل لكل رقم من 1 إلى {len(pairs)}."""


class ClaudeIbanMatcher:
    """يتحقق من تطابق الآيبانات بشكل صارم مع مراعاة أخطاء OCR."""

    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

    def verify_pairs(self, pairs: list[tuple[str, str]], batch_size: int = 20) -> list[bool]:
        """
        لكل (hadaf_iban, bank_iban) يرجع True إذا كانا لنفس الحساب.
        """
        results: list[bool] = [False] * len(pairs)
        for start in range(0, len(pairs), batch_size):
            batch = pairs[start: start + batch_size]
            batch_res = self._call_claude(batch)
            for i, ok in enumerate(batch_res):
                results[start + i] = ok
        return results

    def _call_claude(self, pairs: list[tuple[str, str]]) -> list[bool]:
        prompt = _build_prompt(pairs)
        try:
            message = self._client.messages.create(
                model="claude-opus-4-8",
                max_tokens=2048,
                temperature=0,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            if "```" in raw:
                for part in raw.split("```"):
                    part = part.strip()
                    if part.startswith("json"):
                        part = part[4:].strip()
                    if part.startswith("["):
                        raw = part
                        break
            data = json.loads(raw)
            result = [False] * len(pairs)
            for item in data:
                idx = item["index"] - 1
                if 0 <= idx < len(pairs):
                    result[idx] = bool(item.get("match", False))
            return result
        except Exception as exc:
            logger.warning("Claude IBAN verification failed: %s", exc)
            return [False] * len(pairs)
