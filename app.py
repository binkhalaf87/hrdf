"""نظام مطابقة رواتب هدف مع البنوك السعودية"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from matcher.matching_engine import MatchingEngine
from parser.bank_parser import BankParser
from parser.hadaf_parser import HadafParser
from reports.excel_writer import ExcelWriter
from utils.logger import get_logger

logger = get_logger(__name__)

st.set_page_config(
    page_title="نظام مطابقة رواتب هدف",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
body, .stApp { direction: rtl; }
.status-box { border-radius:8px; padding:12px 16px; margin:6px 0; font-size:15px; }
.green  { background:#c6efce; border-left:4px solid #1a7a1a; }
.yellow { background:#ffeb9c; border-left:4px solid #b86e00; }
.red    { background:#ffc7ce; border-left:4px solid #c0392b; }
.orange { background:#fce4d6; border-left:4px solid #c55a11; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 نظام المطابقة")
    st.markdown("---")
    st.markdown("""
**الإصدار:** 1.1.0

**مراحل المطابقة:**
1. رقم الآيبان (هدف ↔ بنك)
2. رقم الهوية الوطنية
3. الرقم التسلسلي
4. الاسم العربي الكامل
5. مطابقة ذكية (RapidFuzz)
6. ترجمة عربي ↔ إنجليزي

**حدود الثقة:**
- ✅ ≥ 95%: مطابق
- ⚠️ 80–95%: يحتاج مراجعة
- ❌ < 80%: غير مطابق
""")
    st.markdown("---")
    show_debug = st.checkbox("🔍 عرض تشخيص PDF", value=False)

# ── Main ──────────────────────────────────────────────────────────────────────
st.title("🏦 نظام مطابقة رواتب هدف مع البنوك السعودية")

col_h, col_b = st.columns(2)
with col_h:
    st.subheader("📁 ملف هدف (Hadaf PDF)")
    hadaf_file = st.file_uploader("ارفع ملف هدف", type=["pdf"], key="hadaf_up",
                                   help="ملف PDF ببيانات موظفي برنامج هدف")
with col_b:
    st.subheader("🏦 ملف البنك (Bank PDF)")
    bank_file  = st.file_uploader("ارفع ملف البنك", type=["pdf"], key="bank_up",
                                   help="ملف PDF كشف رواتب البنك")

st.markdown("---")
process_btn = st.button(
    "⚙️ معالجة الملفات / Process Files",
    type="primary",
    use_container_width=True,
    disabled=(hadaf_file is None or bank_file is None),
)

# ── Processing ────────────────────────────────────────────────────────────────
if process_btn and hadaf_file and bank_file:
    hadaf_bytes = hadaf_file.read()
    bank_bytes  = bank_file.read()

    hadaf_parser = HadafParser()
    bank_parser  = BankParser()

    # Debug info
    if show_debug:
        with st.expander("🔍 تشخيص ملف هدف", expanded=True):
            dbg = hadaf_parser.debug_extract(hadaf_bytes)
            st.write(f"**عدد الصفحات:** {dbg.get('page_count', '?')}")
            st.write(f"**جداول مكتشفة:** {len(dbg.get('tables', []))}")
            for t in dbg.get("tables", []):
                st.write(f"  صفحة {t['page']} — {t['rows']} صف × {t['cols']} عمود")
                st.write(f"  العناوين: {t['header']}")
                st.write(f"  عينة: {t['sample']}")
            if dbg.get("text_sample"):
                st.code(dbg["text_sample"], language=None)

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

    # Parse
    with st.spinner("جاري استخراج بيانات ملف هدف..."):
        try:
            hadaf_employees = hadaf_parser.parse(hadaf_bytes)
        except Exception as exc:
            st.error(f"فشل استخراج بيانات هدف: {exc}")
            st.stop()

    if not hadaf_employees:
        st.error("""
⛔ **لم يتم العثور على موظفين في ملف هدف.**

**أسباب محتملة:**
- الملف محمي بكلمة مرور
- تنسيق مختلف (جداول مدمجة أو نص غير منظم)
- ملف ممسوح ضوئياً (يحتاج Tesseract OCR)

