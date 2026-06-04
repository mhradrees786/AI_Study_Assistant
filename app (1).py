import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
import threading, json, os, requests, time, urllib.parse
from datetime import datetime
import pyttsx3
import speech_recognition as sr
from pypdf import PdfReader

# ──────────────────────────────────────────────────────────────────────────────
HISTORY_FILE = "aura_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return []
    return []

def save_history(data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

chat_history = load_history()

# ──────────────────────────────────────────────────────────────────────────────
# VOICE
# ──────────────────────────────────────────────────────────────────────────────
def speak(text):
    def _go():
        try:
            eng = pyttsx3.init()
            eng.setProperty("rate", 160)
            eng.say(text[:200])
            eng.runAndWait()
        except: pass
    threading.Thread(target=_go, daemon=True).start()

# ──────────────────────────────────────────────────────────────────────────────
# KEY STORAGE
# ──────────────────────────────────────────────────────────────────────────────
KEY_FILE = "aura_key.txt"

def load_keys():
    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE) as f: return json.load(f)
        except: return {}
    return {}

def save_keys(d):
    with open(KEY_FILE, "w") as f: json.dump(d, f)

# ──────────────────────────────────────────────────────────────────────────────
# AI PROVIDERS
# ──────────────────────────────────────────────────────────────────────────────
def build_messages(history_msgs, system_prompt):
    msgs = [{"role": "system", "content": system_prompt}]
    for m in history_msgs[-10:]:
        msgs.append({
            "role": "user" if m["role"] == "user" else "assistant",
            "content": m["text"]
        })
    return msgs

def try_groq(messages, system_prompt, api_key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": build_messages(messages, system_prompt),
        "max_tokens": 1024,
        "temperature": 0.7
    }
    r = requests.post(url, json=payload,
                      headers={"Authorization": f"Bearer {api_key}",
                               "Content-Type": "application/json"},
                      timeout=30)
    if r.status_code == 200:
        return r.json()["choices"][0]["message"]["content"].strip()
    raise Exception(f"Groq HTTP {r.status_code}: {r.text[:200]}")

def try_gemini(messages, system_prompt, api_key):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-1.5-flash:generateContent?key={api_key}")
    contents = []
    for m in messages[-12:]:
        contents.append({
            "role": "user" if m["role"] == "user" else "model",
            "parts": [{"text": m["text"]}]
        })
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents
    }
    r = requests.post(url, json=payload, timeout=30)
    if r.status_code == 200:
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    raise Exception(f"Gemini HTTP {r.status_code}: {r.text[:200]}")

def try_openrouter(messages, system_prompt, api_key=""):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "HTTP-Referer": "https://auraai.app",
        "X-Title": "Aura AI"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": "meta-llama/llama-3.1-8b-instruct:free",
        "messages": build_messages(messages, system_prompt)
    }
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    if r.status_code == 200:
        content = r.json()["choices"][0]["message"]["content"]
        if content and content.strip():
            return content.strip()
    raise Exception(f"OpenRouter HTTP {r.status_code}: {r.text[:200]}")

def try_pollinations(messages, system_prompt):
    url = "https://text.pollinations.ai/"
    payload = {"messages": build_messages(messages, system_prompt)}
    r = requests.post(url, json=payload,
                      headers={"Content-Type": "application/json",
                               "User-Agent": "AuraAI/2.0"},
                      timeout=35)
    if r.status_code == 200 and r.text.strip():
        return r.text.strip()
    raise Exception(f"Pollinations HTTP {r.status_code}")

def try_pollinations_get(messages, system_prompt):
    last = messages[-1]["text"] if messages else "Hello"
    prompt = f"{system_prompt}\n\nUser: {last}\nAssistant:"
    encoded = urllib.parse.quote(prompt[:600])
    url = f"https://text.pollinations.ai/{encoded}"
    r = requests.get(url, timeout=35)
    if r.status_code == 200 and r.text.strip():
        return r.text.strip()
    raise Exception(f"Pollinations-GET HTTP {r.status_code}")

