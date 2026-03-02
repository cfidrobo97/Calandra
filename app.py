import io
import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from github import Github

# ---------------- GitHub upload ----------------
def upload_to_github(excel_bytes: bytes, filename: str) -> str:
    try:
        # 1. Obtener credenciales de los secrets
        token = st.secrets["github"]["token"]
        repo_name = st.secrets["github"]["repo"]
        branch = st.secrets["github"]["branch"]

        g = Github(token)
        repo = g.get_repo(repo_name)

        # Ruta donde se guardará dentro del repositorio (ej: reportes/2026/marzo/archivo.xlsx)
        path = f"reportes/2026/marzo/{filename}"

        # Intentar ver si el archivo ya existe para actualizarlo o crear uno nuevo
        try:
            contents = repo.get_contents(path, ref=branch)
            repo.update_file(contents.path, f"Actualizar {filename}", excel_bytes, contents.sha, branch=branch)
        except Exception:
            repo.create_file(path, f"Crear {filename}", excel_bytes, branch=branch)

        # Generar link al archivo
        file_url = f"https://github.com/{repo_name}/blob/{branch}/{path}"
        return file_url

    except Exception as e:
        st.error(f"❌ Error al guardar en GitHub: {e}")
        return ""


# ---------------- Page config ----------------
st.set_page_config(page_title="Control - Calandra", layout="wide")
st.title("🧾 Control (por día: Horas + Pedidos)")

# ---------------- Sidebar config ----------------
st.sidebar.header("⚙️ Configuración")
pago_hora = st.sidebar.number_input("Pago por hora ($/hora)", min_value=0.0, value=2.50, step=0.10, format="%.2f")
tarifa_grande = st.sidebar.number_input("Tarifa Rollo Grande ($/metro)", min_value=0.0, value=0.65, step=0.01, format="%.2f")
tarifa_pequeno = st.sidebar.number_input("Tarifa Rollo Pequeño ($/metro)", min_value=0.0, value=0.55, step=0.01, format="%.2f")

st.sidebar.subheader("📅 Rango de fechas")
inicio = st.sidebar.date_input("Desde", value=date.today())
fin = st.sidebar.date_input("Hasta", value=date.today())
if fin < inicio:
    st.sidebar.error("⚠️ 'Hasta' no puede ser menor que 'Desde'.")

# ---------------- Lists ----------------
TIPOS = ["Calandra", "Bryan", "Jose", "Klever"]
ESTADO_HORAS = ["Pagado", "Pendiente", "Debe"]
ROLLOS = ["Pequeño", "Grande", "Especial"]
ESTADO_PED = ["Pagado", "Pendiente"]

# ---------------- Helpers ----------------
def normalize_time_str(x) -> str | None:
    """
    Convierte entradas tipo:
    - 1700 -> 17:00
    - "1700" -> 17:00
    - "17" -> 17:00
    - "7" -> 07:00
    - "830" -> 08:30
    - "08:30" -> 08:30
    Si no puede, devuelve None.
    """
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None

    # Si viene como datetime.time
    if hasattr(x, "hour") and hasattr(x, "minute"):
        return f"{int(x.hour):02d}:{int(x.minute):02d}"

    s = str(x).strip()
    if s == "" or s.lower() in ("none", "nan"):
        return None

    # ya viene HH:MM
    if re.fullmatch(r"\d{1,2}:\d{2}", s):
        hh, mm = s.split(":")
        hh_i, mm_i = int(hh), int(mm)
        if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
            return f"{hh_i:02d}:{mm_i:02d}"
        return None

    # solo dígitos (ej 1700, 830, 17, 7)
    if re.fullmatch(r"\d{1,4}", s):
        if len(s) <= 2:
            hh_i = int(s)
            if 0 <= hh_i <= 23:
                return f"{hh_i:02d}:00"
            return None

        # 3 o 4 dígitos -> HHMM
        if len(s) == 3:
            hh_i = int(s[0])
            mm_i = int(s[1:])
        else:
            hh_i = int(s[:2])
            mm_i = int(s[2:])

        if 0 <= hh_i <= 23 and 0 <= mm_i <= 59:
            return f"{hh_i:02d}:{mm_i:02d}"
        return None

    return None


