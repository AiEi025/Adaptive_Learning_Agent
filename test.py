import streamlit as st

st.set_page_config(
    page_title="آزمون ۴ سواله",
    page_icon="📝",
    layout="centered"
)

# راست‌چین کردن رابط کاربری
st.markdown("""
<style>
    .stApp {
        direction: rtl;
        text-align: right;
    }
    div[data-testid="stRadio"] label {
        direction: rtl;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

st.title("📝 آزمون ۴ سواله")
st.write("به آزمون خوش آمدید. به هر ۴ سوال پاسخ دهید و سپس دکمه ثبت را بزنید.")

# -----------------------------
# سوالات آزمون
# -----------------------------
questions = [
    {
        "question": "پایتخت ایران کدام شهر است؟",
        "options": ["تهران", "اصفهان", "مشهد", "شیراز"],
        "answer": 0
    },
    {
        "question": "کدام سیاره به «سیاره سرخ» معروف است؟",
        "options": ["زهره", "مریخ", "مشتری", "زحل"],
        "answer": 1
    },
    {
        "question": "آب از چه عناصری تشکیل شده است؟",
        "options": ["اکسیژن و کربن", "هیدروژن و اکسیژن", "نیتروژن و هیدروژن", "کربن و نیتروژن"],
        "answer": 1
    },
    {
        "question": "کدام گزینه یک زبان برنامه‌نویسی است؟",
        "options": ["HTML", "Python", "HTTP", "CSS"],
        "answer": 1
    }
]

# -----------------------------
# مقداردهی اولیه session_state
# -----------------------------
if "submitted" not in st.session_state:
    st.session_state.submitted = False

if "score" not in st.session_state:
    st.session_state.score = 0

if "answers" not in st.session_state:
    st.session_state.answers = []

# -----------------------------
# نمایش فرم آزمون
# -----------------------------
if not st.session_state.submitted:
    with st.form("quiz_form"):
        answers = []

        for i, q in enumerate(questions):
            st.markdown(f"### سوال {i + 1}")
            st.write(q["question"])

            selected = st.radio(
                "گزینه صحیح را انتخاب کنید:",
                q["options"],
                index=None,
                key=f"q{i}",
                label_visibility="collapsed"
            )
            answers.append(selected)
            st.divider()

        submitted = st.form_submit_button("ثبت پاسخ‌ها")

    if submitted:
        if any(answer is None for answer in answers):
            st.warning("⚠️ لطفاً به همه سوالات پاسخ دهید.")
        else:
            score = 0
            for i, answer in enumerate(answers):
                correct_answer = questions[i]["options"][questions[i]["answer"]]
                if answer == correct_answer:
                    score += 1

            st.session_state.score = score
            st.session_state.answers = answers
            st.session_state.submitted = True
            st.rerun()

# -----------------------------
# نمایش نتیجه
# -----------------------------
else:
    st.success(f"🎯 نمره شما: {st.session_state.score} از {len(questions)}")

    for i, q in enumerate(questions):
        user_answer = st.session_state.answers[i]
        correct_answer = q["options"][q["answer"]]

        if user_answer == correct_answer:
            st.markdown(f"✅ **سوال {i + 1}:** درست — پاسخ صحیح: **{correct_answer}**")
        else:
            st.markdown(
                f"❌ **سوال {i + 1}:** پاسخ شما: **{user_answer}** — "
                f"پاسخ صحیح: **{correct_answer}**"
            )

    st.divider()

    if st.button("🔄 شروع دوباره"):
        for key in ["submitted", "score", "answers"]:
            st.session_state.pop(key, None)

        for i in range(len(questions)):
            st.session_state.pop(f"q{i}", None)

        st.rerun()