# ──────────────────────────────────────────────────────────────────────────────
# MAIN ENGINE
# ──────────────────────────────────────────────────────────────────────────────
def get_ai_reply(history_msgs, mode, on_progress=None):
    # Load key from file, fallback to hardcoded
    keys = load_keys()
    groq_key = keys.get("groq", "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")

    system_prompt = (
        f"You are Aura AI, a powerful study assistant in '{mode}' mode. "
        "Give thorough, accurate, cleanly formatted educational responses."
    )

    if on_progress:
        on_progress("Connecting to Groq…")

    try:
        result = try_groq(history_msgs, system_prompt, groq_key)
        if result and len(result.strip()) > 5:
            return result.strip(), "Groq Llama3 ⚡"
    except Exception as ex:
        return (
            f"⚠️ Groq Error: {ex}\n\n"
            "Key check karo — console.groq.com pe valid hai?",
            "Error"
        )

    return "⚠️ Groq ne koi response nahi diya.", "Error"

# ──────────────────────────────────────────────────────────────────────────────
# DESIGN TOKENS
# ──────────────────────────────────────────────────────────────────────────────
BG       = "#FFFFFF"
NAV_BG   = "#F1F3F5"
PANEL_BG = "#E2E8F0"
SURFACE  = "#E9ECEF"
RAISED   = "#DEE2E6"
BORDER   = "#CBD5E1"
ACCENT   = "#0F172A"
TXT      = "#1E293B"
TXT_M    = "#475569"

USER_BG="#E2E8F0"; USER_TXT="#0F172A"; USER_NM="#334155"
AI_BG="#F8FAFC";   AI_TXT="#0F172A";   AI_NM="#0284C7"
SYS_BG="#FEF3C7";  SYS_TXT="#78350F"
ERR_BG="#FEE2E2";  ERR_TXT="#991B1B"

GREEN="#16A34A"; AMBER="#D97706"; RED="#DC2626"
TEAL="#0369A1";  CYAN="#0F766E";  BLUE="#2563EB"

FT_BRAND=("Segoe UI",18,"bold")
FT_HEAD =("Segoe UI",13,"bold")
FT_BODY =("Segoe UI",13)
FT_CHAT =("Segoe UI",13)
FT_CHATB=("Segoe UI",13,"bold")
FT_MONO =("Consolas",11)
FT_SM   =("Segoe UI",11)

# ──────────────────────────────────────────────────────────────────────────────
# ROOT
# ──────────────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")
root = ctk.CTk()
root.title("Aura AI  ·  Study Assistant")
root.geometry("1540x920")
root.minsize(1200, 750)
root.configure(fg_color=BG)
root.grid_rowconfigure(0, weight=1)
root.grid_columnconfigure(0, weight=0)
root.grid_columnconfigure(1, weight=1)
root.grid_columnconfigure(2, weight=0)

# ── LEFT NAV ──────────────────────────────────────────────────────────────────
nav = ctk.CTkFrame(root, width=240, fg_color=NAV_BG, corner_radius=0)
nav.grid(row=0, column=0, sticky="nswe")
nav.grid_propagate(False)
nav.grid_rowconfigure(2, weight=1)
nav.grid_columnconfigure(0, weight=1)

bf = ctk.CTkFrame(nav, fg_color="transparent")
bf.grid(row=0, column=0, sticky="ew", padx=16, pady=(22,10))
ctk.CTkLabel(bf, text="✨", font=("Segoe UI Emoji",24), text_color=ACCENT,
             width=44, height=44, fg_color=SURFACE, corner_radius=22).pack(side="left", padx=(0,10))
bt = ctk.CTkFrame(bf, fg_color="transparent"); bt.pack(side="left")
ctk.CTkLabel(bt, text="Aura AI", font=FT_BRAND, text_color=TXT).pack(anchor="w")
ctk.CTkLabel(bt, text="Study Assistant", font=FT_SM, text_color=TXT_M).pack(anchor="w")
ctk.CTkFrame(nav, height=1, fg_color=BORDER).grid(row=1, column=0, sticky="ew", padx=12, pady=2)

sess_scroll = ctk.CTkScrollableFrame(nav, fg_color="transparent",
                                      scrollbar_button_color=SURFACE,
                                      scrollbar_button_hover_color=ACCENT)
sess_scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=6)
sess_scroll.grid_columnconfigure(0, weight=1)

def add_session(text):
    s = (text[:24]+"…") if len(text)>24 else text
    ctk.CTkButton(sess_scroll, text=f"  💬  {s}", font=FT_BODY, anchor="w",
                   fg_color="transparent", hover_color=SURFACE, text_color=TXT,
                   height=32, corner_radius=10).pack(fill="x", pady=2)

