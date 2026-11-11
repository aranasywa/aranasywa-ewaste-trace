import hashlib
import io
import sqlite3
import uuid
from datetime import datetime

import pandas as pd
import qrcode
import streamlit as st

DB = "ewaste.db"
CATEGORIES = ["Laptop", "Ponsel", "Kabel", "Baterai", "Papan sirkuit", "Aksesori", "Lainnya"]
STATUSES = ["Dikumpulkan", "Diangkut", "Diterima Pengolah", "Selesai Diolah"]
ROLES = ["Penghasil", "Pengumpul", "Pengangkut", "Pengolah", "Admin"]


# ---------- Database ----------
def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches(
                code TEXT PRIMARY KEY, category TEXT, qty INTEGER, weight_kg REAL,
                origin TEXT, notes TEXT, status TEXT, created_at TEXT, created_by TEXT);
            CREATE TABLE IF NOT EXISTS handovers(
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, from_party TEXT,
                to_party TEXT, location TEXT, status TEXT, note TEXT, ts TEXT,
                prev_hash TEXT, hash TEXT);
            """
        )


def make_hash(prev, code, frm, to, loc, status, note, ts):
    raw = "|".join([prev, code, frm, to, loc, status, note, ts])
    return hashlib.sha256(raw.encode()).hexdigest()


def add_handover(code, frm, to, loc, status, note):
    """Catatan serah terima bersifat append-only dan dirantai dengan hash."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db() as c:
        last = c.execute(
            "SELECT hash FROM handovers WHERE code=? ORDER BY id DESC LIMIT 1", (code,)
        ).fetchone()
        prev = last["hash"] if last else "GENESIS"
        h = make_hash(prev, code, frm, to, loc, status, note, ts)
        c.execute(
            "INSERT INTO handovers(code,from_party,to_party,location,status,note,ts,prev_hash,hash)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (code, frm, to, loc, status, note, ts, prev, h),
        )
        c.execute("UPDATE batches SET status=? WHERE code=?", (status, code))


