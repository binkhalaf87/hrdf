"""نظام مطابقة رواتب هدف مع البنوك السعودية"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
# Path is used below for hadaf file extension detection

import streamlit as st
from matcher.matching_engine import MatchingEngine
from parser.bank_parser import BankParser
from parser.hadaf_parser import HadafParser
from parser.hadaf_excel_parser import HadafExcelParser
from parser.bank_raw_extractor import BankRawExtractor
from reports.excel_writer import ExcelWriter
from reports.pdf_writer import PDFWriter
from reports.bank_style_pdf import BankStylePDFWriter
from reports.pdf_overlay import PDFOverlayWriter
from utils.logger import get_logger

logger = get_logger(__name__)

st.set_page_config(
    page_title="نظام مطابقة رواتب هدف",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
/* إخفاء الشريط الجانبي بالكامل */
[data-testid="stSidebar"] { display: none !important; }
[data-testid="collapsedControl"] { display: none !important; }

body, .stApp { direction: rtl; font-family: 'Segoe UI', Tahoma, sans-serif; }

/* هيدر رئيسي */
.hero-header {
    background: linear-gradient(135deg, #1a3c6e 0%, #2563a8 60%, #1e88e5 100%);
    border-radius: 16px;
    padding: 36px 40px 28px 40px;
    margin-bottom: 28px;
    text-align: center;
    color: white;
    box-shadow: 0 4px 24px rgba(30,136,229,0.18);
}
.hero-header h1 { font-size: 2rem; font-weight: 700; margin: 0 0 6px 0; letter-spacing: -0.5px; }
.hero-header p  { font-size: 1rem; opacity: 0.85; margin: 0; }

/* بطاقات الرفع */
.upload-card {
    background: #f8fafd;
    border: 2px dashed #b0c4de;
    border-radius: 14px;
    padding: 24px 20px;
    text-align: center;
    transition: border-color .2s;
}
.upload-card:hover { border-color: #2563a8; }
.upload-card-title { font-size: 1.05rem; font-weight: 600; color: #1a3c6e; margin-bottom: 4px; }
.upload-card-sub   { font-size: 0.82rem; color: #6b7280; margin-bottom: 14px; }

/* شرائح معلومات المراحل */
.info-strip {
    display: flex; flex-wrap: wrap; gap: 10px; justify-content: center;
    margin: 18px 0 0 0;
}
.info-chip {
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.8rem;
    color: white;
}

.status-box { border-radius:8px; padding:12px 16px; margin:6px 0; font-size:15px; }
.green  { background:#c6efce; border-left:4px solid #1a7a1a; }
.yellow { background:#ffeb9c; border-left:4px solid #b86e00; }
.red    { background:#ffc7ce; border-left:4px solid #c0392b; }
.orange { background:#fce4d6; border-left:4px solid #c55a11; }
</style>
""", unsafe_allow_html=True)

show_debug = False  # إخفاء التشخيص بشكل افتراضي

# ── Hero Header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-header">
  <h1>🏦 نظام مطابقة رواتب هدف مع البنوك</h1>
  <p>ارفع ملف هدف وملف البنك للحصول على تقرير المطابقة فوراً</p>
  <div class="info-strip">
    <span class="info-chip">1️⃣ آيبان</span>
    <span class="info-chip">2️⃣ رقم الهوية</span>
    <span class="info-chip">3️⃣ الرقم التسلسلي</span>
    <span class="info-chip">4️⃣ الاسم العربي</span>
    <span class="info-chip">5️⃣ مطابقة ذكية</span>
    <span class="info-chip">6️⃣ ترجمة عربي↔إنجليزي</span>
    <span class="info-chip">7️⃣ Claude AI</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── رفع الملفات ───────────────────────────────────────────────────────────────
col_h, col_b = st.columns(2, gap="large")
with col_h:
    st.markdown('<div class="upload-card-title">📁 ملف هدف</div><div class="upload-card-sub">PDF أو Excel ببيانات برنامج هدف</div>', unsafe_allow_html=True)
    hadaf_file = st.file_uploader(
        "ملف هدف",
        type=["pdf", "xlsx", "xls"],
        key="hadaf_up",
        label_visibility="collapsed",
    )
    if hadaf_file:
        ext = Path(hadaf_file.name).suffix.lower()
        st.success(f"{'📄 Excel' if ext in ('.xlsx', '.xls') else '📑 PDF'} — {hadaf_file.name}")