nav_bot = ctk.CTkFrame(nav, fg_color="transparent")
nav_bot.grid(row=3, column=0, sticky="ew", padx=12, pady=14)

def export_log():
    try:
        with open("aura_log.txt","w",encoding="utf-8") as f:
            for e in chat_history: f.write(f"[{e['role'].upper()}] {e['text']}\n")
        set_status("Log saved ✓", GREEN)
        root.after(2500, lambda: set_status("Ready", GREEN))
    except: set_status("Save failed", RED)

ctk.CTkButton(nav_bot, text="📥  Export Log", font=FT_BODY, fg_color=SURFACE,
               hover_color=RAISED, text_color=TXT, height=34, corner_radius=10,
               command=export_log).pack(fill="x", pady=3)

# ── CENTER ────────────────────────────────────────────────────────────────────
center = ctk.CTkFrame(root, fg_color=BG, corner_radius=0)
center.grid(row=0, column=1, sticky="nswe")
center.grid_rowconfigure(1, weight=1)
center.grid_columnconfigure(0, weight=1)

topbar = ctk.CTkFrame(center, fg_color=PANEL_BG, height=56, corner_radius=0)
topbar.grid(row=0, column=0, sticky="ew")
topbar.grid_propagate(False)
topbar.grid_columnconfigure(1, weight=1)
ctk.CTkLabel(topbar, text="Workspace", font=("Segoe UI",15,"bold"),
             text_color=ACCENT).grid(row=0, column=0, padx=20, sticky="w")

mode_var = tk.StringVar(value="Research")
chip_row = ctk.CTkFrame(topbar, fg_color="transparent")
chip_row.grid(row=0, column=1, sticky="w", padx=8)
mode_chips = {}

def pick_mode(m):
    mode_var.set(m)
    for k,b in mode_chips.items():
        b.configure(fg_color=ACCENT if k==m else SURFACE,
                    text_color="#FFFFFF" if k==m else TXT_M)

for mn in ["Research","Code","Math","Summary","General"]:
    b = ctk.CTkButton(chip_row, text=mn, font=FT_SM, width=74, height=27, corner_radius=13,
                       fg_color=ACCENT if mn=="Research" else SURFACE, hover_color=ACCENT,
                       text_color="#FFFFFF" if mn=="Research" else TXT_M,
                       command=lambda x=mn: pick_mode(x))
    b.pack(side="left", padx=2)
    mode_chips[mn] = b

provider_lbl = ctk.CTkLabel(topbar, text="", font=FT_SM, text_color=CYAN)
provider_lbl.grid(row=0, column=2, padx=8)

spill = ctk.CTkFrame(topbar, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=GREEN)
spill.grid(row=0, column=3, padx=8)
sdot = ctk.CTkLabel(spill, text="●", font=FT_SM, text_color=GREEN)
sdot.pack(side="left", padx=(10,3), pady=5)
stxt = ctk.CTkLabel(spill, text="Ready", font=FT_SM, text_color=TXT)
stxt.pack(side="left", padx=(0,10), pady=5)

def set_status(text, color=None):
    c = color or GREEN
    sdot.configure(text_color=c)
    spill.configure(border_color=c)
    stxt.configure(text=text)

clk = ctk.CTkLabel(topbar, text="", font=FT_SM, text_color=TXT_M)
clk.grid(row=0, column=4, padx=(0,16))
def tick():
    clk.configure(text=datetime.now().strftime("%H:%M:%S"))
    root.after(1000, tick)
tick()

# ── CHAT ──────────────────────────────────────────────────────────────────────
chat_scroll = ctk.CTkScrollableFrame(center, fg_color=BG,
                                      scrollbar_button_color=SURFACE,
                                      scrollbar_button_hover_color=ACCENT)
chat_scroll.grid(row=1, column=0, sticky="nsew")
chat_scroll.grid_columnconfigure(0, weight=1)
brow = [0]

