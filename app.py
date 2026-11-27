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
        "Teljes 30 kérdéses lépcsőzetes IQ-teszt (90–145 IQ)",
        "Téri-vizuális logika és mátrixok (lépcsőzetes)",
        "Számsorozatok és matematikai minták (lépcsőzetes)",
        "Verbális analógiák és fogalmi logika (lépcsőzetes)",
        "Deduktív logikai rejtvények (lépcsőzetes)"
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
if "iq_raw_points" not in st.session_state:
    st.session_state.iq_raw_points = 0
if "iq_max_points" not in st.session_state:
    st.session_state.iq_max_points = 0
if "iq_total_time" not in st.session_state:
    st.session_state.iq_total_time = 0.0
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
# --- HELYI IRODALMI ADATBÁZIS ---
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
            "explanation": f"Ez az idézet **{item['szerzo']}**: *{item['mu']}* című művéből származik.",
            "weight": 1,
            "tier_label": ""
        })
        st.session_state.asked_history.append(item["idezet"])
    return local_qs

# --- LÉPCSŐZETES MATEMATIKAI IQ-GENERÁTOR (1-4. NEHÉZSÉGI SZINT) ---
def generate_single_math_iq(tier):
    if tier == 1:  # 90-105 IQ: Alapvető számsorok
        if random.choice([True, False]):
            start = random.randint(3, 25)
            step = random.randint(4, 13)
            seq = [start + i * step for i in range(5)]
            ans = start + 5 * step
            expl = f"Minden lépésben **+{step}** adódik hozzá az előző számhoz ({seq[-1]} + {step} = {ans})."
        else:
            start = random.randint(2, 5)
            mult = random.choice([2, 3])
            seq = [start * (mult ** i) for i in range(5)]
            ans = start * (mult ** 5)
            expl = f"Minden szám az előző **{mult}-szerese** ({seq[-1]} × {mult} = {ans})."

    elif tier == 2:  # 105-120 IQ: Növekvő különbség vagy Fibonacci
        if random.choice([True, False]):
            start = random.randint(2, 15)
            diff = random.randint(2, 5)
            seq = [start]
            curr = start
            for i in range(4):
                curr += diff + i
                seq.append(curr)
            ans = curr + diff + 4
            expl = f"A különbség minden lépésben 1-gyel nő (+{diff}, +{diff+1}, +{diff+2}, +{diff+3}, végül **+{diff+4}**)."
        else:
            a, b = random.randint(2, 7), random.randint(3, 9)
            seq = [a, b]
            for _ in range(3):
                seq.append(seq[-1] + seq[-2])
            ans = seq[-1] + seq[-2]
            expl = f"Fibonacci-elv: minden szám az előző két szám összege ({seq[-2]} + {seq[-1]} = {ans})."

    elif tier == 3:  # 120-132 IQ: Kettős egymásba fűzött sorozat vagy eltolt négyzetszámok
        if random.choice([True, False]):
            a = random.randint(3, 12)
            b = random.randint(25, 45)
            seq = [a, b, a + 4, b - 3, a + 8]
            ans = b - 6
            expl = f"Két egymásba fűzött sorozat: a páratlan helyeken **+4**, a páros helyeken **-3** a szabály ({b - 3} - 3 = {ans})."
        else:
            offset = random.randint(2, 7)
            seq = [(i + 2) ** 2 + offset for i in range(5)]
            ans = 7 ** 2 + offset
            expl = f"A négyzetszámokhoz (4, 9, 16, 25, 36, 49) minden lépésben **+{offset}** adódik (49 + {offset} = {ans})."

    else:  # tier == 4: 132-145+ IQ (Mensa szint): Köbszámok / Kétszintű szorzás+eltolás / Prím-lépés
        sub = random.choice(["kob", "szorzas_plusz", "prim_lepes"])
        if sub == "kob":
            offset = random.randint(1, 5)
            seq = [(i + 1) ** 3 - offset for i in range(5)]
            ans = 6 ** 3 - offset
            expl = f"A köbszámokból (1, 8, 27, 64, 125, 216) minden lépésben **{offset}** van kivonva (216 - {offset} = {ans})."
        elif sub == "szorzas_plusz":
            start = random.randint(2, 4)
            seq = [start]
            for i in range(4):
                seq.append(seq[-1] * 2 + (i + 1))
            ans = seq[-1] * 2 + 5
            expl = f"Minden lépésben az előző szám **duplájához** adjuk hozzá a lépés sorszámát (×2+1, ×2+2, ×2+3, ×2+4, végül **×2+5** = {ans})."
        else:
            primes = [2, 3, 5, 7, 11, 13]
            start = random.randint(5, 15)
            seq = [start]
            for p in primes[:4]:
                seq.append(seq[-1] + p)
            ans = seq[-1] + primes[4]
            expl = f"A növekmények az egymást követő **prímszámok** (+2, +3, +5, +7, végül **+11** = {ans})."

    wrong_set = set()
    while len(wrong_set) < 3:
        delta = random.choice([-12, -8, -6, -5, -4, -3, -2, -1, 1, 2, 3, 4, 5, 6, 8, 12])
        if ans + delta > 0 and (ans + delta) != ans:
            wrong_set.add(ans + delta)

    opts = [str(w) for w in wrong_set] + [str(ans)]
    random.shuffle(opts)
    seq_str = ", ".join(map(str, seq)) + ", **?**"
    tier_names = {
        1: "I. szint (90–105 IQ)",
        2: "II. szint (105–120 IQ)",
        3: "III. szint (120–132 IQ)",
        4: "IV. szint – Mensa zóna (132–145+ IQ)"
    }

    return {
        "question": f"Melyik szám következik a logikai sorozatban?\n\n### {seq_str}",
        "options": opts,
        "answer": str(ans),
        "explanation": expl,
        "weight": tier,
        "tier_label": tier_names[tier]
    }

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
    
    if is_iq_selected:
        st.info("🧠 **30 kérdéses lépcsőzetes IQ-teszt (25 perc):**\n1–8. kérdés: 90–105 IQ\n9–16. kérdés: 105–120 IQ\n17–24. kérdés: 120–132 IQ\n25–30. kérdés: 132–145+ IQ (Mensa)")
        level = "Lépcsőzetes (90–145 IQ)"
        num_questions = 30
        speed_mode = False
    else:
        level = st.radio("Érettségi szint:", ["Középszint", "Emelt szint"], horizontal=True)
        num_questions = st.slider("Kérdések száma egy körben:", 5, 15, 10)
        speed_mode = st.toggle("⏱️ Gyorsasági bónusz", value=True, help="Ha kikapcsolod, minden jó válasz fix 200 pontot ér időkorlát nélkül.")

    start_btn = st.button("🚀 Új kör indítása", type="primary", use_container_width=True)
