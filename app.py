"""
نظام مطابقة رواتب هدف مع البنوك السعودية
Hadaf-Bank Salary Matching System
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from matcher.matching_engine import MatchingEngine
from models import ProcessingSummary
from parser.bank_parser import BankParser
from parser.hadaf_parser import HadafParser
from reports.excel_writer import ExcelWriter
from utils.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="نظام مطابقة رواتب هدف",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS — RTL support and custom styling
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    body, .stApp { direction: rtl; }
    .metric-card {
        background: #f0f2f6;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
        border: 1px solid #ddd;
    }
    .metric-card .value { font-size: 2rem; font-weight: bold; }
    .metric-card .label { font-size: 0.9rem; color: #666; }
    .matched   { color: #1a7a1a; }
    .review    { color: #b86e00; }
    .unmatched { color: #c0392b; }
    .success   { color: #2471a3; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("📊 نظام المطابقة")
    st.markdown("---")
    st.markdown(
        """
        **الإصدار:** 1.0.0
        **مراحل المطابقة:**
        1. رقم الهوية الوطنية
        2. رقم الآيبان / الرقم التسلسلي
        3. الاسم العربي الكامل
        4. مطابقة ذكية (RapidFuzz)
        5. ترجمة عربي ↔ إنجليزي

        **حدود الثقة:**
        - ✅ ≥ 95%: مطابق
        - ⚠️ 80–95%: يحتاج مراجعة
        - ❌ < 80%: غير مطابق
        """
    )
    st.markdown("---")
    st.caption("تطوير: نظام معالجة رواتب هدف")


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------
st.title("🏦 نظام مطابقة رواتب هدف مع البنوك السعودية")
st.markdown("قم برفع ملف هدف وملف البنك لبدء عملية المطابقة الآلية.")

col_hadaf, col_bank = st.columns(2)

with col_hadaf:
    st.subheader("📁 ملف هدف (Hadaf PDF)")
    hadaf_file = st.file_uploader(
        "ارفع ملف هدف",
        type=["pdf"],
        key="hadaf_upload",
        help="ملف PDF يحتوي على بيانات موظفي برنامج هدف",
    )

with col_bank:
    st.subheader("🏦 ملف البنك (Bank PDF)")
    bank_file = st.file_uploader(
        "ارفع ملف البنك",
        type=["pdf"],
        key="bank_upload",
        help="ملف PDF كشف رواتب البنك",
    )

st.markdown("---")

process_btn = st.button(
    "⚙️ معالجة الملفات / Process Files",
    type="primary",
    use_container_width=True,
    disabled=(hadaf_file is None or bank_file is None),
)

if process_btn and hadaf_file and bank_file:
    hadaf_bytes = hadaf_file.read()
    bank_bytes = bank_file.read()

    with st.spinner("جاري استخراج بيانات ملف هدف..."):
        try:
            hadaf_parser = HadafParser()
            hadaf_employees = hadaf_parser.parse(hadaf_bytes)
            st.success(f"✅ تم استخراج {len(hadaf_employees)} موظف من ملف هدف")
        except Exception as exc:
            st.error(f"فشل في استخراج بيانات هدف: {exc}")
            st.stop()

    with st.spinner("جاري استخراج بيانات ملف البنك..."):
        try:
            bank_parser = BankParser()
            bank_employees = bank_parser.parse(bank_bytes)
            st.success(f"✅ تم استخراج {len(bank_employees)} سجل من ملف البنك")
        except Exception as exc:
            st.error(f"فشل في استخراج بيانات البنك: {exc}")
            st.stop()

    if not hadaf_employees:
        st.error("لم يتم العثور على موظفين في ملف هدف. تحقق من تنسيق الملف.")
        st.stop()

    if not bank_employees:
        st.error("لم يتم العثور على سجلات في ملف البنك. تحقق من تنسيق الملف.")
        st.stop()

    with st.spinner("جاري تنفيذ المطابقة..."):
        engine = MatchingEngine()
        result = engine.match(hadaf_employees, bank_employees)

    st.session_state["engine_result"] = result
    st.session_state["hadaf_employees"] = hadaf_employees
    st.session_state["bank_employees"] = bank_employees


# ---------------------------------------------------------------------------
# Results display
# ---------------------------------------------------------------------------
if "engine_result" in st.session_state:
    result = st.session_state["engine_result"]
    hadaf_employees = st.session_state["hadaf_employees"]
    bank_employees = st.session_state["bank_employees"]
    summary: ProcessingSummary = result.summary

    st.markdown("## 📈 نتائج المطابقة")

    # Metrics row
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("إجمالي موظفي البنك", summary.total_bank)
    with c2:
        st.metric("المطابقات ✅", summary.matched)
    with c3:
        st.metric("تحتاج مراجعة ⚠️", summary.review_required)
    with c4:
        st.metric("غير مطابق ❌", summary.unmatched)
    with c5:
        st.metric("نسبة النجاح 🎯", f"{summary.success_rate:.1f}%")

    st.markdown("---")

    # Result tabs
    tab_matched, tab_review, tab_unmatched = st.tabs(
        ["✅ المطابقات", "⚠️ تحتاج مراجعة", "❌ غير مطابق"]
    )

    with tab_matched:
        if result.matched:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        "الرقم التسلسلي": r.hadaf_serial,
                        "اسم هدف": r.hadaf_name,
                        "اسم البنك": r.bank_name,
                        "الآيبان": r.iban or "",
                        "المبلغ": f"{r.amount:,.2f}",
                        "طريقة المطابقة": r.match_method,
                        "الثقة %": f"{r.confidence:.1f}%",
                    }
                    for r in result.matched
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("لا توجد مطابقات ناجحة")

    with tab_review:
        if result.review:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        "اسم البنك": r.bank_name,
                        "الاسم المقترح (هدف)": r.hadaf_name,
                        "الرقم التسلسلي المقترح": r.hadaf_serial,
                        "الآيبان": r.iban or "",
                        "المبلغ": f"{r.amount:,.2f}",
                        "طريقة المطابقة": r.match_method,
                        "الثقة %": f"{r.confidence:.1f}%",
                    }
                    for r in result.review
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("لا توجد سجلات تحتاج مراجعة")

    with tab_unmatched:
        if result.unmatched_bank:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        "اسم البنك": e.name,
                        "الآيبان": e.iban or "",
                        "المبلغ": f"{e.amount:,.2f}",
                        "رقم المرجع": e.reference or "",
                    }
                    for e in result.unmatched_bank
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.success("جميع سجلات البنك تم مطابقتها!")

    # ---------------------------------------------------------------------------
    # Download section
    # ---------------------------------------------------------------------------
    st.markdown("---")
    st.markdown("## 📥 تحميل التقارير")

    excel_writer = ExcelWriter()

    dl_col1, dl_col2, dl_col3, dl_col4 = st.columns(4)

    with dl_col1:
        matched_bytes = excel_writer.build_matched_excel(result.matched)
        st.download_button(
            label="📗 تحميل المطابقات",
            data=matched_bytes,
            file_name="matched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with dl_col2:
        review_bytes = excel_writer.build_review_excel(result.review)
        st.download_button(
            label="📙 تحميل المراجعة",
            data=review_bytes,
            file_name="review.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with dl_col3:
        unmatched_bytes = excel_writer.build_unmatched_excel(result.unmatched_bank)
        st.download_button(
            label="📕 تحميل غير المطابق",
            data=unmatched_bytes,
            file_name="unmatched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    with dl_col4:
        summary_bytes = excel_writer.build_summary_excel(
            summary=result.summary,
            hadaf_employees=hadaf_employees,
            bank_employees=bank_employees,
            matched=result.matched,
            review=result.review,
            unmatched_bank=result.unmatched_bank,
        )
        st.download_button(
            label="📘 تحميل الملخص",
            data=summary_bytes,
            file_name="summary.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

elif hadaf_file is None or bank_file is None:
    st.info("👆 يرجى رفع كلا الملفين للبدء في عملية المطابقة")