with col_b:
    st.markdown('<div class="upload-card-title">🏦 ملف البنك</div><div class="upload-card-sub">PDF كشف رواتب البنك</div>', unsafe_allow_html=True)
    bank_file = st.file_uploader(
        "ملف البنك",
        type=["pdf"],
        key="bank_up",
        label_visibility="collapsed",
    )
    if bank_file:
        st.success(f"📑 PDF — {bank_file.name}")

st.markdown("<br>", unsafe_allow_html=True)

_KEY_FILE = Path(__file__).parent / ".claude_api_key"

def _load_saved_key() -> str:
    try:
        return _KEY_FILE.read_text().strip()
    except Exception:
        return ""

def _save_key(key: str) -> None:
    try:
        _KEY_FILE.write_text(key.strip())
    except Exception:
        pass

if "claude_api_key" not in st.session_state:
    st.session_state["claude_api_key"] = _load_saved_key()

with st.expander("🤖 إعدادات المطابقة الذكية بالذكاء الاصطناعي (اختياري)", expanded=False):
    st.caption("أدخل مفتاح Claude API لتفعيل مرحلة المطابقة الذكية للأسماء غير المتطابقة")
    col_key, col_btn = st.columns([4, 1])
    with col_key:
        claude_api_key = st.text_input(
            "مفتاح Claude API",
            type="password",
            placeholder="sk-ant-...",
            value=st.session_state["claude_api_key"],
            key="claude_api_key_input",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("💾 حفظ", use_container_width=True):
            _save_key(claude_api_key)
            st.session_state["claude_api_key"] = claude_api_key
            st.success("✅ تم الحفظ")
    if claude_api_key:
        st.success("✅ سيتم تفعيل مطابقة الأسماء بالذكاء الاصطناعي (المرحلة 7)")
    else:
        st.info("ℹ️ بدون مفتاح API ستعمل مراحل المطابقة 1-6 فقط")

process_btn = st.button(
    "⚙️ بدء المطابقة",
    type="primary",
    use_container_width=True,
    disabled=(hadaf_file is None or bank_file is None),
)

# ── Processing ────────────────────────────────────────────────────────────────
if process_btn and hadaf_file and bank_file:
    hadaf_bytes = hadaf_file.read()
    bank_bytes  = bank_file.read()

    hadaf_ext   = Path(hadaf_file.name).suffix.lower()
    is_excel    = hadaf_ext in (".xlsx", ".xls")

    bank_parser = BankParser()

    # Debug info (only relevant for PDF inputs)
    if show_debug:
        if not is_excel:
            hadaf_parser_dbg = HadafParser()
            with st.expander("🔍 تشخيص ملف هدف", expanded=True):
                dbg = hadaf_parser_dbg.debug_extract(hadaf_bytes)
                st.write(f"**عدد الصفحات:** {dbg.get('page_count', '?')}")
                st.write(f"**جداول مكتشفة:** {len(dbg.get('tables', []))}")
                for t in dbg.get("tables", []):
                    st.write(f"  صفحة {t['page']} — {t['rows']} صف × {t['cols']} عمود")
                    st.write(f"  العناوين: {t['header']}")
                    st.write(f"  عينة: {t['sample']}")
                if dbg.get("text_sample"):
                    st.code(dbg["text_sample"], language=None)
        else:
            st.info("🔍 ملف هدف بصيغة Excel — لا يحتاج تشخيص PDF")

        with st.expander("🔍 تشخيص ملف البنك", expanded=True):
            dbg = bank_parser.debug_extract(bank_bytes)
            st.write(f"**عدد الصفحات:** {dbg.get('page_count', '?')}")
            st.write(f"**جداول مكتشفة:** {len(dbg.get('tables', []))}")
            for t in dbg.get("tables", []):
                st.write(f"  صفحة {t['page']} — {t['rows']} صف × {t['cols']} عمود")
                st.write(f"  العناوين: {t['header']}")
                st.write(f"  عينة: {t['sample']}")
            if dbg.get("text_sample"):
                st.code(dbg["text_sample"], language=None)

    # ── Parse Hadaf ───────────────────────────────────────────────────────────
    with st.spinner("جاري استخراج بيانات ملف هدف..."):
        try:
            if is_excel:
                hadaf_employees = HadafExcelParser().parse(hadaf_bytes)
            else:
                hadaf_employees = HadafParser().parse(hadaf_bytes)
        except Exception as exc:
            st.error(f"فشل استخراج بيانات هدف: {exc}")
            st.stop()

    if not hadaf_employees:
        st.error("⛔ لم يتم العثور على موظفين في ملف هدف. فعّل التشخيص لمزيد من التفاصيل.")
        st.stop()

    st.success(f"✅ تم استخراج **{len(hadaf_employees)}** موظف من ملف هدف")

    # ── Parse Bank PDF (raw extractor for Excel-mode, standard parser otherwise) ──
    with st.spinner("جاري استخراج بيانات ملف البنك..."):
        try:
            if is_excel:
                # Excel mode: use raw extractor that preserves ALL bank columns
                bank_raw = BankRawExtractor().extract(bank_bytes)
            else:
                bank_raw = None
            bank_employees = bank_parser.parse(bank_bytes)
        except Exception as exc:
            st.error(f"فشل استخراج بيانات البنك: {exc}")
            st.stop()

    if not bank_employees:
        st.error("⛔ لم يتم استخراج سجلات من ملف البنك. فعّل التشخيص لمزيد من التفاصيل.")
        st.stop()

    st.success(f"✅ تم استخراج **{len(bank_employees)}** سجل من ملف البنك")

    # ── Match ─────────────────────────────────────────────────────────────────
    _claude_key = (st.session_state.get("claude_api_key_input") or st.session_state.get("claude_api_key", "")).strip() or None
    with st.spinner("جاري المطابقة..."):
        result = MatchingEngine(claude_api_key=_claude_key).match(hadaf_employees, bank_employees)

    # Build IBAN lookup for the bank-style PDF (Excel mode only)
    hadaf_by_iban_for_pdf = (
        {e.iban.upper(): e.serial for e in hadaf_employees if e.iban}
        if is_excel else None
    )

    st.session_state.update({
        "result": result,
        "hadaf_employees": hadaf_employees,
        "bank_employees": bank_employees,
        "bank_raw": bank_raw,
        "bank_bytes": bank_bytes,
        "hadaf_by_iban_for_pdf": hadaf_by_iban_for_pdf,
        "is_excel_mode": is_excel,
    })

# ── Results ───────────────────────────────────────────────────────────────────
if "result" in st.session_state:
    result           = st.session_state["result"]
    hadaf_employees  = st.session_state["hadaf_employees"]
    bank_employees   = st.session_state["bank_employees"]
    s                = result.summary

    st.markdown("## 📈 نتائج المطابقة")

    # ---- KPI cards ----
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    hadaf_matched_count = s.total_hadaf - s.hadaf_not_in_bank
    c1.metric("موظفو هدف 📋",              s.total_hadaf)
    c2.metric("سجلات البنك 🏦",             s.total_bank)
    c3.metric("نزل راتبهم ✅",              hadaf_matched_count)
    c4.metric("لم ينزل راتبهم ❌",          s.hadaf_not_in_bank)
    c5.metric("بالبنك فقط (ليسوا في هدف)", s.unmatched)
    c6.metric("نسبة تغطية هدف 🎯",         f"{s.success_rate:.1f}%")

    # ---- Hadaf-not-in-bank alert ----
    if s.hadaf_not_in_bank > 0:
        st.markdown(
            f'<div class="status-box orange">⚠️ <b>{s.hadaf_not_in_bank} موظف في هدف</b> '
            f'لم ينزل راتبهم في البنك هذا الشهر.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    import pandas as pd

    # ---- الجدول الرئيسي: كشف البنك مع رقم هدف أولاً ----
    st.markdown("### 📄 كشف الرواتب المُحدَّث")
    st.caption("رقم هدف أول عمود — أخضر: مطابق تام | أصفر: يحتاج مراجعة | أحمر: غير مطابق")

    def _row_color(status):
        return {"matched": "🟢", "review": "🟡", "bank_only": "🔴"}.get(status, "⚪")

    df_main = pd.DataFrame([{
        "رقم هدف": (
            str(r.hadaf_serial) if r.status == "matched"
            else (f"{r.hadaf_serial}؟" if r.status == "review" else "—")
        ),
        "اسم الموظف": r.bank_name,
        "الآيبان": r.iban or "",
        "المبلغ": r.bank_amount,
        "رقم المرجع": r.reference or "",
        "الحالة": _row_color(r.status),
    } for r in result.bank_report])
    st.dataframe(df_main, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ---- تفاصيل إضافية في tabs ----
    tab_review, tab_unmatched, tab_hadaf_only = st.tabs([
        "⚠️ يحتاج مراجعة بشرية",
        "❌ غير مطابق من البنك",
        "📋 موظفو هدف لم ينزل راتبهم",
    ])

    with tab_review:
        if result.review:
            df = pd.DataFrame([{
                "اسم البنك":            r.bank_name,
                "الاسم المقترح (هدف)": r.hadaf_name,
                "رقم هدف المقترح":     r.hadaf_serial,
                "المبلغ (البنك)":      r.bank_amount,
                "طريقة المطابقة":      r.match_method,
                "الثقة %":             f"{r.confidence:.1f}%",
            } for r in result.review])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.success("لا توجد سجلات تحتاج مراجعة ✅")

    with tab_unmatched:
        if result.unmatched_bank:
            df = pd.DataFrame([{
                "اسم البنك":   e.name,
                "الآيبان":    e.iban or "",
                "المبلغ":     e.amount,
                "رقم المرجع": e.reference or "",
            } for e in result.unmatched_bank])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.success("جميع سجلات البنك تم مطابقتها ✅")

    with tab_hadaf_only:
        if result.unmatched_hadaf:
            df = pd.DataFrame([{
                "رقم هدف":     e.serial,
                "اسم الموظف":  e.name_arabic,
                "رقم الهوية":  e.national_id or "",
                "الآيبان":     e.iban or "",
            } for e in result.unmatched_hadaf])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.success("جميع موظفي هدف موجودون في ملف البنك ✅")

    # ── Downloads ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📥 تحميل التقارير")

    writer     = ExcelWriter()
    pdf_writer = PDFWriter()

    is_excel_mode        = st.session_state.get("is_excel_mode", False)
    bank_raw             = st.session_state.get("bank_raw")
    bank_bytes           = st.session_state.get("bank_bytes", b"")
    hadaf_by_iban_for_pdf = st.session_state.get("hadaf_by_iban_for_pdf")

    # ── الزران الرئيسيان جنباً لجنب ────────────────────────────────────
    st.markdown("### ⬇️ تحميل الكشف المُحدَّث")

    # مجموعة الأرقام التسلسلية المطابَقة — كل من وُجد في البنك بأي طريقة
    matched_serials_set = {
        mr.hadaf_serial
        for mr in result.matched + result.review
    }

    with st.spinner("جاري تعديل ملف البنك الأصلي بإضافة رقم هدف..."):
        if is_excel_mode and hadaf_by_iban_for_pdf:
            pdf_bytes, _ = PDFOverlayWriter().overlay(
                bank_bytes, hadaf_by_iban_for_pdf
            )
            pdf_label = "🖨️ تحميل ملف البنك الأصلي المعدَّل (رقم هدف مُضاف)"
            pdf_help  = "نفس ملف البنك الأصلي بالضبط — رقم هدف مُضاف في الهامش الأيمن بجانب كل موظف"
        else:
            pdf_bytes = pdf_writer.build_bank_report_pdf(
                result.bank_report,
                title="كشف الرواتب المُحدَّث — برنامج هدف",
            )
            pdf_label = "🖨️ تحميل كشف البنك PDF (رقم هدف كأول عمود)"
            pdf_help  = "نفس بيانات البنك — رقم هدف التسلسلي العمود الأول، ثم اسم الموظف، الآيبان، المبلغ"

    # بناء dict: hadaf_serial → رقم م في البنك (للتحقق العكسي)
    # — مطابَق بالإيبان: يُكتب رقم م
    # — مطابَق بالاسم/الهوية: يُكتب اسم الموظف في ملف البنك
    bank_serial_by_hadaf: dict[int, str] = {}
    if is_excel_mode and bank_raw and hadaf_by_iban_for_pdf:
        for rec in bank_raw:
            if rec.iban and rec.bank_serial:
                iban_up = rec.iban.upper()
                if iban_up in hadaf_by_iban_for_pdf:
                    bank_serial_by_hadaf[hadaf_by_iban_for_pdf[iban_up]] = rec.bank_serial
    else:
        bank_serial_by_iban = {
            e.iban.upper(): str(e.serial)
            for e in bank_employees
            if e.iban and e.serial is not None
        }
        for mr in result.matched + result.review:
            if mr.iban and mr.iban.upper() in bank_serial_by_iban:
                bank_serial_by_hadaf[mr.hadaf_serial] = bank_serial_by_iban[mr.iban.upper()]

    # للموظفين المطابَقين بالاسم/الهوية (لا إيبان) — أضف اسم البنك بدلاً من رقم م
    for mr in result.matched + result.review:
        if mr.hadaf_serial not in bank_serial_by_hadaf and mr.bank_name:
            bank_serial_by_hadaf[mr.hadaf_serial] = mr.bank_name

    # dict: hadaf_serial → طريقة المطابقة
    match_method_by_hadaf: dict[int, str] = {
        mr.hadaf_serial: mr.match_method
        for mr in result.matched + result.review
    }

    hadaf_employees_list = st.session_state.get("hadaf_employees", [])
    with st.spinner("جاري بناء قائمة موظفي هدف..."):
        excel_status_bytes = writer.build_hadaf_status_excel(
            hadaf_employees_list, matched_serials_set, bank_serial_by_hadaf,
            match_method_by_hadaf,
        )

    col_pdf, col_hadaf_xl = st.columns(2)
    with col_pdf:
        st.download_button(
            label=pdf_label,
            data=pdf_bytes,
            file_name="كشف_البنك_مع_رقم_هدف.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
            help=pdf_help,
        )
    with col_hadaf_xl:
        st.download_button(
            label=f"📋 تحميل موظفو هدف مع حالة البنك ({len(hadaf_employees_list)} موظف)",
            data=excel_status_bytes,
            file_name="موظفو_هدف_حالة_البنك.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
            help="قائمة كاملة لجميع موظفي هدف مع عمود يوضح هل نزل راتب كل موظف في البنك أم لا",
        )

    # ── Excel المطابقة بالآيبان (الزر الرئيسي الثاني) ───────────────────
    if is_excel_mode and bank_raw and hadaf_by_iban_for_pdf:
        st.markdown("---")
        st.markdown("### 📥 Excel المطابقة بالآيبان")

        hadaf_employees_list = st.session_state["hadaf_employees"]
        hadaf_name_by_iban   = {e.iban.upper(): e.name_arabic
                                 for e in hadaf_employees_list if e.iban}
        hadaf_amount_by_iban = {e.iban.upper(): e.support_amount
                                 for e in hadaf_employees_list
                                 if e.iban and e.support_amount is not None}

        with st.spinner("جاري توليد Excel..."):
            excel_iban = writer.build_iban_matched_excel(
                bank_raw,
                hadaf_by_iban_for_pdf,
                hadaf_name_by_iban,
                hadaf_amount_by_iban,
            )

        matched_count = sum(
            1 for r in bank_raw
            if r.iban and r.iban.upper() in hadaf_by_iban_for_pdf
        )
        st.download_button(
            label=f"📊 تحميل Excel المطابقة بالآيبان  ({matched_count} موظف مطابَق)",
            data=excel_iban,
            file_name="مطابقة_هدف_بالآيبان.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary",
        )

    # ── تقارير ثانوية ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**تقارير إضافية:**")
    d1, d2, d3, d4 = st.columns(4)
    with d1:
        st.download_button(
            "📊 Excel كامل",
            data=writer.build_bank_report_excel(result.bank_report),
            file_name="كشف_الرواتب_مع_رقم_هدف.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "📙 يحتاج مراجعة",
            data=writer.build_review_excel(result.review),
            file_name="review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with d3:
        st.download_button(
            "📕 غير مطابق",
            data=writer.build_unmatched_excel(result.unmatched_bank),
            file_name="unmatched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with d4:
        st.download_button(
            "📘 الملخص",
            data=writer.build_summary_excel(s, result.matched, result.review),
            file_name="summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

elif hadaf_file is None or bank_file is None:
    st.info("👆 ارفع كلا الملفين للبدء")
