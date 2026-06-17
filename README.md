# نظام مطابقة رواتب هدف مع البنوك السعودية

نظام ذكي لمطابقة ملفات رواتب برنامج هدف مع كشوف رواتب البنوك السعودية تلقائياً.

---

## المتطلبات

- Python 3.12+
- Tesseract OCR (للملفات الممسوحة ضوئياً)
- Java (مطلوب لـ tabula-py)

---

## التثبيت خطوة بخطوة

### 1. تثبيت Tesseract OCR

**Windows:**
- حمّل المثبت من: https://github.com/UB-Mannheim/tesseract/wiki
- قم بتثبيته وتأكد من إضافة المسار إلى متغير البيئة PATH
- حمّل ملف اللغة العربية: `ara.traineddata` وضعه في مجلد `tessdata`

**Linux/Mac:**
```bash
# Ubuntu/Debian
sudo apt-get install tesseract-ocr tesseract-ocr-ara

# macOS
brew install tesseract tesseract-lang
```

### 2. استنساخ المشروع وتثبيت المتطلبات

```bash
git clone <repository-url>
cd hrdf

# إنشاء بيئة افتراضية (موصى به)
python -m venv venv

# تفعيل البيئة
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# تثبيت المتطلبات
pip install -r requirements.txt
```

### 3. إنشاء ملفات تجريبية (اختياري)

```bash
python tests/sample_data/create_samples.py
```

ستجد الملفات في: `tests/sample_data/`

### 4. تشغيل الاختبارات

```bash
python -m pytest tests/ -v
```

أو مع تقرير التغطية:
```bash
python -m pytest tests/ -v --cov=. --cov-report=html
```

### 5. تشغيل التطبيق

```bash
streamlit run app.py
```

ثم افتح المتصفح على: http://localhost:8501

---

## كيفية الاستخدام

1. **ارفع ملف هدف** (Hadaf PDF) من الجانب الأيسر
2. **ارفع ملف البنك** (Bank PDF) من الجانب الأيمن
3. اضغط زر **"معالجة الملفات"**
4. انتظر اكتمال المعالجة وظهور النتائج
5. حمّل التقارير المطلوبة (matched / review / unmatched / summary)

---

## مراحل المطابقة

| المرحلة | الطريقة | مستوى الثقة |
|---------|---------|------------|
| 1 | رقم الهوية الوطنية | 100% |
| 2 | الرقم التسلسلي | 100% |
| 3 | الاسم العربي الكامل (بعد التطبيع) | 100% |
| 4 | RapidFuzz Fuzzy Matching | متغير |
| 5 | ترجمة عربي ↔ إنجليزي | متغير |

### حدود الثقة:
- **≥ 95%** → مطابق ✅
- **80–94%** → يحتاج مراجعة ⚠️
- **< 80%** → غير مطابق ❌

---

## هيكل المشروع

```
hrdf/
├── app.py                  # واجهة Streamlit الرئيسية
├── models.py               # نماذج البيانات
├── parser/
│   ├── pdf_utils.py        # أدوات معالجة PDF
│   ├── hadaf_parser.py     # محلل ملف هدف
│   └── bank_parser.py      # محلل ملف البنك
├── matcher/
│   ├── arabic_utils.py     # تطبيع النصوص العربية
│   ├── transliteration.py  # ترجمة عربي-إنجليزي
│   ├── name_matcher.py     # استراتيجيات المطابقة
│   └── matching_engine.py  # المحرك الرئيسي
├── reports/
│   └── excel_writer.py     # توليد ملفات Excel
├── utils/
│   ├── config.py           # الإعدادات
│   └── logger.py           # السجلات
├── tests/
│   ├── test_matcher.py     # اختبارات المطابقة
│   ├── test_parser.py      # اختبارات المحلل
│   └── sample_data/        # ملفات تجريبية
├── requirements.txt
└── README.md
```

---

## المخرجات

| الملف | المحتوى |
|-------|---------|
| `matched.xlsx` | السجلات المطابقة مع الرقم التسلسلي ونسبة الثقة |
| `review.xlsx` | السجلات التي تحتاج مراجعة بشرية |
| `unmatched.xlsx` | السجلات غير المطابقة |
| `summary.xlsx` | ملخص إحصائي شامل |

---

## استكشاف الأخطاء

### مشكلة: "tesseract is not installed"
تأكد من تثبيت Tesseract وإضافته إلى PATH:
```bash
tesseract --version
```

### مشكلة: "No tables found in PDF"
- تأكد من أن ملف PDF يحتوي على جدول منظم
- جرب تحويله إلى PDF نصي إذا كان ممسوحاً ضوئياً بجودة منخفضة

### مشكلة: "Java not found" (tabula-py)
- قم بتثبيت Java JDK من: https://adoptium.net/
- أو استخدم pdfplumber فقط (يعمل بدون Java)

---

## التطوير والمساهمة

```bash
# تشغيل الاختبارات مع تفاصيل
python -m pytest tests/ -v -s

# التحقق من جودة الكود
python -m flake8 . --max-line-length=100
python -m mypy . --ignore-missing-imports
```