# --- KÉRDÉSEK GENERÁLÁSA (CSAK GOMBNYOMÁSRA!) ---
def generate_quiz(api_key, model_name, subject, topic, level, count, history):
    is_lit = "irodalom" in subject.lower()
    is_iq = "iq" in subject.lower()
    client = genai.Client(api_key=api_key)

    # --- LÉPCSŐZETES 30 KÉRDÉSES IQ TESZT ---
    if is_iq:
        tier_plan = [1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4]
        tier_names = {
            1: "I. szint (90–105 IQ)",
            2: "II. szint (105–120 IQ)",
            3: "III. szint (120–132 IQ)",
            4: "IV. szint – Mensa zóna (132–145+ IQ)"
        }
        
        if "számsorozatok" in topic.lower():
            return [generate_single_math_iq(t) for t in tier_plan]
        
        # Vegyes IQ: minden 3. feladat matekos (10 db), 20 db AI (téri-vizuális + deduktív)
        math_indices = set(range(0, 30, 3)) if "teljes" in topic.lower() else set()
        ai_needed = 30 - len(math_indices)

        # Véletlenszerű témakörök az ismétlődés ellen
        themes_pool = [
            "űrállomás zsiliprendszerei", "kódolt diplomáciai üzenetek", "fogaskerekek és óraművek",
            "alkimista fiolák és mérlegek", "labirintusok és iránytűk", "kristályrácsok",
            "vonatszerelvények rendezése", "tükörszobák és fénysugarak", "ősi naptárak",
            "kibernetikus áramkörök", "hajózási útvonalak", "színházi ülésrend"
        ]
        selected_themes = ", ".join(random.sample(themes_pool, 6))

        visual_focus = "100% TÉRI-VIZUÁLIS LOGIKA (Unicode mátrixok, mentális kockahajtogatás, papírhajtogatás, iránykövetés)!" if "téri" in topic.lower() else """
        - 40% TÉRI-VIZUÁLIS LOGIKA (kép nélkül, szöveggel és szimbólumokkal):
          * Unicode mátrixok (3x3-as rácsok pl. ▲, ▼, ◀, ▶, ■, □, ●, ○, ◐, ◑ karakterekkel, ahol a sorok/oszlopok forgását vagy eltolódását kell folytatni, a hiányzó helyen '?' jellel).
          * Mentális kockahajtogatás (kiterített kocka szemközti vagy szomszédos oldalai).
          * Papírhajtogatás és lyukasztás (hogyan néz ki a papír kihajtva).
          * Térbeli irány- és útvonalkövetés (forgatások, tükrözések, égtájak).
        - 60% DEDUKTÍV ÉS VERBÁLIS LOGIKA:
          * Elvont fogalmi analógiák, több feltételes kizárásos rejtvények, szillogizmusok.
        """

        prompt = f"""
        Készíts pontosan {ai_needed} darab magyar nyelvű, valódi kognitív IQ-teszt feladatot SZIGORÚAN NÖVEKVŐ NEHÉZSÉGI SORRENDBEN!
        Témakör: {topic}
        
        FELADATTÍPUSOK ELOSZTÁSA (keverd őket minden nehézségi szinten):
        {visual_focus}

        KREATIVITÁS ÉS ISMÉTLŐDÉS ELKERÜLÉSE:
        - Használd ezeket az egyedi kerettörténeteket: {selected_themes}.
        - TILTÓLISTA: rózsák és virágok, 3 lámpakapcsoló, folyón átkelő farkas/kecske, hazudós/igazmondó őrök alapverziója.
        - Minden generálásnál találj ki teljesen új struktúrákat!

        A feladatok sorrendje és nehézsége kövesse ezt a 4 lépcsőt:
        - Az első {ai_needed // 4} feladat: KÖNNYŰ (90–105 IQ szint – alap analógiák, egyszerű iránykövetés vagy 1 lépéses szimbólumminták).
        - A következő {ai_needed // 4} feladat: KÖZEPES (105–120 IQ szint – elvontabb analógiák, 2 lépéses téri forgatások, kiterített kockák).
        - A következő {ai_needed // 4} feladat: NEHÉZ (120–132 IQ szint – összetett szillogizmusok, 3x3-as kétváltozós Unicode mátrixok, több feltételes rejtvények).
        - Az utolsó {ai_needed - 3*(ai_needed // 4)} feladat: EXTRÉM NEHÉZ / MENSA SZINT (132–145+ IQ szint – mély absztrakt logikai paradoxonok, komplex mentális 3D forgatások, többszörösen összetett kizárásos rejtvények).
        
        Szabályok:
        1. NE készíts számsorozatokat és NE kérdezz lexikális műveltségi adatokat!
        2. Unicode mátrixoknál használj sortöréseket (\\n), hogy rácsszerűen jelenjen meg!
        3. Minden feladathoz pontosan 4 válaszlehetőség tartozzon, és csak egyetlen logikailag támadhatatlan helyes válasz létezzen.
        4. Az 'explanation' mezőben vezesd le röviden a logikai megoldást!
        """

        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=QuizSet,
                temperature=0.95
            ),
        )
        ai_qs = QuizSet.model_validate_json(response.text).questions
        
        final_iq_list = []
        ai_idx = 0
        for i in range(30):
            t = tier_plan[i]
            if i in math_indices:
                final_iq_list.append(generate_single_math_iq(t))
            else:
                if ai_idx < len(ai_qs):
                    q = ai_qs[ai_idx]
                    ai_idx += 1
                    opts = list(q.options)
                    random.shuffle(opts)
                    final_iq_list.append({
                        "question": q.question,
                        "options": opts,
                        "answer": q.correct_answer,
                        "explanation": q.explanation,
                        "weight": t,
                        "tier_label": tier_names[t]
                    })
                else:
                    final_iq_list.append(generate_single_math_iq(t))
        return final_iq_list

    # --- NORMÁL ÉRETTSÉGI KVÍZ ---
    local_qs = []
    ai_count = count
    if is_lit:
        num_local = count // 2
        local_qs = create_local_lit_questions(num_local, history)
        ai_count = count - len(local_qs)

    formatted_questions = list(local_qs)
    if ai_count > 0:
        history_text = ""
        if history:
            recent = history[-25:]
            history_text = f"\nEzeket a kérdéseket már feltetted korábban, kérlek NE ismételd meg őket:\n- " + "\n- ".join(recent)

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
        2. Minden kérdéshez pontosan 4 válaszlehetőség tartozzon, csak 1 helyes válasszal.
        3. Az 'explanation' mezőben adj rövid, közérthető magyarázatot.
        4. Kerüld az ismétlődő, unalmas kliséket.{lit_note}{history_text}
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
        for q in QuizSet.model_validate_json(response.text).questions:
            opts = list(q.options)
            random.shuffle(opts)
            formatted_questions.append({
                "question": q.question,
                "options": opts,
                "answer": q.correct_answer,
                "explanation": q.explanation,
                "weight": 1,
                "tier_label": ""
            })
            st.session_state.asked_history.append(q.question)

    random.shuffle(formatted_questions)
    return formatted_questions

