import streamlit as st
import time
import random
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# --- OLDAL BEÁLLÍTÁSOK ---
st.set_page_config(page_title="Érettségi QuizUp ⚡", page_icon="🧬", layout="centered")

# --- JSON SÉMA A HIBAMENTES AI VÁLASZHOZ ---
class QuizQuestion(BaseModel):
    question: str = Field(description="A magyar nyelvű érettségi szintű kérdés.")
    options: list[str] = Field(description="Pontosan 4 darab válaszlehetőség.")
    correct_answer: str = Field(description="A helyes válasz, amelynek pontosan egyeznie kell az options egyik elemével.")
    explanation: str = Field(description="Rövid, 1-2 mondatos közérthető magyarázat, miért ez a helyes válasz az érettségi követelmények alapján.")

class QuizSet(BaseModel):
    questions: list[QuizQuestion]

TOPICS = {
    "🩻 Anatómia és Élettan": [
        "Vegyes anatómiai feladatsor",
        "Mozgásrendszer (csontok, ízületek, vázizmok)",
        "Keringési rendszer (szív, erek, vér és nyirok)",
        "Légzőrendszer és gázcsere",
        "Emésztőrendszer és anyagcsere",
        "Kiválasztó- és szaporítórendszer",
        "Idegrendszer és érzékszervek",
        "Hormonrendszer (endokrin szervek)"
    ],
    "🧬 Biológia": [
        "Vegyes érettségi feladatsor",
        "Sejtbiológia és biokémia",
        "Genetika és öröklődéstan",
        "Ökológia és evolúció",
        "Növény- és állatrendszertan"
    ],
    "🧪 Kémia": [
        "Vegyes érettségi feladatsor",
        "Atomszerkezet és periódusos rendszer",
        "Kémiai kötések és halmazállapotok",
        "Szervetlen kémia és reakciótípusok",
        "Szerves kémia (szénhidrogének, oxigén- és nitrogéntartalmú vegyületek)",
        "Kémiai egyensúlyok és sav-bázis folyamatok"
    ],
    "⚛️ Fizika": [
        "Vegyes érettségi feladatsor",
        "Mechanika (kinematika, dinamika, munka és energia)",
        "Hőtan és termodinamika",
        "Elektromosságtan és mágnesesség",
        "Optika és hullámtan",
        "Modern fizika (atom- és magfizika)"
    ]
}

# --- SESSION STATE INICIALIZÁLÁSA ---
if "questions" not in st.session_state:
    st.session_state.questions = []
if "q_index" not in st.session_state:
    st.session_state.q_index = 0
if "score" not in st.session_state:
    st.session_state.score = 0
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "answered" not in st.session_state:
    st.session_state.answered = False
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "asked_history" not in st.session_state:
    st.session_state.asked_history = []

# --- OLDALSÁV (AI & JÁTÉK BEÁLLÍTÁSOK) ---
with st.sidebar:
    st.header("🔑 AI Beállítások")
    
    # API kulcs betöltése Streamlit Secrets-ből vagy kézi megadással
    api_key = st.secrets.get("GEMINI_API_KEY", "")
    if api_key:
        st.success("✅ API Key betöltve (Secrets)")
    else:
        api_key = st.text_input("Google Gemini API kulcs", type="password")

    model_choice = st.selectbox(
        "🤖 Gemini Modell:",
        ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-2.5-flash"],
        index=0
    )

    st.divider()
    st.header("🎓 Érettségi Témakör")
    
    subject = st.selectbox("Tantárgy:", list(TOPICS.keys()))
    subtopic = st.selectbox("Témakör:", TOPICS[subject])
    custom_topic = st.text_input("Vagy írj be saját tételt/altémát:", placeholder="pl. Fotoszintézis, Redoxireakciók...")
    
    level = st.radio("Érettségi szint:", ["Középszint", "Emelt szint"], horizontal=True)
    num_questions = st.slider("Kérdések száma egy körben:", 5, 15, 10)

    start_btn = st.button("🚀 Új QuizUp kör indítása", type="primary", use_container_width=True)