def verify_chain(code):
    with db() as c:
        rows = c.execute("SELECT * FROM handovers WHERE code=? ORDER BY id", (code,)).fetchall()
    prev = "GENESIS"
    for r in rows:
        expected = make_hash(prev, r["code"], r["from_party"], r["to_party"],
                             r["location"], r["status"], r["note"], r["ts"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return False
        prev = r["hash"]
    return True


def qr_image(text):
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- AI (saran awal) ----------
def suggest_category(image_bytes, filename):
    """
    PLACEHOLDER. Ganti dengan model computer vision sungguhan
    (mis. Hugging Face image-classification / model Teachable Machine).
    Keluaran: (kategori, tingkat_keyakinan). Hanya saran awal, bukan keputusan akhir.
    """
    name = filename.lower()
    keywords = {
        "laptop": "Laptop", "hp": "Ponsel", "phone": "Ponsel", "kabel": "Kabel",
        "cable": "Kabel", "baterai": "Baterai", "battery": "Baterai",
        "pcb": "Papan sirkuit", "board": "Papan sirkuit",
    }
    for k, v in keywords.items():
        if k in name:
            return v, 0.85
    return "Lainnya", 0.40


# ---------- UI ----------
st.set_page_config(page_title="E-Waste Traceability", page_icon="♻️", layout="wide")
init_db()

st.markdown(
    """
<style>
.block-container{padding-top:2rem;max-width:1100px}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0f3d2e,#1b5e43)}
[data-testid="stSidebar"] *{color:#eafaf1 !important}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] [data-baseweb="select"] *{color:#1a1a1a !important}
.hero{background:linear-gradient(135deg,#1b5e43,#2e9e6b);padding:1.6rem 2rem;
      border-radius:16px;margin-bottom:1.5rem}
.hero h1{margin:0;font-size:1.9rem;color:#fff !important}
.hero p{margin:.3rem 0 0;color:#e6f7ee !important}
[data-testid="stMetric"]{background:#f3faf6;border:1px solid #cfe8da;
      border-radius:14px;padding:1rem}
[data-testid="stMetric"] *{color:#14532d !important}
.stButton>button,.stFormSubmitButton>button{background:#2e9e6b;color:#fff;
      border:0;border-radius:10px;padding:.5rem 1.2rem}
.stButton>button:hover,.stFormSubmitButton>button:hover{background:#25855a;color:#fff}
</style>
""",
    unsafe_allow_html=True,
)


def hero(title, subtitle):
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>',
                unsafe_allow_html=True)


def seed_demo():
    """Isi data contoh (dummy) untuk demo."""
    data = [
        ("Laptop", 12, 30.5, "Lab Komputer FT", "Gedung A, Lab 2"),
        ("Ponsel", 25, 4.2, "Fakultas Ekonomi", "Gedung B, Ruang TU"),
        ("Baterai", 40, 6.0, "UPT Teknologi Informasi", "Gudang UPT"),
        ("Kabel", 80, 15.0, "Perpustakaan Pusat", "Lantai 1"),
        ("Papan sirkuit", 15, 3.8, "Bengkel Elektronika", "Workshop"),
        ("Aksesori", 30, 5.5, "Biro Umum", "Gedung Rektorat"),
    ]
    chain = [("Diangkut", "Bank Sampah Kampus", "Pengangkut Hijau Lestari"),
             ("Diterima Pengolah", "Pengangkut Hijau Lestari", "PT Daur Ulang Contoh"),
             ("Selesai Diolah", "PT Daur Ulang Contoh", "PT Daur Ulang Contoh")]
    for i, (cat, qty, w, origin, loc) in enumerate(data):
        code = "EW-DEMO%02d" % (i + 1)
        with db() as c:
            if c.execute("SELECT 1 FROM batches WHERE code=?", (code,)).fetchone():
                continue
            c.execute("INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?)",
                      (code, cat, qty, w, origin, "Data contoh", "Dikumpulkan",
                       datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Bank Sampah Kampus"))
        add_handover(code, origin, "Bank Sampah Kampus", loc, "Dikumpulkan", "Batch dibuat")
        for status, frm, to in chain[: i % 4]:
            add_handover(code, frm, to, "Titik serah terima %d" % (i + 1), status, "Data contoh")

st.sidebar.title("♻️ E-Waste Traceability")
user = st.sidebar.text_input("Nama / instansi Anda", "Pengguna Demo")
role = st.sidebar.selectbox("Peran", ROLES)
page = st.sidebar.radio("Menu", ["Dashboard", "Input Batch", "Serah Terima", "Lacak Batch"])
st.sidebar.caption("Catatan: login di sini hanya simulasi peran untuk demo.")
if st.sidebar.button("Isi data contoh"):
    seed_demo()
    st.sidebar.success("Data contoh ditambahkan.")

# --- Dashboard ---
if page == "Dashboard":
    hero("♻️ Dashboard Limbah Elektronik", "Pantau jumlah, kategori, dan status limbah elektronik")
    with db() as c:
        df = pd.read_sql("SELECT * FROM batches", c)
    if df.empty:
        st.info("Belum ada data. Tambahkan batch di menu Input Batch.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Total batch", len(df))
        c2.metric("Total berat (kg)", round(df["weight_kg"].sum(), 1))
        c3.metric("Selesai diolah", int((df["status"] == "Selesai Diolah").sum()))
        a, b = st.columns(2)
        a.subheader("Per kategori")
        a.bar_chart(df.groupby("category")["qty"].sum())
        b.subheader("Per status")
        b.bar_chart(df["status"].value_counts())
        st.subheader("Semua batch")
        st.dataframe(df, use_container_width=True)

# --- Input batch ---
elif page == "Input Batch":
    hero("📦 Input Batch Baru", "Catat limbah elektronik dan buat kode QR pelacakan")
    if role not in ("Penghasil", "Pengumpul", "Admin"):
        st.warning("Hanya Penghasil, Pengumpul, atau Admin yang dapat membuat batch.")
        st.stop()

    photo = st.file_uploader("Foto limbah (opsional, untuk saran kategori AI)", type=["jpg", "jpeg", "png"])
    default_idx = 0
    if photo:
        label, conf = suggest_category(photo.getvalue(), photo.name)
        st.image(photo, width=250)
        st.info(f"Saran AI: **{label}** (keyakinan {conf:.0%}). Ini hanya identifikasi awal dari tampilan visual.")
        if conf < 0.7:
            st.warning("Keyakinan rendah: wajib ditinjau dan dipilih ulang oleh petugas.")
        default_idx = CATEGORIES.index(label)

    with st.form("batch"):
        category = st.selectbox("Kategori (konfirmasi petugas)", CATEGORIES, index=default_idx)
        qty = st.number_input("Jumlah unit", min_value=1, value=1)
        weight = st.number_input("Perkiraan berat (kg)", min_value=0.0, value=1.0)
        origin = st.text_input("Asal / penghasil")
        location = st.text_input("Lokasi pengumpulan")
        notes = st.text_area("Catatan")
        ok = st.form_submit_button("Simpan batch")

    if ok:
        if not origin or not location:
            st.error("Asal dan lokasi wajib diisi.")
        else:
            code = "EW-" + uuid.uuid4().hex[:8].upper()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with db() as c:
                c.execute(
                    "INSERT INTO batches VALUES (?,?,?,?,?,?,?,?,?)",
                    (code, category, qty, weight, origin, notes, "Dikumpulkan", now, user),
                )
            add_handover(code, origin, user, location, "Dikumpulkan", "Batch dibuat")
            st.success(f"Batch tersimpan dengan kode {code}")
            st.image(qr_image(code), width=180, caption=code)
            st.warning("Baterai rusak/menggembung/bocor jangan dibongkar sendiri; serahkan ke pihak kompeten.")

# --- Serah terima ---
elif page == "Serah Terima":
    hero("🤝 Catat Serah Terima", "Rekam perpindahan batch antar pihak, lengkap dengan lokasi dan waktu")
    with db() as c:
        codes = [r["code"] for r in c.execute("SELECT code FROM batches ORDER BY created_at DESC")]
    if not codes:
        st.info("Belum ada batch.")
        st.stop()
    with st.form("handover"):
        code = st.selectbox("Kode batch", codes)
        frm = st.text_input("Dari (pihak penyerah)", user)
        to = st.text_input("Kepada (pihak penerima)")
        loc = st.text_input("Lokasi serah terima")
        status = st.selectbox("Status baru", STATUSES)
        note = st.text_area("Catatan")
        ok = st.form_submit_button("Catat")
    if ok:
        if not to or not loc:
            st.error("Penerima dan lokasi wajib diisi.")
        else:
            add_handover(code, frm, to, loc, status, note)
            st.success("Serah terima tercatat.")

# --- Lacak ---
elif page == "Lacak Batch":
    hero("🔎 Lacak Batch", "Telusuri perjalanan limbah dari penghasil sampai pengolah")
    code = st.text_input("Masukkan kode batch (mis. EW-1A2B3C4D)").strip().upper()
    if code:
        with db() as c:
            b = c.execute("SELECT * FROM batches WHERE code=?", (code,)).fetchone()
            hs = pd.read_sql("SELECT from_party,to_party,location,status,note,ts FROM handovers "
                             "WHERE code=? ORDER BY id", c, params=(code,))
        if not b:
            st.error("Kode tidak ditemukan.")
        else:
            st.subheader(f"{b['category']} • {b['qty']} unit • {b['weight_kg']} kg")
            st.write(f"Asal: **{b['origin']}** | Status saat ini: **{b['status']}**")
            if verify_chain(code):
                st.success("Integritas riwayat terverifikasi (rantai hash utuh).")
            else:
                st.error("Riwayat tidak konsisten! Kemungkinan data diubah.")
            st.image(qr_image(code), width=150)
            st.subheader("Timeline perjalanan")
            st.dataframe(hs, use_container_width=True)