# --- KÖR INDÍTÁSA ---
if start_btn:
    if not api_key:
        st.error("⚠️ Kérlek add meg a Gemini API kulcsot a bal oldali sávban (vagy a Streamlit Secrets-ben)!")
    else:
        chosen_topic = custom_topic.strip() if custom_topic.strip() else subtopic
        with st.spinner(f"⚡ {num_questions} db feladat előkészítése..."):
            try:
                st.session_state.questions = generate_quiz(
                    api_key, model_choice, subject, chosen_topic, level, num_questions, st.session_state.asked_history
                )
                st.session_state.q_index = 0
                st.session_state.score = 0
                st.session_state.correct_count = 0
                st.session_state.iq_raw_points = 0
                st.session_state.iq_max_points = sum(q.get("weight", 1) for q in st.session_state.questions)
                st.session_state.iq_total_time = 0.0
                st.session_state.answered = False
                st.session_state.last_result = None
                st.session_state.start_time = time.time()
                st.session_state.active_subject = subject
                st.rerun()
            except Exception as e:
                st.error(f"Hiba történt a generálás során: {e}")
# --- FŐKÉPERNYŐ ---
st.title("⚡ Érettségi & IQ QuizUp")
st.caption("Gimnáziumi érettségi felkészítő és 30 kérdéses lépcsőzetes kognitív IQ-teszt")

