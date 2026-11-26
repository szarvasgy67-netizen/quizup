import streamlit as st
import time
import random
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from idezetek import VERSEK, PROZAK

# --- OLDAL BEÁLLÍTÁSOK ---
st.set_page_config(page_title="Érettségi & IQ QuizUp ⚡", page_icon="🎓", layout="centered")

# --- JSON SÉMA A HIBAMENTES AI VÁLASZHOZ ---
class QuizQuestion(BaseModel):
    question: str = Field(description="A magyar nyelvű kérdés.")
    options: list[str] = Field(description="Pontosan 4 darab válaszlehetőség.")
    correct_answer: str = Field(description="A helyes válasz, amelynek pontosan egyeznie kell az options egyik elemével.")
    explanation: str = Field(description="Rövid, 1-2 mondatos közérthető magyarázat.")

class QuizSet(BaseModel):
    questions: list[QuizQuestion]

# --- TANTÁRGYAK ÉS TÉMAKÖRÖK ---
TOPICS = {
    "🧠 Dinamikus IQ & Logika": [
        "Vegyes IQ és logikai feladatsor",
        "Számsorozatok és matematikai minták",
        "Verbális analógiák és fogalmi logika",
        "Deduktív logikai rejtvények (állító-tagadó feladatok)",
        "Kakukktojás és fogalmi rendszerezés"
    ],
    "🏛️ Magyar történelem": [
        "Vegyes magyar történelem érettségi",
        "Honfoglalás és az Árpád-kor (1301-ig)",
        "Vegyes-házi királyok és a Hunyadiak kora (1301–1526)",
        "Három részre szakadt ország és a Rákóczi-szabadságharc",
        "Reformkor és az 1848–49-es forradalom és szabadságharc",
        "A dualizmus kora (1867–1918)",
        "A Horthy-korszak és a II. világháború",
        "A Rákosi- és a Kádár-korszak, rendszerváltás (1945–1990)"
    ],
    "📚 Magyar irodalom": [
        "Vegyes magyar irodalom érettségi",
        "Ókor, középkor és reneszánsz (Balassi Bálint, Zrínyi Miklós)",
        "Felvilágosodás és reformkor (Csokonai, Berzsenyi, Katona József)",
        "A romantika nagyjai (Vörösmarty, Petőfi, Arany János)",
        "A Nyugat első nemzedéke (Ady, Babits, Kosztolányi, Móricz)",
        "A két világháború közötti irodalom (József Attila, Radnóti, Márai)",
        "Kortárs és 1945 utáni magyar irodalom (Pilinszky, Örkény, Kertész)",
        "Műfajelmélet, stíluskorszakok és verstani alapok"
    ],
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
if "correct_count" not in st.session_state:
    st.session_state.correct_count = 0
if "start_time" not in st.session_state:
    st.session_state.start_time = None
if "answered" not in st.session_state:
    st.session_state.answered = False
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "asked_history" not in st.session_state:
    st.session_state.asked_history = []
if "active_subject" not in st.session_state:
    st.session_state.active_subject = ""
if "active_level" not in st.session_state:
    st.session_state.active_level = "Középszint"

# --- HELYI ADATBÁZIS ÉS MATEMATIKAI IQ GENERÁTOROK ---
def create_local_lit_questions(num_local, history):
    pool = [{"tipus": "vers", **v} for v in VERSEK] + [{"tipus": "próza", **p} for p in PROZAK]
    available = [item for item in pool if item["idezet"] not in history]
    if len(available) < num_local:
        available = pool
    
    chosen = random.sample(available, min(num_local, len(available)))
    all_pairs = list({f"{item['szerzo']} – {item['mu']}" for item in pool})
    
    local_qs = []
    for item in chosen:
        correct = f"{item['szerzo']} – {item['mu']}"
        wrong_choices = random.sample([p for p in all_pairs if p != correct], 3)
        opts = wrong_choices + [correct]
        random.shuffle(opts)
        
        label = "versrészletnek" if item["tipus"] == "vers" else "próza- / drámarészletnek"
        q_text = f"Ki a szerzője és mi a címe az alábbi {label}?\n\n> *„{item['idezet']}”*"
        
        local_qs.append({
            "question": q_text,
            "options": opts,
            "answer": correct,
            "explanation": f"Ez az idézet **{item['szerzo']}**: *{item['mu']}* című művéből származik."
        })
        st.session_state.asked_history.append(item["idezet"])
    return local_qs

def create_math_iq_questions(num_math, level):
    iq_qs = []
    patterns = ["aritmetikai", "mertani", "novekvo_kulonbseg", "fibonacci", "valtakozo"]
    if level == "Emelt szint":
        patterns.extend(["negyzetszam_eltolt", "ketlepeses"])

    for _ in range(num_math):
        pattern_type = random.choice(patterns)
        
        if pattern_type == "aritmetikai":
            start = random.randint(2, 25)
            step = random.randint(4, 15)
            seq = [start + i * step for i in range(5)]
            ans = start + 5 * step
            expl = f"Minden lépésben **+{step}** adódik hozzá az előző számhoz ({seq[-1]} + {step} = {ans})."
            
        elif pattern_type == "mertani":
            start = random.randint(2, 5)
            mult = random.choice([2, 3])
            seq = [start * (mult ** i) for i in range(5)]
            ans = start * (mult ** 5)
            expl = f"Minden szám az előző **{mult}-szerese** ({seq[-1]} × {mult} = {ans})."
            
        elif pattern_type == "novekvo_kulonbseg":
            start = random.randint(1, 15)
            diff = random.randint(1, 4)
            seq = [start]
            curr = start
            for i in range(4):
                curr += diff + i
                seq.append(curr)
            ans = curr + diff + 4
            expl = f"A különbség minden lépésben 1-gyel nő (+{diff}, +{diff+1}, +{diff+2}, +{diff+3}, végül **+{diff+4}**)."
            
        elif pattern_type == "fibonacci":
            a, b = random.randint(1, 6), random.randint(2, 8)
            seq = [a, b]
            for _ in range(3):
                seq.append(seq[-1] + seq[-2])
            ans = seq[-1] + seq[-2]
            expl = f"Minden szám az előző két szám összege ({seq[-2]} + {seq[-1]} = {ans})."

        elif pattern_type == "negyzetszam_eltolt":
            offset = random.randint(1, 5)
            seq = [(i + 1) ** 2 + offset for i in range(5)]
            ans = 6 ** 2 + offset
            expl = f"A négyzetszámokhoz (1, 4, 9, 16, 25, 36) minden lépésben **+{offset}** adódik (36 + {offset} = {ans})."

        elif pattern_type == "ketlepeses":
            a = random.randint(2, 10)
            b = random.randint(15, 30)
            seq = [a, b, a + 3, b - 2, a + 6]
            ans = b - 4
            expl = f"Két egymásba fűzött sorozat: a páratlan helyeken **+3**, a páros helyeken **-2** a szabály ({b - 2} - 2 = {ans})."
            
        else:  # valtakozo
            start = random.randint(10, 30)
            plus = random.randint(5, 12)
            minus = random.randint(2, 4)
            seq = [start]
            for i in range(4):
                if i % 2 == 0:
                    seq.append(seq[-1] + plus)
                else:
                    seq.append(seq[-1] - minus)
            ans = seq[-1] + plus
            expl = f"Váltakozó szabály: először **+{plus}**, majd **-{minus}** ismétlődik ({seq[-1]} + {plus} = {ans})."

        wrong_set = set()
        while len(wrong_set) < 3:
            delta = random.choice([-10, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 10])
            if ans + delta > 0 and (ans + delta) != ans:
                wrong_set.add(ans + delta)
                
        opts = [str(w) for w in wrong_set] + [str(ans)]
        random.shuffle(opts)
        seq_str = ", ".join(map(str, seq)) + ", **?**"
        
        iq_qs.append({
            "question": f"Melyik szám következik a logikai sorozatban?\n\n### {seq_str}",
            "options": opts,
            "answer": str(ans),
            "explanation": expl
        })
    return iq_qs
# --- OLDALSÁV (AI & JÁTÉK BEÁLLÍTÁSOK) ---
with st.sidebar:
    st.header("🔑 AI Beállítások")
    
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
    st.header("🎓 Kategória és Szint")
    
    subject = st.selectbox("Tantárgy / Terület:", list(TOPICS.keys()))
    subtopic = st.selectbox("Témakör:", TOPICS[subject])
    custom_topic = st.text_input("Vagy írj be saját tételt/altémát:", placeholder="pl. Aranybulla, Toldi, Fotoszintézis...")
    
    is_iq_selected = "iq" in subject.lower()
    level_label = "Nehézségi szint:" if is_iq_selected else "Érettségi szint:"
    level = st.radio(level_label, ["Középszint", "Emelt szint"], horizontal=True)
    num_questions = st.slider("Kérdések száma egy körben:", 5, 15, 10)
    
    if is_iq_selected:
        st.info("🧠 IQ-teszt módban nincs időkorlát és gyorsasági bónusz – koncentrálj a pontos logikára!")
        speed_mode = False
    else:
        speed_mode = st.toggle("⏱️ Gyorsasági bónusz", value=True, help="Ha kikapcsolod, minden jó válasz fix 200 pontot ér időkorlát nélkül.")

    start_btn = st.button("🚀 Új kör indítása", type="primary", use_container_width=True)

# --- KÉRDÉSEK GENERÁLÁSA (CSAK GOMBNYOMÁSRA!) ---
def generate_quiz(api_key, model_name, subject, topic, level, count, history):
    is_lit = "irodalom" in subject.lower()
    is_iq = "iq" in subject.lower()
    local_qs = []
    ai_count = count

    if is_lit:
        num_local = count // 2
        local_qs = create_local_lit_questions(num_local, history)
        ai_count = count - len(local_qs)
    elif is_iq and ("vegyes" in topic.lower() or "számsorozatok" in topic.lower()):
        num_math = count if "számsorozatok" in topic.lower() else (count // 2)
        local_qs = create_math_iq_questions(num_math, level)
        ai_count = count - len(local_qs)

    formatted_questions = list(local_qs)

    if ai_count > 0:
        client = genai.Client(api_key=api_key)
        history_text = ""
        if history:
            recent = history[-25:]
            history_text = f"\nEzeket a kérdéseket már feltetted korábban, kérlek NE ismételd meg őket:\n- " + "\n- ".join(recent)

        if is_iq:
            prompt = f"""
            Készíts egy {ai_count} feladatból álló, magyar nyelvű, valódi logikai és kognitív IQ-teszt feladatsort!
            
            Témakör: {topic}
            Nehézségi szint: {level} (Középszint = 100–115 IQ szintű feladatok, Emelt szint = 120–140 IQ szintű összetett logikai feladatok)
            
            Szabályok:
            1. Készíts verbális analógiákat (pl. 'A : B = C : ?'), deduktív szillogizmusokat (állító-tagadó logikai következtetéseket), vagy kakukktojás feladatokat!
            2. NE készíts számsorozatokat és NE tegyél fel lexikális műveltségi kérdéseket (pl. évszámok, fővárosok), kizárólag tiszta logikai gondolkodást igénylő feladatokat!
            3. Minden feladathoz pontosan 4 válaszlehetőség tartozzon, és csak egyetlen logikailag támadhatatlan helyes megoldás létezzen.
            4. Az 'explanation' mezőben vezesd le röviden, lépésről lépésre a logikai következtetést!
            {history_text}
            """
        else:
            lit_note = ""
            if is_lit:
                lit_note = "\n5. FONTOS: Ne idézz verseket vagy prózarészleteket (azok külön adatbázisból jönnek), hanem kérdezz irodalomtörténeti összefüggésekre, műfajokra, stíluskorszakokra, cselekményre és életrajzi adatokra!"

            prompt = f"""
            Készíts egy {ai_count} kérdésből álló, pörgős, QuizUp-stílusú magyar nyelvű feleletválasztós kvízt a magyar gimnáziumi érettségi követelmények alapján!
            
            Tantárgy: {subject}
            Témakör: {topic}
            Szint: {level}
            
            Szabályok:
            1. A kérdések legyenek szakmailag 100%-ig pontosak, de tömörek és jól olvashatók.
            2. Minden kérdéshez pontosan 4 válaszlehetőség tartozzon (1 helyes, 3 hihető, de hibás elterelő válasz).
            3. A 'correct_answer' mező karakterre pontosan egyezzen meg a 4 válaszlehetőség egyikével.
            4. Az 'explanation' mezőben adj egy rövid, 1-2 mondatos, tanulást segítő magyarázatot.
            {lit_note}
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

    random.shuffle(formatted_questions)
    return formatted_questions
if start_btn:
    if not api_key:
        st.error("⚠️ Kérlek add meg a Gemini API kulcsot a bal oldali sávban (vagy a Streamlit Secrets-ben)!")
    else:
        chosen_topic = custom_topic.strip() if custom_topic.strip() else subtopic
        with st.spinner(f"⚡ {num_questions} db {level.lower()}ű feladat előkészítése..."):
            try:
                st.session_state.questions = generate_quiz(
                    api_key, model_choice, subject, chosen_topic, level, num_questions, st.session_state.asked_history
                )
                st.session_state.q_index = 0
                st.session_state.score = 0
                st.session_state.correct_count = 0
                st.session_state.answered = False
                st.session_state.last_result = None
                st.session_state.start_time = time.time()
                st.session_state.active_subject = subject
                st.session_state.active_level = level
                st.rerun()
            except Exception as e:
                st.error(f"Hiba történt a generálás során: {e}")

# --- FŐKÉPERNYŐ ---
st.title("⚡ Érettségi & IQ QuizUp")
st.caption("Gimnáziumi érettségi felkészítő és dinamikus kognitív IQ-teszt")

if not st.session_state.questions:
    st.info("👈 Válassz tantárgyat vagy IQ-tesztet a bal oldali menüben, majd kattints az **Új kör indítása** gombra!")
else:
    total_q = len(st.session_state.questions)
    idx = st.session_state.q_index
    running_iq = "iq" in st.session_state.active_subject.lower()

    # Fejléc: Haladás és Pontszám / Helyes válaszok
    col1, col2 = st.columns(2)
    with col1:
        st.progress(idx / total_q)
    with col2:
        if running_iq:
            st.metric("✅ Helyes megoldások", f"{st.session_state.correct_count} / {total_q}")
        else:
            st.metric("🏆 Pontszám", f"{st.session_state.score} pt")

    # JÁTÉK KÖZBEN
    if idx < total_q:
        q_data = st.session_state.questions[idx]
        st.subheader(f"{idx + 1}. / {total_q} feladat")
        st.markdown(f"### {q_data['question']}")

        if not st.session_state.answered:
            for i, option in enumerate(q_data["options"]):
                if st.button(option, key=f"opt_{idx}_{i}", use_container_width=True):
                    elapsed = time.time() - st.session_state.start_time
                    is_correct = (option == q_data["answer"])
                    
                    if is_correct:
                        st.session_state.correct_count += 1
                        if running_iq:
                            st.session_state.score += 200
                            st.session_state.last_result = ("success", "✅ **Helyes logikai következtetés!**")
                        elif speed_mode:
                            effective_time = max(0.0, elapsed - 5.0)
                            speed_bonus = max(0, int((45.0 - effective_time) * (50.0 / 45.0)))
                            gained = 150 + speed_bonus
                            st.session_state.score += gained
                            st.session_state.last_result = ("success", f"✅ Helyes válasz! (+150 alap + {speed_bonus} gyorsasági bónusz = **{gained} pont** | Idő: {elapsed:.1f} mp)")
                        else:
                            gained = 200
                            st.session_state.score += gained
                            st.session_state.last_result = ("success", f"✅ Helyes válasz! (**+200 pont** | Idő: {elapsed:.1f} mp)")
                    else:
                        st.session_state.last_result = ("error", f"❌ Sajnos nem talált! A helyes megoldás: **{q_data['answer']}**")
                    
                    st.session_state.answered = True
                    st.rerun()
        
        else:
            status, msg = st.session_state.last_result
            if status == "success":
                st.success(msg)
            else:
                st.error(msg)
            
            st.info(f"💡 **Magyarázat:** {q_data['explanation']}")
            
            if st.button("Következő kérdés ➡️", type="primary", use_container_width=True):
                st.session_state.q_index += 1
                st.session_state.answered = False
                st.session_state.last_result = None
                st.session_state.start_time = time.time()
                st.rerun()

    # JÁTÉK VÉGE
    else:
        ratio = st.session_state.correct_count / total_q

        if running_iq:
            base_iq = 108 if st.session_state.active_level == "Emelt szint" else 100
            estimated_iq = int(round(base_iq + (ratio - 0.60) * 65))
            estimated_iq = max(75, min(145, estimated_iq))

            st.metric("🧠 Becsült kognitív IQ-értéked", f"{estimated_iq} IQ ({st.session_state.correct_count}/{total_q} helyes)")
            st.caption("Megjegyzés: Ez egy pszichometriai szempontból kalibrált, tájékoztató jellegű becslés (Wechsler-skála, átlag = 100, szórás = 15).")

            if estimated_iq < 90:
                st.warning("🧩 **Átlag alatti tartomány (<90):** Most kicsit fáradtabb volt a logikai fókusz, vagy elkapkodtad a következtetéseket. Pihenj egyet, és próbáld újra!")
            elif estimated_iq < 110:
                st.info("⚖️ **Átlagos intelligencia-tartomány (90–109):** Stabil, kiegyensúlyozott logikai gondolkodás – a népesség nagy többségével azonos szinten teljesítettél.")
            elif estimated_iq < 125:
                st.success("💡 **Átlag feletti intelligencia (110–124):** Kiemelkedő mintafelismerés és gyors absztrakt gondolkodás! Ez már egyetemi/kutatói szintű logikai érzék.")
            elif estimated_iq < 135:
                st.balloons()
                st.success("🚀 **Kiváló, magas intelligencia (125–134):** A népesség felső 5%-ába tartozó logikai teljesítmény! Kiválóan átlátod a rejtett összefüggéseket.")
            else:
                st.balloons()
                st.success("👑 **Kiemelkedő, Mensa-szintű teljesítmény (135+):** A népesség felső 1-2%-ába tartozó zseniális analitikus elme! Gratulálok!")
        else:
            max_possible = total_q * 200
            score_pct = int((st.session_state.score / max_possible) * 100)
            st.metric("Végső pontszámod", f"{st.session_state.score} / {max_possible} pont ({score_pct}%)")

            if score_pct < 25:
                st.error("📕 **Érdemjegy: 1 (Elégtelen)** – Ülj le, fiam, egyes! Augusztusi pótvizsgán találkozunk, addig is elő a tankönyvekkel!")
            elif score_pct < 40:
                st.warning("📙 **Érdemjegy: 2 (Elégséges)** – Rezgő léc, de megvan a kettes! Van még hová fejlődni, de a bizonyítványban már nem piros.")
            elif score_pct < 60:
                st.info("📒 **Érdemjegy: 3 (Közepes)** – Stabil közepes! Nem váltod meg vele a világot, de egy jó erős hármassal már nyugodtan mehetsz haza.")
            elif score_pct < 80:
                st.success("📗 **Érdemjegy: 4 (Jó)** – Szép munka, ez már egy sima négyes! Egy hajszál választott el a jelesről, legközelebb meglesz!")
            else:
                st.balloons()
                st.success("🏆 **Érdemjegy: 5 (Jeles)** – Hűha, gratula! Te már most mehetsz érettségizni, a bizottság is állva tapsolna!")

        if st.button("🔄 Új kör indítása", type="primary"):
            st.session_state.questions = []
            st.rerun()
