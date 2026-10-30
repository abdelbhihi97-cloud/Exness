# app.py
import streamlit as st
import yfinance as yf
import pandas as pd
import time

# ============================================================
# 1) إعدادات الصفحة (مصممة للجوال أولاً)
# ============================================================
st.set_page_config(
    page_title="إشارات التداول | Exness",
    page_icon="📈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ============================================================
# 2) تصميم CSS متجاوب للهاتف
# ============================================================
st.markdown("""
<style>
    /* تصغير الهوامش لشاشة الجوال */
    .block-container { padding-top: 1.2rem; padding-bottom: 1rem; }

    /* كرت الإشارة الكبير */
    div.signal-card {
        border-radius: 18px;
        padding: 30px 10px;
        text-align: center;
        margin: 15px 0;
        font-family: sans-serif;
        box-shadow: 0 4px 15px rgba(0,0,0,0.25);
    }
    .signal-buy  { background: linear-gradient(135deg, #00c853, #009624); color: white; }
    .signal-sell { background: linear-gradient(135deg, #ff1744, #b71c1c); color: white; }
    .signal-hold { background: linear-gradient(135deg, #9e9e9e, #616161); color: white; }

    .signal-title { font-size: 2.6em; font-weight: 900; letter-spacing: 2px; }
    .signal-sub   { font-size: 1.1em; margin-top: 6px; opacity: 0.95; }

    /* أرقام الدخول و SL و TP */
    div.price-row {
        background: #1e1e2e;
        border-radius: 14px;
        padding: 14px 18px;
        margin: 8px 0;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .price-label { color: #aaa; font-size: 1.0em; }
    .price-value { color: #ffffff; font-size: 1.5em; font-weight: 800; font-family: monospace; }
    .val-sl  { color: #ff6b6b !important; }
    .val-tp  { color: #4ade80 !important; }
    .val-ent { color: #60a5fa !important; }

    /* عنوان المؤشرات */
    .ind-title { color: #888; font-size: 0.95em; margin: 18px 0 6px 0; font-weight: 600; }

    /* تحذير */
    .warn-box {
        background: #2b1d1d; color: #ffb4b4;
        border-radius: 10px; padding: 10px; font-size: 0.85em; margin-top: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 3) قائمة العملات المطابقة لرموز Yahoo (بدون تأخير زمني)
# ============================================================
ASSETS = {
    "Bitcoin (BTCUSD)": "BTC-USD",
    "Gold (XAUUSD)":    "GC=F",
    "EURUSD":           "EURUSD=X",
}

# ============================================================
# 4) محرك التحليل الفني (EMA + RSI + ATR)
# ============================================================
def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low  = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close  = (df["Low"]  - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

@st.cache_data(ttl=60, show_spinner=False)
def fetch_and_analyze(symbol: str) -> dict:
    """جلب بيانات فريم 5 دقائق وحساب جميع المؤشرات"""
    df = yf.Ticker(symbol).history(period="5d", interval="5m")
    if df is None or len(df) < 30:
        return None

    df["EMA9"]  = df["Close"].ewm(span=9,  adjust=False).mean()
    df["EMA21"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["RSI"]   = compute_rsi(df["Close"])
    df["ATR"]   = compute_atr(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    price = float(last["Close"])
    rsi   = float(last["RSI"])
    atr   = float(last["ATR"])

    # ---- منطق الإشارة (توافق EMA + RSI) ----
    ema9, ema21 = float(last["EMA9"]), float(last["EMA21"])
    uptrend   = ema9 > ema21
    crossover = (prev["EMA9"] <= prev["EMA21"] and ema9 > ema21)  # تقاطع صاعد حديث

    if (uptrend or crossover) and rsi < 35:
        signal = "BUY"
    elif (not uptrend) and rsi > 65:
        signal = "SELL"
    else:
        signal = "HOLD"

    # ---- حساب SL / TP بدقة ATR (SL = 1.5×ATR | TP = 2.5×ATR) ----
    sl_dist = 1.5 * atr
    tp_dist = 2.5 * atr
    if signal == "BUY":
        entry, sl, tp = price, price - sl_dist, price + tp_dist
    elif signal == "SELL":
        entry, sl, tp = price, price + sl_dist, price - tp_dist
    else:
        entry, sl, tp = price, price - sl_dist, price + tp_dist  # توضيحي فقط

    return {
        "signal": signal, "entry": entry, "sl": sl, "tp": tp,
        "rsi": rsi, "atr": atr, "ema9": ema9, "ema21": ema21,
        "price": price,
    }

# ============================================================
# 5) واجهة التطبيق
# ============================================================
st.title("📈 إشارات التداول اللحظية")

# القائمة المنسدلة
choice = st.selectbox("🔽 اختر الأصل:", list(ASSETS.keys()))
symbol = ASSETS[choice]

# زر تحديث يدوي + خيار التحديث التلقائي
col1, col2 = st.columns(2)
with col1:
    refresh = st.button("🔄 تحديث الآن", use_container_width=True)
with col2:
    auto = st.checkbox("تحديث تلقائي (60ث)", value=True)

data = fetch_and_analyze(symbol)

if data is None:
    st.error("❌ تعذر جلب البيانات، تحقق من الاتصال بالإنترنت.")
    st.stop()

signal = data["signal"]

# ---- كرت الإشارة الكبير ----
colors = {"BUY": ("signal-buy", "🟢"), "SELL": ("signal-sell", "🔴"), "HOLD": ("signal-hold", "⚪")}
cls, icon = colors[signal]
st.markdown(
    f'<div class="signal-card {cls}">'
    f'<div class="signal-title">{icon} {signal}</div>'
    f'<div class="signal-sub">{choice} — فريم 5 دقائق</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ---- أرقام التداول الكبيرة والواضحة ----
def fmt(v):
    return f"{v:,.2f}"

st.markdown(
    f'<div class="price-row"><span class="price-label">💰 الدخول</span>'
    f'<span class="price-value val-ent">{fmt(data["entry"])}</span></div>'
    f'<div class="price-row"><span class="price-label">🛑 وقف الخسارة</span>'
    f'<span class="price-value val-sl">{fmt(data["sl"])}</span></div>'
    f'<div class="price-row"><span class="price-label">🎯 جني الأرباح</span>'
    f'<span class="price-value val-tp">{fmt(data["tp"])}</span></div>',
    unsafe_allow_html=True,
)

# ---- حالة المؤشرات ----
st.markdown('<div class="ind-title">📊 حالة المؤشرات (5 دقائق)</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
c1.metric("RSI (14)", f"{data['rsi']:.1f}")
c2.metric("EMA 9", fmt(data["ema9"]))
c3.metric("ATR (14)", fmt(data["atr"]))

trend_txt = "صاعد 📈" if data["ema9"] > data["ema21"] else "هابط 📉"
st.caption(f"الاتجاه: {trend_txt} | إشارة الحالية قد تتغير مع تطور الشمعة — حدّث قبل التنفيذ.")

st.markdown(
    '<div class="warn-box">⚠️ تنبيه: هذا التطبيق أداة تحليل مساعدة فقط وليس نصيحة مالية. '
    'التداول بالهامش (مارجن) ينطوي على مخاطر عالية — لا تخاطر بأكثر من 1-2% من رأس مالك في الصفقة الواحدة.</div>',
    unsafe_allow_html=True,
)

# ---- تحديث تلقائي كل 60 ثانية ----
if auto:
    time.sleep(60)
    st.rerun()