def to_minutes(x):
    s = normalize_time_str(x)
    if s is None:
        return None
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def calc_horas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Normaliza automáticamente HHMM -> HH:MM para que quede visible en la tabla
    df["Hora inicio"] = df["Hora inicio"].apply(lambda v: normalize_time_str(v) or "")
    df["Hora fin"] = df["Hora fin"].apply(lambda v: normalize_time_str(v) or "")

    mins_ini = df["Hora inicio"].apply(to_minutes)
    mins_fin = df["Hora fin"].apply(to_minutes)

    total = []
    for a, b in zip(mins_ini, mins_fin):
        if a is None or b is None:
            total.append(None)
            continue
        diff = b - a
        if diff < 0:
            diff += 24 * 60
        total.append(diff / 60.0)

    df["Total horas"] = total

    # Total dinero: SOLO empleados. Calandra SIEMPRE vacío.
    dinero = []
    for tipo, h in zip(df["Tipo"], df["Total horas"]):
        if tipo == "Calandra":
            dinero.append(None)
        elif h is None:
            dinero.append(None)
        else:
            dinero.append(round(float(h) * pago_hora, 2))
    df["Total dinero"] = dinero

    return df


def calc_pedidos(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    totales = []

    for _, r in df.iterrows():
        metros = r.get("Total metros")
        rollo = r.get("Rollo")
        precio_esp = r.get("Precio especial ($)")

        if pd.isna(metros) or metros == "":
            metros = None

        if rollo == "Especial":
            # Precio especial es $/metro (no total)
            if metros is None:
                totales.append(None)
                continue

            if pd.isna(precio_esp) or precio_esp == "" or float(precio_esp or 0) == 0:
                totales.append(None)
            else:
                totales.append(round(float(metros) * float(precio_esp), 2))

        elif rollo == "Grande" and metros is not None:
            totales.append(round(float(metros) * tarifa_grande, 2))

        elif rollo == "Pequeño" and metros is not None:
            totales.append(round(float(metros) * tarifa_pequeno, 2))

        else:
            totales.append(None)

    df["Total ($)"] = totales
    return df


def default_horas_day():
    return pd.DataFrame([
        {"Tipo": "Calandra", "Hora inicio": "", "Hora fin": "", "Total horas": None, "Total dinero": None, "Estado": ""},
        {"Tipo": "Bryan",   "Hora inicio": "", "Hora fin": "", "Total horas": None, "Total dinero": None, "Estado": ""},
        {"Tipo": "Jose",    "Hora inicio": "", "Hora fin": "", "Total horas": None, "Total dinero": None, "Estado": ""},
        {"Tipo": "Klever",  "Hora inicio": "", "Hora fin": "", "Total horas": None, "Total dinero": None, "Estado": ""},
    ])


def default_pedidos_day():
    return pd.DataFrame([{
        "Cliente": "",
        "Total metros": None,
        "Rollo": "",
        "Precio especial ($)": None,
        "Total ($)": None,
        "Estado": ""
    } for _ in range(6)])


def date_range(start: date, end: date):
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


# ---------------- State: one dict per day ----------------
if "days" not in st.session_state:
    st.session_state.days = {}

dias = date_range(inicio, fin) if fin >= inicio else [inicio]

# Inicializa días si no existen (✅ incluye comentario)
for d in dias:
    key = d.isoformat()
    if key not in st.session_state.days:
        st.session_state.days[key] = {
            "horas": calc_horas(default_horas_day()),
            "pedidos": calc_pedidos(default_pedidos_day()),
            "comentario": "",  # ✅ FIX KeyError
        }

# Selector de día
st.sidebar.subheader("📌 Día")
day_labels = [d.strftime("%a %d/%m/%Y") for d in dias]
idx = st.sidebar.radio(" ", options=list(range(len(dias))), format_func=lambda i: day_labels[i])
dia_sel = dias[idx]
dia_key = dia_sel.isoformat()

# ✅ Seguro extra para días viejos sin comentario
st.session_state.days[dia_key].setdefault("comentario", "")

st.subheader(f"📌 Día: {dia_sel.strftime('%d/%m/%Y')}")

col1, col2 = st.columns(2)

# ========= FORM PARA EVITAR RECARGA/RESET AL ESCRIBIR =========
with st.form(key=f"form_{dia_key}", clear_on_submit=False):
    with col1:
        st.markdown("### ⏱️ Horas (del día)")
        horas_edit = st.data_editor(
            st.session_state.days[dia_key]["horas"],
            width="stretch",
            num_rows="dynamic",
            column_config={
                "Tipo": st.column_config.SelectboxColumn(options=TIPOS),
                "Hora inicio": st.column_config.TextColumn(help="Puedes escribir 1700, 830, 17, 7… y se convertirá a HH:MM."),
                "Hora fin": st.column_config.TextColumn(help="Puedes escribir 1700, 830, 17, 7… y se convertirá a HH:MM."),
                "Total horas": st.column_config.NumberColumn(disabled=True, format="%.2f"),
                "Total dinero": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
                "Estado": st.column_config.SelectboxColumn(options=ESTADO_HORAS),
            },
            key=f"horas_editor_{dia_key}",
        )

    with col2:
        st.markdown("### 🧵 Pedidos (del día)")
        pedidos_edit = st.data_editor(
            st.session_state.days[dia_key]["pedidos"],
            width="stretch",
            num_rows="dynamic",
            column_config={
                "Cliente": st.column_config.TextColumn(),
                "Total metros": st.column_config.NumberColumn(format="%.2f", step=0.01, min_value=0.0),
                "Rollo": st.column_config.SelectboxColumn(options=ROLLOS),
                "Precio especial ($)": st.column_config.NumberColumn(
                    format="$%.2f", step=0.01,
                    help="Si Rollo=Especial: este valor es $/metro (ej: 0.50)."
                ),
                "Total ($)": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
                "Estado": st.column_config.SelectboxColumn(options=ESTADO_PED),
            },
            key=f"pedidos_editor_{dia_key}",
        )

    # ✅ NUEVA CAJA DE COMENTARIOS (ya no rompe)
    comentario_input = st.text_area(
        "📝 Notas / Observaciones del día",
        value=st.session_state.days[dia_key]["comentario"],
        placeholder="Escribe aquí cualquier detalle importante..."
    )

    guardar = st.form_submit_button("💾 Guardar día")

if guardar:
    st.session_state.days[dia_key]["horas"] = calc_horas(horas_edit)
    st.session_state.days[dia_key]["pedidos"] = calc_pedidos(pedidos_edit)
    st.session_state.days[dia_key]["comentario"] = comentario_input
    st.success("✅ Guardado.")

st.divider()

# ---------------- Aggregation (rango completo) ----------------
all_horas = []
all_pedidos = []
all_notes = []  # ✅ FIX: antes no existía

for d in dias:
    k = d.isoformat()

    # ✅ Seguro por si quedó guardado sin comentario
    st.session_state.days[k].setdefault("comentario", "")

    h = st.session_state.days[k]["horas"].copy()
    h.insert(0, "Fecha", d)

    p = st.session_state.days[k]["pedidos"].copy()
    p.insert(0, "Fecha", d)

    all_horas.append(h)
    all_pedidos.append(p)

    note = st.session_state.days[k].get("comentario", "")
    if note:
        all_notes.append({"Fecha": d.strftime('%d/%m/%Y'), "Nota": note})

horas_all = pd.concat(all_horas, ignore_index=True)
pedidos_all = pd.concat(all_pedidos, ignore_index=True)

ventas_total = pd.to_numeric(pedidos_all["Total ($)"], errors="coerce").fillna(0).sum()
metros_total = pd.to_numeric(pedidos_all["Total metros"], errors="coerce").fillna(0).sum()

# Ventas pendientes: SOLO pedidos cuyo Estado == "Pendiente"
ventas_pendiente = pd.to_numeric(
    pedidos_all.loc[pedidos_all["Estado"] == "Pendiente", "Total ($)"],
    errors="coerce"
).fillna(0).sum()


def pago_tipo_total(tipo: str) -> float:
    """Total histórico (pagado + pendiente + debe) del empleado."""
    s = horas_all.loc[horas_all["Tipo"] == tipo, "Total dinero"]
    return pd.to_numeric(s, errors="coerce").fillna(0).sum()


def pago_tipo_pendiente(tipo: str) -> float:
    """Solo lo que aún se debe pagar al empleado (Estado != Pagado)."""
    s = horas_all.loc[(horas_all["Tipo"] == tipo) & (horas_all["Estado"] != "Pagado"), "Total dinero"]
    return pd.to_numeric(s, errors="coerce").fillna(0).sum()


# Totales históricos por empleado
p_bryan_total = pago_tipo_total("Bryan")
p_jose_total = pago_tipo_total("Jose")
p_klever_total = pago_tipo_total("Klever")
p_total_hist = p_bryan_total + p_jose_total + p_klever_total

# Pendientes por empleado (si ya está Pagado, no aparece aquí)
p_bryan_pend = pago_tipo_pendiente("Bryan")
p_jose_pend = pago_tipo_pendiente("Jose")
p_klever_pend = pago_tipo_pendiente("Klever")
p_total_pend = p_bryan_pend + p_jose_pend + p_klever_pend

# ✅ Pago Pendiente (lo que debe pagar el cliente) MENOS lo que debo a Bryan (pendiente)
pago_pendiente_cliente = max(0.0, ventas_pendiente - p_bryan_pend)

# Neto: ventas totales (pagadas + pendientes) - pago total histórico de empleados
neto_total = ventas_total - p_total_hist

# ---------------- Totales visibles abajo ----------------
st.subheader("📊 Totales (rango seleccionado)")

t1, t2, t3, t4, t5, t6, t7, t8 = st.columns(8)

t1.metric("Total metros", f"{metros_total:.2f}")
t2.metric("Total ventas", f"${ventas_total:,.2f}")

# 👇 Solo lo pendiente por empleado
t3.metric("Bryan (pendiente)", f"${p_bryan_pend:,.2f}")
t4.metric("Jose (pendiente)", f"${p_jose_pend:,.2f}")
t5.metric("Klever (pendiente)", f"${p_klever_pend:,.2f}")

# 👇 Total histórico
t6.metric("Total empleados (histórico)", f"${p_total_hist:,.2f}")

t7.metric("Pago pendiente (T - B)", f"${pago_pendiente_cliente:,.2f}")
t8.metric("Neto (ventas - empleados)", f"${neto_total:,.2f}")

st.caption(
    "Notas:\n"
    "- 'Bryan/Jose/Klever (pendiente)' solo suma filas donde Estado != Pagado.\n"
    "- 'Total empleados (histórico)' suma TODO (Pagado + Pendiente + Debe) para que quede el registro completo.\n"
    "- 'Pago pendiente (cliente - Bryan)' = Ventas pendientes - Bryan pendiente.\n"
    "- 'Neto' = Ventas totales - Total histórico empleados."
)

# ---------------- Export ----------------
st.subheader("📤 Exportar")
st.caption("Exporta a Excel con 2 hojas (Horas + Pedidos) + Resumen del rango.")

def rebuild_aggregates():
    all_horas_local, all_pedidos_local = [], []

    for d in dias:
        k = d.isoformat()

        h = st.session_state.days[k]["horas"].copy()
        h.insert(0, "Fecha", d)

        p = st.session_state.days[k]["pedidos"].copy()
        p.insert(0, "Fecha", d)

        all_horas_local.append(h)
        all_pedidos_local.append(p)

    horas_all_local = pd.concat(all_horas_local, ignore_index=True)
    pedidos_all_local = pd.concat(all_pedidos_local, ignore_index=True)

    # Limpieza (opcional)
    horas_all_local = horas_all_local[
        (horas_all_local["Hora inicio"].astype(str).str.strip() != "") |
        (horas_all_local["Hora fin"].astype(str).str.strip() != "")
    ].copy()

    pedidos_all_local = pedidos_all_local[
        (pedidos_all_local["Cliente"].astype(str).str.strip() != "") |
        (pd.to_numeric(pedidos_all_local["Total metros"], errors="coerce").fillna(0) > 0)
    ].copy()

    return horas_all_local, pedidos_all_local


def build_excel_bytes() -> bytes:
    horas_all_export, pedidos_all_export = rebuild_aggregates()

    ventas_total_export = pd.to_numeric(pedidos_all_export["Total ($)"], errors="coerce").fillna(0).sum()
    metros_total_export = pd.to_numeric(pedidos_all_export["Total metros"], errors="coerce").fillna(0).sum()

    ventas_pendiente_export = pd.to_numeric(
        pedidos_all_export.loc[pedidos_all_export["Estado"] == "Pendiente", "Total ($)"],
        errors="coerce"
    ).fillna(0).sum()

    def pago_total_export(tipo: str) -> float:
        s = horas_all_export.loc[horas_all_export["Tipo"] == tipo, "Total dinero"]
        return pd.to_numeric(s, errors="coerce").fillna(0).sum()

    def pago_pend_export(tipo: str) -> float:
        s = horas_all_export.loc[
            (horas_all_export["Tipo"] == tipo) & (horas_all_export["Estado"] != "Pagado"),
            "Total dinero"
        ]
        return pd.to_numeric(s, errors="coerce").fillna(0).sum()

    # Históricos
    p_bryan_total_e = pago_total_export("Bryan")
    p_jose_total_e = pago_total_export("Jose")
    p_klever_total_e = pago_total_export("Klever")
    p_total_hist_e = p_bryan_total_e + p_jose_total_e + p_klever_total_e

    # Pendientes
    p_bryan_pend_e = pago_pend_export("Bryan")
    p_jose_pend_e = pago_pend_export("Jose")
    p_klever_pend_e = pago_pend_export("Klever")
    p_total_pend_e = p_bryan_pend_e + p_jose_pend_e + p_klever_pend_e

    pago_pend_cliente_e = max(0.0, ventas_pendiente_export - p_bryan_pend_e)
    neto_total_e = ventas_total_export - p_total_hist_e

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        horas_all_export.to_excel(writer, index=False, sheet_name="HORAS")
        pedidos_all_export.to_excel(writer, index=False, sheet_name="PEDIDOS")

        resumen = pd.DataFrame({
            "Concepto": [
                "Desde", "Hasta",
                "Total metros", "Total ventas",
                "Ventas pendientes",
                "Bryan pendiente", "Jose pendiente", "Klever pendiente",
                "Total empleados pendiente",
                "Total empleados histórico",
                "Pago pendiente (cliente - Bryan)",
                "Neto (ventas - empleados)",
            ],
            "Valor": [
                inicio.strftime("%d/%m/%Y"), fin.strftime("%d/%m/%Y"),
                round(metros_total_export, 2), round(ventas_total_export, 2),
                round(ventas_pendiente_export, 2),
                round(p_bryan_pend_e, 2), round(p_jose_pend_e, 2), round(p_klever_pend_e, 2),
                round(p_total_pend_e, 2),
                round(p_total_hist_e, 2),
                round(pago_pend_cliente_e, 2),
                round(neto_total_e, 2),
            ]
        })
        resumen.to_excel(writer, index=False, sheet_name="RESUMEN")

        # ✅ Agrega notas si existen
        if all_notes:
            pd.DataFrame(all_notes).to_excel(writer, index=False, sheet_name="NOTAS_DIARIAS")

    return output.getvalue()


# ✅ Generar solo cuando el usuario lo pida (NO en cada rerun)
if "excel_bytes" not in st.session_state:
    st.session_state.excel_bytes = None

col_exp1, col_exp2 = st.columns([1, 3])

with col_exp1:
    generar = st.button("🧾 Generar Excel", type="primary")

if generar:
    st.session_state.excel_bytes = build_excel_bytes()
    filename = f"Control_{inicio.strftime('%Y-%m-%d')}_a_{fin.strftime('%Y-%m-%d')}.xlsx"

    link = upload_to_github(st.session_state.excel_bytes, filename)

    if link:
        st.success("✅ Subido a GitHub")
        st.markdown(f"📁 Abrir archivo: {link}")

    st.success("✅ Excel generado. Ya puedes descargarlo.")

with col_exp2:
    if st.session_state.excel_bytes:
        st.download_button(
            "⬇️ Descargar Excel (todo el rango)",
            data=st.session_state.excel_bytes,
            file_name=f"Control_{inicio.strftime('%Y-%m-%d')}_a_{fin.strftime('%Y-%m-%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Primero presiona **Generar Excel**.")