**الحل:** فعّل خيار "عرض تشخيص PDF" من الشريط الجانبي لرؤية ما تم استخراجه.
        """)
        st.stop()

    st.success(f"✅ تم استخراج **{len(hadaf_employees)}** موظف من ملف هدف")

    with st.spinner("جاري استخراج بيانات ملف البنك..."):
        try:
            bank_employees = bank_parser.parse(bank_bytes)
        except Exception as exc:
            st.error(f"فشل استخراج بيانات البنك: {exc}")
            st.stop()

    if not bank_employees:
        st.error("⛔ لم يتم استخراج سجلات من ملف البنك. فعّل التشخيص لمزيد من التفاصيل.")
        st.stop()

    st.success(f"✅ تم استخراج **{len(bank_employees)}** سجل من ملف البنك")

    with st.spinner("جاري المطابقة..."):
        result = MatchingEngine().match(hadaf_employees, bank_employees)

    st.session_state.update({
        "result": result,
        "hadaf_employees": hadaf_employees,
        "bank_employees": bank_employees,
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
    c1.metric("موظفو هدف 📋",        s.total_hadaf)
    c2.metric("سجلات البنك 🏦",       s.total_bank)
    c3.metric("مطابق ✅",             s.matched)
    c4.metric("يحتاج مراجعة ⚠️",     s.review_required)
    c5.metric("غير مطابق ❌",        s.unmatched)
    c6.metric("نسبة النجاح 🎯",      f"{s.success_rate:.1f}%")

    # ---- Hadaf-not-in-bank alert ----
    if s.hadaf_not_in_bank > 0:
        st.markdown(
            f'<div class="status-box orange">⚠️ <b>{s.hadaf_not_in_bank} موظف في هدف</b> '
            f'لم ينزل راتبهم في البنك هذا الشهر.</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ---- Tabs ----
    tab_bank, tab_matched, tab_review, tab_unmatched, tab_hadaf_only = st.tabs([
        "📄 تقرير البنك الكامل",
        "✅ المطابقات",
        "⚠️ تحتاج مراجعة",
        "❌ غير مطابق",
        "📋 هدف غير موجود بالبنك",
    ])

    import pandas as pd

    with tab_bank:
        st.caption("جميع سجلات البنك مع الرقم التسلسلي لهدف لكل موظف مطابق")
        df = pd.DataFrame([{
            "اسم الموظف (البنك)":      r.bank_name,
            "الرقم التسلسلي (هدف)":    r.hadaf_serial or "",
            "اسم الموظف (هدف)":        r.hadaf_name or "",
            "الآيبان":                  r.iban or "",
            "المبلغ المحوَّل (البنك)":  r.bank_amount,
            "مبلغ هدف":                r.hadaf_support_amount or "",
            "الفرق":                    r.amount_diff if r.amount_diff is not None else "",
            "الحالة":                   ExcelWriter._status_label(r.status),
            "الثقة %":                  f"{r.confidence:.0f}%" if r.confidence else "",
        } for r in result.bank_report])
        st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_matched:
        if result.matched:
            df = pd.DataFrame([{
                "الرقم التسلسلي": r.hadaf_serial,
                "اسم هدف":        r.hadaf_name,
                "اسم البنك":      r.bank_name,
                "المبلغ (البنك)": r.bank_amount,
                "مبلغ هدف":      r.hadaf_support_amount or "",
                "الفرق":          r.amount_diff if r.amount_diff is not None else "",
                "طريقة المطابقة": r.match_method,
                "الثقة %":        f"{r.confidence:.1f}%",
            } for r in result.matched])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("لا توجد مطابقات ناجحة")

    with tab_review:
        if result.review:
            df = pd.DataFrame([{
                "اسم البنك":             r.bank_name,
                "الاسم المقترح (هدف)":  r.hadaf_name,
                "الرقم التسلسلي":       r.hadaf_serial,
                "المبلغ (البنك)":       r.bank_amount,
                "مبلغ هدف":             r.hadaf_support_amount or "",
                "طريقة المطابقة":       r.match_method,
                "الثقة %":              f"{r.confidence:.1f}%",
            } for r in result.review])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.success("لا توجد سجلات تحتاج مراجعة")

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
            st.success("جميع سجلات البنك تم مطابقتها!")

    with tab_hadaf_only:
        if result.unmatched_hadaf:
            df = pd.DataFrame([{
                "الرقم التسلسلي": e.serial,
                "اسم الموظف":     e.name_arabic,
                "رقم الهوية":     e.national_id or "",
                "الآيبان":        e.iban or "",
                "مبلغ هدف":      e.support_amount or "",
            } for e in result.unmatched_hadaf])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.success("جميع موظفي هدف موجودون في ملف البنك")

    # ── Downloads ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("## 📥 تحميل التقارير")

    writer = ExcelWriter()
    d1, d2, d3, d4, d5 = st.columns(5)

    with d1:
        st.download_button(
            "📊 تقرير البنك المُحدَّث",
            data=writer.build_bank_report_excel(result.bank_report),
            file_name="bank_report_updated.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            help="جميع سجلات البنك مع الرقم التسلسلي لهدف",
        )
    with d2:
        st.download_button(
            "📗 المطابقات",
            data=writer.build_matched_excel(result.matched),
            file_name="matched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with d3:
        st.download_button(
            "📙 المراجعة",
            data=writer.build_review_excel(result.review),
            file_name="review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with d4:
        st.download_button(
            "📕 غير مطابق",
            data=writer.build_unmatched_excel(result.unmatched_bank),
            file_name="unmatched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with d5:
        st.download_button(
            "📘 الملخص",
            data=writer.build_summary_excel(s, result.matched, result.review),
            file_name="summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

elif hadaf_file is None or bank_file is None:
    st.info("👆 ارفع كلا الملفين للبدء")
