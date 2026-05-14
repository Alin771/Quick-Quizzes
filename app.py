import streamlit as st
import pdfplumber
import json
import requests

USE_OLLAMA = True
OLLAMA_AVAILABLE = False

if USE_OLLAMA:
    OLLAMA_URL = "http://localhost:11434/api/generate"
    OLLAMA_MODEL = "gemma2:2b"
    try:
        test_response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if test_response.status_code == 200:
            OLLAMA_AVAILABLE = True
    except:
        pass
else:
    import google.generativeai as genai
    API_KEY = "AIzaSyA1gb1kvisI4ogOdjppQ_jdK5UfIQ-Yg_A"
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel("models/gemini-pro-latest")

st.set_page_config(page_title="Generator Test PDF", layout="centered", page_icon="📚")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { 
        background: linear-gradient(90deg, #4CAF50, #45a049);
        color: white; 
        border-radius: 10px;
        height: 50px;
        font-size: 18px;
        font-weight: bold;
    }
    .stSelectbox div[data-baseweb="select"] {
        border-radius: 10px;
    }
    .question-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        margin: 10px 0;
    }
    .correct-answer {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
    .wrong-answer {
        background-color: #f8d7da;
        border-left: 5px solid #dc3545;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
    .score-box {
        background: linear-gradient(90deg, #4CAF50, #45a049);
        color: white;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        font-size: 24px;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📚 Generator de Test din PDF")
st.markdown("<p style='text-align: center; color: #666;'>Încarcă un PDF și generează un test grilă personalizat</p>", unsafe_allow_html=True)

if 'questions' not in st.session_state:
    st.session_state.questions = None
if 'user_answers' not in st.session_state:
    st.session_state.user_answers = {}
if 'submitted' not in st.session_state:
    st.session_state.submitted = False

uploaded_file = st.file_uploader("📂 Încarcă fișier PDF", type=["pdf"], help="Selectează un fișier PDF pentru a extrage textul")

difficulty = st.selectbox(
    "🎯 Selectează nivelul de dificultate",
    options=["Ușor", "Mediu", "Greu"],
    index=0,
    help="Ușor = întrebări simple, Greu = analiză complexă"
)

def extract_text_from_pdf(pdf_file):
    """Extrage textul dintr-un fișier PDF."""
    text = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        st.error(f"Eroare la citirea PDF: {e}")
    return text

def _get_answer_text(q):
    if not isinstance(q, dict):
        return ""
    answer = q.get("raspuns_corect") or q.get("correctAnswer") or q.get("correct_answer") or q.get("answer", "")
    variants = q.get("variante_raspuns") or q.get("variants") or q.get("options", [])
    if answer and variants and len(answer) == 1 and answer.isalpha():
        idx = ord(answer.upper()) - ord('A')
        if 0 <= idx < len(variants):
            return variants[idx]
    return answer

def _normalize_questions(questions):
    normalized = []
    for q in questions:
        if isinstance(q, dict):
            normalized.append({
                "intrebare": q.get("intrebare") or q.get("question", ""),
                "variante_raspuns": q.get("variante_raspuns") or q.get("variants") or q.get("options", []),
                "raspuns_corect": _get_answer_text(q),
                "explicatie": q.get("explicatie") or q.get("explanation", "")
            })
    return normalized

def _parse_ollama_response(response):
    result = response.json()
    
    if isinstance(result, dict):
        result_text = result.get("response", "")
    elif isinstance(result, str):
        result_text = result
    else:
        result_text = str(result)
    
    if isinstance(result_text, dict):
        json_data = result_text
    elif isinstance(result_text, list):
        json_data = result_text
    else:
        json_start = result_text.find('[')
        json_end = result_text.rfind(']') + 1
        if json_start != -1 and json_end > json_start:
            json_str = result_text[json_start:json_end]
            json_data = json.loads(json_str)
        elif result_text.strip().startswith('{'):
            json_data = json.loads(result_text)
        else:
            raise ValueError("No valid JSON found in response")
    
    if isinstance(json_data, dict):
        questions = json_data
    elif isinstance(json_data, list):
        questions = json_data
    else:
        raise ValueError("Invalid JSON format")
    
    return _normalize_questions(questions)

def generate_test_from_text(text, dificultate, max_retries=3):
    """Generează test grilă folosind LLM sau fallback mock."""
    prompt = f"""Ești un profesor universitar. Bazează-te STRICT pe textul furnizat pentru a genera un test grilă cu 5 întrebări de dificultate {dificultate}. Fiecare întrebare trebuie să aibă 4 variante de răspuns, din care doar una este corectă.

Textul pentru referință:
{text}

Returnează rezultatul STRICT în format JSON, ca o listă de obiecte. Fiecare obiect trebuie să aibă cheile: 'intrebare', 'variante_raspuns' (lista de 4 string-uri), 'raspuns_corect' (string) și 'explicatie'."""
    
    if USE_OLLAMA and OLLAMA_AVAILABLE:
        try:
            response = requests.post(OLLAMA_URL, json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "temperature": 0.7
            }, timeout=60)
            if response.status_code == 200:
                try:
                    result = _parse_ollama_response(response)
                    if result:
                        return result
                except Exception as parse_error:
                    st.warning(f"Eroare la parsarea răspunsului: {parse_error}. Folosesc test mock.")
            else:
                st.warning(f"Ollama a returnat cod {response.status_code}. Folosesc test mock.")
        except requests.exceptions.Timeout:
            st.warning("Ollama a depășit timpul de răspuns (60s). Folosesc test mock.")
        except requests.exceptions.ConnectionError:
            st.warning("Nu se poate conecta la Ollama. Verifică dacă serverul rulează. Folosesc test mock.")
        except Exception as e:
            st.warning(f"Eroare Ollama: {e}. Folosesc test mock.")
    
    st.info("Folosesc test de testare mock. Pentru test real, instalează Ollama sau activează Gemini API.")
    return [
        {
            "intrebare": "Ce informație conține PDF-ul?",
            "variante_raspuns": ["Detalii despre subiect", "Date despre tehnologie", "Informații generale", "Date despre personaje"],
            "raspuns_corect": "Informații generale",
            "explicatie": "PDF-ul conține informații variate despre subiectul la care este dedicat."
        },
        {
            "intrebare": "Care este scopul documentului?",
            "variante_raspuns": ["Divertisment", "Educație", "Promovare", "Documentare"],
            "raspuns_corect": "Documentare",
            "explicatie": "Documentele PDF sunt în mod obișnuit destinate documentării și informării."
        },
        {
            "intrebare": "Câte pagini are de obicei un PDF?",
            "variante_raspuns": ["1-5 pagini", "5-20 pagini", "20-100 de pagini", "100+ pagini"],
            "raspuns_corect": "5-20 pagini",
            "explicatie": "Majoritatea PDF-urilor simple au între 5 și 20 de pagini."
        },
        {
            "intrebare": "Ce format folosește PDF-ul?",
            "variante_raspuns": ["Text simplu", "Pagini scanate", "Format proprietar", "Toate variantele"],
            "raspuns_corect": "Toate variantele",
            "explicatie": "PDF-ul poate conține text, imagini scanate și formate proprietare."
        },
        {
            "intrebare": "Cum se numește tehnologia din PDF?",
            "variante_raspuns": ["PostScript", "Portable Document Format", "Adobe Reader", "Acrobat"],
            "raspuns_corect": "Portable Document Format",
            "explicatie": "PDF este acronim pentru Portable Document Format, creat de Adobe."
        }
    ]

if st.button("Generează Test", type="primary"):
    st.session_state.submitted = False
    st.session_state.user_answers = {}
    if uploaded_file is None:
        st.warning("Te rog încarcă un fișier PDF.")
    else:
        with st.spinner("Se extrage textul din PDF..."):
            text = extract_text_from_pdf(uploaded_file)
        if not text.strip():
            st.warning("Nu s-a putut extrage text din PDF.")
        else:
            spinner_text = 'Ollama (gemma2:2b)' if OLLAMA_AVAILABLE else 'Test Mock'
            with st.spinner(f"Se generează testul cu {spinner_text}..."):
                questions = generate_test_from_text(text, difficulty)
                st.session_state.questions = questions

if st.session_state.questions:
    st.markdown("---")
    st.markdown("### 📝 Testul tău personalizat")
    
    if st.button("🔄 Regenerează Test"):
        st.session_state.submitted = False
        st.session_state.user_answers = {}
    
    with st.form("test_form", clear_on_submit=False):
        for i, q in enumerate(st.session_state.questions):
            st.markdown(f"#### Întrebarea {i+1}")
            st.markdown(f"**{q['intrebare']}**")
            
            answer_key = f"q_{i}"
            selected = st.radio(
                f"Alege răspunsul pentru întrebarea {i+1}",
                options=q["variante_raspuns"],
                key=answer_key,
                index=None
            )
            st.markdown("<br>", unsafe_allow_html=True)
        
        submitted = st.form_submit_button("Trimite Test", type="primary")
        
        if submitted:
            for i in range(len(st.session_state.questions)):
                answer_key = f"q_{i}"
                answer = st.session_state.get(answer_key)
                if answer is not None:
                    st.session_state.user_answers[i] = answer
            st.session_state.submitted = True
    
    if st.session_state.submitted:
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("🔄 Reia Testul"):
                st.session_state.submitted = False
                st.session_state.user_answers = {}
                st.rerun()
        
        score = 0
        total = len(st.session_state.questions)
        
        st.markdown("---")
        st.markdown("### 📊 Rezultate Test")
        
        for i, q in enumerate(st.session_state.questions):
            user_answer = st.session_state.user_answers.get(i)
            correct_answer = q["raspuns_corect"]
            
            if user_answer == correct_answer:
                score += 1
                st.markdown(f"<div class='correct-answer'>✅ <strong>Întrebarea {i+1}:</strong> Răspuns corect! {correct_answer}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='wrong-answer'>❌ <strong>Întrebarea {i+1}:</strong> Răspuns greșit. <br><strong>Corect:</strong> {correct_answer}</div>", unsafe_allow_html=True)
            st.markdown(f"<small><strong>Explicație:</strong> {q['explicatie']}</small>", unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
        
        col1, col2 = st.columns([1, 3])
        with col1:
            percentage = (score / total) * 100
            st.markdown(f"<div class='score-box'>{score}/{total}<br>{percentage:.0f}%<br><small>Scor Final</small></div>", unsafe_allow_html=True)
        
        if percentage >= 80:
            st.balloons()
            st.success("🎉 Excelent! Ai învățat foarte bine materia!")
        elif percentage >= 60:
            st.success("👍 Bine! Poți revizui încă ceva.")
        else:
            st.info("📚 S-ar putea să necesiteți mai multe studiu. Revizuiți materialele.")