if not st.session_state.questions:
    st.info("👈 Válassz tantárgyat vagy a 30 kérdéses lépcsőzetes IQ-tesztet a bal oldali menüben, majd kattints az **Új kör indítása** gombra!")
else:
    total_q = len(st.session_state.questions)
    idx = st.session_state.q_index
    running_iq = "iq" in st.session_state.active_subject.lower()

    col1, col2 = st.columns(2)
    with col1:
        st.progress(idx / total_q)
    with col2:
        if running_iq:
            mins = int(st.session_state.iq_total_time // 60)
            secs = int(st.session_state.iq_total_time % 60)
            st.metric("✅ Helyes megoldások", f"{st.session_state.correct_count} / {total_q}", f"⏱️ {mins:02d}:{secs:02d} / 25:00")
        else:
            st.metric("🏆 Pontszám", f"{st.session_state.score} pt")

    # JÁTÉK KÖZBEN
    if idx < total_q:
        q_data = st.session_state.questions[idx]
        if running_iq and q_data.get("tier_label"):
            st.caption(f"📊 Nehézségi zóna: **{q_data['tier_label']}** (Súlyozás: {q_data.get('weight', 1)}x)")
        st.subheader(f"{idx + 1}. / {total_q} feladat")

        if any(sym in q_data['question'] for sym in ["▲", "■", "●", "◐", "□", "○"]):
            st.markdown(q_data['question'].replace("\n", "  \n"))
        else:
            st.markdown(f"### {q_data['question']}")

        if not st.session_state.answered:
            for i, option in enumerate(q_data["options"]):
                if st.button(option, key=f"opt_{idx}_{i}", use_container_width=True):
                    elapsed = time.time() - st.session_state.start_time
                    is_correct = (option == q_data["answer"])
                    
                    if running_iq:
                        st.session_state.iq_total_time += elapsed
                    
                    if is_correct:
                        st.session_state.correct_count += 1
                        if running_iq:
                            w = q_data.get("weight", 1)
                            st.session_state.iq_raw_points += w
                            st.session_state.score += w * 100
                            st.session_state.last_result = ("success", f"✅ **Helyes logikai következtetés!** (+{w} pont | Idő: {elapsed:.1f} mp)")
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
        if running_iq:
            max_w = max(1, st.session_state.iq_max_points)
            weighted_ratio = st.session_state.iq_raw_points / max_w
            base_iq = 75 + weighted_ratio * 70

            total_t = st.session_state.iq_total_time
            if total_t < 1500:
                time_adj = min(5.0, ((1500 - total_t) / 900.0) * 5.0) * weighted_ratio
            else:
                time_adj = -min(5.0, ((total_t - 1500) / 900.0) * 5.0)

            estimated_iq = int(round(base_iq + time_adj))
            estimated_iq = max(75, min(145, estimated_iq))

            mins = int(total_t // 60)
            secs = int(total_t % 60)

            st.metric(
                "🧠 Súlyozott kognitív IQ-értéked",
                f"{estimated_iq} IQ",
                delta=f"{st.session_state.correct_count}/{total_q} helyes | Idő: {mins:02d}:{secs:02d} (Időkorrekció: {time_adj:+.1f} IQ)"
            )
            st.caption("Megjegyzés: Lépcsőzetes nehézségű (90–145 IQ), téri-vizuális, numerikus és deduktív feladatokat kombináló, 25 perces időkeretre kalibrált becslés.")

            if estimated_iq < 90:
                st.warning("🧩 **Átlag alatti tartomány (<90):** Az alapszintű feladatoknál is becsúszott több hiba. Pihenj egyet, és próbáld újra friss fejjel!")
            elif estimated_iq < 110:
                st.info("⚖️ **Átlagos intelligencia-tartomány (90–109):** Stabil teljesítmény az első két zónában – a népesség nagy többségével azonos szinten gondolkodsz.")
            elif estimated_iq < 125:
                st.success("💡 **Átlag feletti intelligencia (110–124):** A III. zóna (120+ IQ) feladataival is sikeresen megbirkóztál! Kiemelkedő analitikus gondolkodás.")
            elif estimated_iq < 135:
                st.balloons()
                st.success("🚀 **Kiváló, magas intelligencia (125–134):** A népesség felső 5%-ába tartozó logikai teljesítmény! A legnehezebb feladványok nagy részét is megoldottad.")
            else:
                st.balloons()
                st.success("👑 **Mensa-szintű kiemelkedő teljesítmény (135–145):** A népesség felső 1–2%-ába tartozó zseniális elme! A IV. (Mensa) zóna feladatai sem fogtak ki rajtad!")
        else:
            max_possible = total_q * 200
            score_pct = int((st.session_state.score / max_possible) * 100)
            st.metric("Végső pontszámod", f"{st.session_state.score} / {max_possible} pont ({score_pct}%)")

            if score_pct < 25:
                st.error("📕 **Érdemjegy: 1 (Elégtelen)** – Ülj le, fiam, egyes! Augusztusi pótvizsgán találkozunk, addig is elő a tankönyvekkel!")
            elif score_pct < 40:
                st.warning("📙 **Érdemjegy: 2 (Elégséges)** – Éppen csak átcsúsztál a léc alatt, de az érettségin ez már megvan!")
            elif score_pct < 60:
                st.info("📒 **Érdemjegy: 3 (Közepes)** – Stabil alapok, de van még mit csiszolni a biztos tudáshoz!")
            elif score_pct < 80:
                st.success("📗 **Érdemjegy: 4 (Jó)** – Szép munka! Pár apró részlet hiányzik csak a kitűnőhöz.")
            else:
                st.balloons()
                st.success("📘 **Érdemjegy: 5 (Jeles)** – Kiváló teljesítmény, érettségire készen állsz!")