def make_bubble(role, text, ts=""):
    ts = ts or datetime.now().strftime("%H:%M")
    cfg = {
        "user": (USER_BG, USER_NM, "▸ You",      USER_TXT, "right"),
        "ai":   (AI_BG,   AI_NM,   "✨ Aura AI", AI_TXT,   "left"),
        "sys":  (SYS_BG,  AMBER,   "◉ System",   SYS_TXT,  "left"),
        "err":  (ERR_BG,  RED,     "✕ Error",    ERR_TXT,  "left"),
    }
    bg, nclr, nlbl, tclr, side = cfg.get(role, cfg["sys"])
    row_f = ctk.CTkFrame(chat_scroll, fg_color="transparent")
    row_f.grid(row=brow[0], column=0, sticky="ew", padx=16, pady=(5,0))
    row_f.grid_columnconfigure(0, weight=1)
    bub = ctk.CTkFrame(row_f, fg_color=bg, corner_radius=16, border_width=1, border_color=BORDER)
    if side == "right":
        bub.grid(row=0, column=0, sticky="e", padx=(100,0))
    else:
        bub.grid(row=0, column=0, sticky="w", padx=(0,100))
    bub.grid_columnconfigure(0, weight=1)
    hdr = ctk.CTkFrame(bub, fg_color="transparent")
    hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(10,2))
    hdr.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(hdr, text=nlbl, font=FT_CHATB, text_color=nclr).grid(row=0,column=0,sticky="w")
    ctk.CTkLabel(hdr, text=ts, font=FT_SM, text_color=TXT_M).grid(row=0,column=1,sticky="e")
    lines = text.split("\n")
    h = min(max(len(lines) + sum(max(0,len(l)//72) for l in lines), 2), 40)
    body = tk.Text(bub, font=FT_CHAT, fg=tclr, bg=bg, relief="flat", bd=0,
                   highlightthickness=0, wrap="word", state="normal", width=1, height=h,
                   padx=14, pady=8, selectbackground=ACCENT, selectforeground="#ffffff",
                   insertwidth=0, cursor="arrow")
    body.insert("1.0", text)
    body.configure(state="disabled")
    body.grid(row=1, column=0, sticky="ew")
    brow[0] += 1
    root.after(80, lambda: chat_scroll._parent_canvas.yview_moveto(1.0))

typing_frame = [None]
def show_typing():
    f = ctk.CTkFrame(chat_scroll, fg_color=AI_BG, corner_radius=16,
                     border_width=1, border_color=BORDER)
    f.grid(row=brow[0], column=0, sticky="w", padx=16, pady=(5,0))
    ctk.CTkLabel(f, text="✨ Aura AI is processing…", font=FT_CHATB,
                 text_color=AI_NM).pack(padx=14, pady=12)
    typing_frame[0] = (f, brow[0])
    brow[0] += 1
    root.after(80, lambda: chat_scroll._parent_canvas.yview_moveto(1.0))

def hide_typing():
    if typing_frame[0]:
        typing_frame[0][0].destroy()
        typing_frame[0] = None

if chat_history:
    make_bubble("sys", "Previous session restored.")
    for e in chat_history: make_bubble(e.get("role","sys"), e.get("text",""))
else:
    make_bubble("ai",
        "Welcome! I'm Aura AI — your Study Assistant.\n\n"
        "⚠️  Pehli baar use karne ke liye FREE Groq key chahiye:\n\n"
        "  1. console.groq.com par jao\n"
        "  2. Google se signup karo (free)\n"
        "  3. API Keys → Create API Key\n"
        "  4. Key copy karo (gsk_... se shuru hogi)\n"
        "  5. Neeche ⚙️ button → Groq field mein paste → Save\n\n"
        "Bas itna! Phir main kaam karna shuru kar dunga 🎉"
    )

# ── INPUT DOCK ────────────────────────────────────────────────────────────────
dock = ctk.CTkFrame(center, fg_color=NAV_BG, height=80, corner_radius=0)
dock.grid(row=2, column=0, sticky="ew")
dock.grid_propagate(False)
dock.grid_columnconfigure(1, weight=1)

att = ctk.CTkFrame(dock, fg_color="transparent")
att.grid(row=0, column=0, padx=(14,4), pady=18)

def do_pdf():
    path = filedialog.askopenfilename(filetypes=[("PDF Files","*.pdf")])
    if not path: return
    try:
        set_status("Reading PDF…", AMBER)
        reader = PdfReader(path)
        txt = "".join(pg.extract_text() or "" for pg in reader.pages)
        if not txt.strip(): set_status("PDF is empty", RED); return
        make_bubble("sys", f"PDF loaded: {os.path.basename(path)}")
        send_query(f"Summarise and analyse this document:\n\n{txt[:4000]}")
    except Exception as ex: set_status(f"PDF error: {ex}", RED)

def do_voice():
    def _listen():
        rec = sr.Recognizer()
        try:
            with sr.Microphone() as src:
                root.after(0, lambda: set_status("Listening…", BLUE))
                audio = rec.listen(src, timeout=6, phrase_time_limit=10)
            set_status("Transcribing…", ACCENT)
            txt = rec.recognize_google(audio)
            root.after(0, lambda: [inp.delete(0,"end"), inp.insert(0,txt),
                                    set_status("Ready", GREEN)])
        except: root.after(0, lambda: set_status("Voice error", RED))
    threading.Thread(target=_listen, daemon=True).start()

for ico, fn, clr in [("📎", do_pdf, AMBER), ("🎤", do_voice, TEAL)]:
    ctk.CTkButton(att, text=ico, font=("Segoe UI Emoji",16), width=40, height=44,
                   corner_radius=10, fg_color=SURFACE, hover_color=RAISED,
                   text_color=clr, command=fn).pack(side="left", padx=3)

inp = ctk.CTkEntry(dock, placeholder_text="Ask anything — maths, science, code, history…",
                    font=("Segoe UI",13), fg_color=BG, border_color=BORDER, border_width=1,
                    text_color=TXT, placeholder_text_color=TXT_M, height=46, corner_radius=14)
inp.grid(row=0, column=1, padx=10, pady=17, sticky="ew")

def dispatch(event=None):
    q = inp.get().strip()
    if not q: return "break"
    inp.delete(0,"end")
    send_query(q)
    return "break"

inp.bind("<Return>", dispatch)

send_btn = ctk.CTkButton(dock, text="Send  ➤", font=FT_HEAD, width=100, height=46,
                          corner_radius=14, fg_color=ACCENT, hover_color=TXT_M,
                          text_color="#FFFFFF", command=dispatch)
send_btn.grid(row=0, column=2, padx=(0,6), pady=17)

# ── SETTINGS ──────────────────────────────────────────────────────────────────
def open_settings():
    win = ctk.CTkToplevel(root)
    win.title("⚙️ API Keys")
    win.geometry("560x420")
    win.configure(fg_color=BG)
    win.grab_set()
    win.resizable(False, False)

    ctk.CTkLabel(win, text="⚙️ API Keys (Sab FREE hain)",
                  font=("Segoe UI",16,"bold"), text_color=TXT).pack(pady=(20,4))
    ctk.CTkLabel(win,
        text="Groq recommend hai — fastest aur bilkul free!",
        font=FT_SM, text_color=TXT_M).pack(pady=(0,14))

    keys = load_keys()
    entries = {}

    for fk, label, placeholder in [
        ("groq",       "🚀 Groq Key  (console.groq.com)",            "gsk_..."),
        ("gemini",     "✨ Gemini Key  (aistudio.google.com)",        "AIza..."),
        ("openrouter", "🔓 OpenRouter Key  (openrouter.ai)",          "sk-or-..."),
    ]:
        ctk.CTkLabel(win, text=label, font=FT_HEAD, text_color=TXT).pack(
            anchor="w", padx=30, pady=(10,2))
        e = ctk.CTkEntry(win, width=480, height=36, font=("Consolas",11),
                          fg_color=SURFACE, border_color=BORDER, text_color=TXT,
                          placeholder_text=placeholder)
        e.pack(pady=(2,0))
        if keys.get(fk): e.insert(0, keys[fk])
        entries[fk] = e

    def save_and_close():
        d = load_keys()
        for fk, entry in entries.items():
            val = entry.get().strip()
            if val: d[fk] = val
        save_keys(d)
        set_status("Keys saved ✓", GREEN)
        root.after(2000, lambda: set_status("Ready", GREEN))
        win.destroy()

    ctk.CTkButton(win, text="💾 Save Keys", font=FT_HEAD, fg_color=ACCENT,
                   hover_color=TXT_M, text_color="#FFFFFF", height=42,
                   corner_radius=21, command=save_and_close).pack(pady=20)

ctk.CTkButton(dock, text="⚙️", font=("Segoe UI Emoji",16), width=46, height=46,
               corner_radius=10, fg_color=SURFACE, hover_color=RAISED, text_color=TXT,
               command=open_settings).grid(row=0, column=3, padx=(0,14), pady=17)

# ── RIGHT PANEL ───────────────────────────────────────────────────────────────
rp = ctk.CTkFrame(root, width=260, fg_color=NAV_BG, corner_radius=0)
rp.grid(row=0, column=2, sticky="nswe")
rp.grid_propagate(False)

def sec(title):
    f = ctk.CTkFrame(rp, fg_color=BG, corner_radius=14, border_width=1, border_color=BORDER)
    f.pack(fill="x", padx=14, pady=7)
    ctk.CTkLabel(f, text=title, font=FT_MONO, text_color=TXT_M).pack(
        anchor="w", padx=14, pady=(10,4))
    return f

sc = sec("SESSION STATS")
_sv = {}
for label, clr in [("Messages",ACCENT),("PDFs",CYAN),("Voice",TEAL)]:
    r = ctk.CTkFrame(sc, fg_color="transparent"); r.pack(fill="x", padx=14, pady=2)
    ctk.CTkLabel(r, text=label, font=FT_BODY, text_color=TXT_M).pack(side="left")
    v = tk.StringVar(value="0"); _sv[label] = v
    ctk.CTkLabel(r, textvariable=v, font=("Segoe UI",13,"bold"), text_color=clr).pack(side="right")

def inc(k): _sv[k].set(str(int(_sv[k].get())+1))

tc = sec("FEATURES")
tts_v = tk.BooleanVar(value=True)
ctk.CTkSwitch(tc, text="🔊 Read replies aloud", font=FT_BODY, text_color=TXT_M,
               progress_color=ACCENT, button_color=SURFACE,
               variable=tts_v).pack(anchor="w", padx=14, pady=4)

qc = sec("QUICK PROMPTS")
for qp in ["Explain this simply","5 practice questions","Summarise key points"]:
    ctk.CTkButton(qc, text=qp, font=FT_BODY, anchor="w", fg_color=SURFACE,
                   hover_color=RAISED, text_color=TXT, height=28, corner_radius=8,
                   command=lambda p=qp: [inp.delete(0,"end"), inp.insert(0,p),
                                          dispatch()]).pack(fill="x", padx=10, pady=2)

def clear_workspace():
    global chat_history
    chat_history = []
    save_history([])
    for w in chat_scroll.winfo_children(): w.destroy()
    brow[0] = 0
    for v in _sv.values(): v.set("0")
    for w in sess_scroll.winfo_children(): w.destroy()
    make_bubble("ai", "Fresh workspace ready.")
    set_status("Ready", GREEN)

ctk.CTkButton(rp, text="＋ New Chat", font=FT_HEAD, fg_color=ACCENT, hover_color=TXT_M,
               text_color="#FFFFFF", height=40, corner_radius=20,
               command=clear_workspace).pack(fill="x", padx=14, pady=(6,4))
ctk.CTkButton(rp, text="🗑 Clear All", font=FT_HEAD, fg_color=SURFACE, hover_color=RAISED,
               border_color=RED, border_width=1, text_color=RED, height=38,
               corner_radius=19, command=clear_workspace).pack(fill="x", padx=14, pady=(4,16))

# ── QUERY MANAGER ─────────────────────────────────────────────────────────────
def send_query(prompt):
    if not prompt.strip(): return
    make_bubble("user", prompt)
    add_session(prompt)
    inc("Messages")
    chat_history.append({"role":"user","text":prompt})
    save_history(chat_history)
    set_status("Connecting…", AMBER)
    send_btn.configure(state="disabled", fg_color=SURFACE, text_color=TXT_M)
    inp.configure(state="disabled")
    show_typing()

    def _call():
        def _progress(msg): root.after(0, lambda: set_status(msg, AMBER))
        reply, provider = get_ai_reply(chat_history, mode_var.get(), _progress)

        def _done():
            hide_typing()
            make_bubble("ai", reply)
            provider_lbl.configure(text=f"via {provider}")
            chat_history.append({"role":"ai","text":reply})
            save_history(chat_history)
            set_status("Ready", GREEN)
            send_btn.configure(state="normal", fg_color=ACCENT, text_color="#FFFFFF")
            inp.configure(state="normal")
            inp.focus()
            if tts_v.get(): speak(reply.split("\n")[0][:180])

        root.after(0, _done)

    threading.Thread(target=_call, daemon=True).start()

# ──────────────────────────────────────────────────────────────────────────────
inp.focus()
root.mainloop()