# --- KÉRDÉSEK GENERÁLÁSA (CSAK GOMBNYOMÁSRA!) ---
def generate_quiz(api_key, model_name, subject, topic, level, count, history):
    client = genai.Client(api_key=api_key)
    
    history_text = ""
    if history:
        recent = history[-20:]
        history_text = f"\nEzeket a kérdéseket már feltetted korábban, kérlek NE ismételd meg őket:\n- " + "\n- ".join(recent)

    prompt = f"""
    Készíts egy {count} kérdésből álló, pörgős, QuizUp-stílusú magyar nyelvű feleletválasztós kvízt a magyar gimnáziumi érettségi követelmények alapján!
    
    Tantárgy: {subject}
    Témakör: {topic}
    Szint: {level}
    
    Szabályok:
    1. A kérdések legyenek szakmailag 100%-ig pontosak, de tömörek és jól olvashatók gyors játékhoz.
    2. Minden kérdéshez pontosan 4 válaszlehetőség tartozzon (1 helyes, 3 hihető, de hibás elterelő válasz).
    3. A 'correct_answer' mező karakterre pontosan egyezzen meg a 4 válaszlehetőség egyikével.
    4. Az 'explanation' mezőben adj egy rövid, 1-2 mondatos, tanulást segítő magyarázatot.
    {history_text}
    """

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QuizSet,
            temperature=0.7
        ),
    )
    
    quiz_data = QuizSet.model_validate_json(response.text)
    formatted_questions = []
    for q in quiz_data.questions:
        opts = list(q.options)
        random.shuffle(opts)
        formatted_questions.append({
            "question": q.question,
            "options": opts,
            "answer": q.correct_answer,
            "explanation": q.explanation
        })
        st.session_state.asked_history.append(q.question)
        
    return formatted_questions

if start_btn:
    if not api_key:
        st.error("⚠️ Kérlek add meg a Gemini API kulcsot a bal oldali sávban (vagy a Streamlit Secrets-ben)!")
    else:
        chosen_topic = custom_topic.strip() if custom_topic.strip() else subtopic
        with st.spinner(f"⚡ {num_questions} db {level.lower()}ű {subject} kérdés generálása..."):
            try:
                st.session_state.questions = generate_quiz(
                    api_key, model_choice, subject, chosen_topic, level, num_questions, st.session_state.asked_history
                )
                st.session_state.q_index = 0
                st.session_state.score = 0
                st.session_state.answered = False
                st.session_state.last_result = None
                st.session_state.start_time = time.time()
                st.rerun()
            except Exception as e:
                st.error(f"Hiba történt a generálás során: {e}")

# --- FŐKÉPERNYŐ ---
st.title("⚡ Érettségi QuizUp")
st.caption("Gimnáziumi Biológia, Kémia és Fizika villámkvíz gyorsasági bónusszal")

if not st.session_state.questions:
    st.info("👈 Válassz tantárgyat, témakört és szintet a bal oldali menüben, majd kattints az **Új QuizUp kör indítása** gombra!")
else:
    total_q = len(st.session_state.questions)
    idx = st.session_state.q_index

    # Fejléc: Haladás és Pontszám
    col1, col2 = st.columns([3, 1])
    with col1:
        st.progress(idx / total_q)
    with col2:
        st.metric("🏆 Pontszám", f"{st.session_state.score} pt")

    # JÁTÉK KÖZBEN
    if idx < total_q:
        q_data = st.session_state.questions[idx]
        st.subheader(f"{idx + 1}. / {total_q} kérdés")
        st.markdown(f"### {q_data['question']}")

        # Válaszgombok megjelenítése
        if not st.session_state.answered:
            for i, option in enumerate(q_data["options"]):
                if st.button(option, key=f"opt_{idx}_{i}", use_container_width=True):
                    elapsed = time.time() - st.session_state.start_time
                    is_correct = (option == q_data["answer"])
                    
                    if is_correct:
                        # Alap 100 pont + max 100 gyorsasági bónusz (15 mp alatt)
                        speed_bonus = max(0, int((15 - elapsed) * (100 / 15)))
                        gained = 100 + speed_bonus
                        st.session_state.score += gained
                        st.session_state.last_result = ("success", f"✅ Helyes válasz! (+100 alap + {speed_bonus} gyorsasági bónusz = **{gained} pont** | Idő: {elapsed:.1f} mp)")
                    else:
                        st.session_state.last_result = ("error", f"❌ Sajnos nem talált! A helyes válasz: **{q_data['answer']}**")
                    
                    st.session_state.answered = True
                    st.rerun()
        
        # Visszajelzés és magyarázat válaszadás után
        else:
            status, msg = st.session_state.last_result
            if status == "success":
                st.success(msg)
            else:
                st.error(msg)
            
            st.info(f"💡 **Érettségi magyarázat:** {q_data['explanation']}")
            
            if st.button("Következő kérdés ➡️", type="primary", use_container_width=True):
                st.session_state.q_index += 1
                st.session_state.answered = False
                st.session_state.last_result = None
                st.session_state.start_time = time.time()
                st.rerun()

    # JÁTÉK VÉGE
    else:
        st.balloons()
        st.success(f"🎉 **Gratulálok! Végigértél a feladatsoron!**")
        max_possible = total_q * 200
        st.metric("Végső pontszámod", f"{st.session_state.score} / {max_possible} pont")
        
        if st.button("🔄 Új kör indítása ugyanebben a témában", type="primary"):
            st.session_state.questions = []
            st.rerun()
