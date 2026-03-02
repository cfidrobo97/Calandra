import io
from datetime import date, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Control Semanal - Calandra", layout="wide")

st.title("🧾 Control semanal (Horas + Pedidos)")

# --- Sidebar config ---
st.sidebar.header("⚙️ Configuración")
pago_hora = st.sidebar.number_input("Pago por hora ($/hora)", min_value=0.0, value=2.50, step=0.10, format="%.2f")
tarifa_grande = st.sidebar.number_input("Tarifa Rollo Grande ($/metro)", min_value=0.0, value=0.65, step=0.01, format="%.2f")
tarifa_pequeno = st.sidebar.number_input("Tarifa Rollo Pequeño ($/metro)", min_value=0.0, value=0.55, step=0.01, format="%.2f")
dias_semana = st.sidebar.selectbox("Días de la semana", options=[5, 6, 7], index=0)
inicio = st.sidebar.date_input("Semana desde", value=date.today())
fin = inicio + timedelta(days=dias_semana - 1)
st.sidebar.caption(f"Hasta: **{fin.strftime('%d/%m/%Y')}**")

# --- Helpers ---
TIPOS = ["Calandra", "Bryan", "Jose", "Klever"]
ESTADO_HORAS = ["Pagado", "Pendiente", "Debe"]
ROLLOS = ["Pequeño", "Grande", "Especial"]
ESTADO_PED = ["Pagado", "Pendiente"]

def calc_horas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # convert times safely
    def to_minutes(x):
        if pd.isna(x) or x == "":
            return None
        if isinstance(x, str):
            try:
                h, m = x.split(":")
                return int(h) * 60 + int(m)
            except Exception:
                return None
        if hasattr(x, "hour"):
            return x.hour * 60 + x.minute
        return None

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
    df["Total dinero"] = df["Total horas"].apply(lambda h: None if h is None else round(h * pago_hora, 2))
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
            if pd.isna(precio_esp) or precio_esp == "" or precio_esp == 0:
                totales.append(None)
            else:
                totales.append(float(precio_esp))
        elif rollo == "Grande" and metros is not None:
            totales.append(round(float(metros) * tarifa_grande, 2))
        elif rollo == "Pequeño" and metros is not None:
            totales.append(round(float(metros) * tarifa_pequeno, 2))
        else:
            totales.append(None)
    df["Total ($)"] = totales
    return df

def default_horas():
    return pd.DataFrame([{
        "Fecha": inicio,
        "Tipo": "",
        "Hora inicio": "",
        "Hora fin": "",
        "Total horas": None,
        "Total dinero": None,
        "Estado": ""
    } for _ in range(10)])

def default_pedidos():
    return pd.DataFrame([{
        "Fecha": inicio,
        "Cliente": "",
        "Total metros": None,
        "Rollo": "",
        "Precio especial ($)": None,
        "Total ($)": None,
        "Estado": ""
    } for _ in range(10)])

if "horas" not in st.session_state:
    st.session_state.horas = default_horas()
if "pedidos" not in st.session_state:
    st.session_state.pedidos = default_pedidos()

col1, col2 = st.columns(2)

with col1:
    st.subheader("⏱️ HORAS")
    horas_edit = st.data_editor(
        st.session_state.horas,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Tipo": st.column_config.SelectboxColumn(options=TIPOS),
            "Hora inicio": st.column_config.TextColumn(help="Formato recomendado: HH:MM (ej 08:30)"),
            "Hora fin": st.column_config.TextColumn(help="Formato recomendado: HH:MM (ej 17:45)"),
            "Total horas": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "Total dinero": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
            "Estado": st.column_config.SelectboxColumn(options=ESTADO_HORAS),
        },
        key="horas_editor",
    )
    horas_calc = calc_horas(horas_edit)

with col2:
    st.subheader("🧵 PEDIDOS")
    pedidos_edit = st.data_editor(
        st.session_state.pedidos,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "Fecha": st.column_config.DateColumn(format="DD/MM/YYYY"),
            "Cliente": st.column_config.TextColumn(),
            "Total metros": st.column_config.NumberColumn(format="%.2f"),
            "Rollo": st.column_config.SelectboxColumn(options=ROLLOS),
            "Precio especial ($)": st.column_config.NumberColumn(format="$%.2f", help="Solo si Rollo=Especial (es el TOTAL manual)."),
            "Total ($)": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
            "Estado": st.column_config.SelectboxColumn(options=ESTADO_PED),
        },
        key="pedidos_editor",
    )
    pedidos_calc = calc_pedidos(pedidos_edit)

# save back
st.session_state.horas = horas_calc
st.session_state.pedidos = pedidos_calc

st.divider()

# --- Summary ---
ventas_total = pd.to_numeric(pedidos_calc["Total ($)"], errors="coerce").fillna(0).sum()
metros_total = pd.to_numeric(pedidos_calc["Total metros"], errors="coerce").fillna(0).sum()

def pago_tipo(tipo):
    s = horas_calc.loc[horas_calc["Tipo"] == tipo, "Total dinero"]
    return pd.to_numeric(s, errors="coerce").fillna(0).sum()

p_bryan = pago_tipo("Bryan")
p_jose = pago_tipo("Jose")
p_klever = pago_tipo("Klever")
p_total = p_bryan + p_jose + p_klever

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total metros", f"{metros_total:.2f}")
c2.metric("Total ventas", f"${ventas_total:,.2f}")
c3.metric("Pagos empleados", f"${p_total:,.2f}")
c4.metric("Mi total (ventas - Bryan)", f"${(ventas_total - p_bryan):,.2f}")
c5.metric("Neto (ventas - todos)", f"${(ventas_total - p_total):,.2f}")

# --- Export ---
st.subheader("📤 Exportar")
st.caption("Exporta a Excel con 2 hojas (Horas y Pedidos) + Resumen.")

def build_excel_bytes() -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        horas_calc.to_excel(writer, index=False, sheet_name="HORAS")
        pedidos_calc.to_excel(writer, index=False, sheet_name="PEDIDOS")
        resumen = pd.DataFrame({
            "Concepto": [
                "Semana desde", "Semana hasta",
                "Total metros", "Total ventas",
                "Pago Bryan", "Pago Jose", "Pago Klever",
                "Pago total empleados",
                "Mi total (ventas - Bryan)",
                "Neto (ventas - todos)",
            ],
            "Valor": [
                inicio.strftime("%d/%m/%Y"), fin.strftime("%d/%m/%Y"),
                round(metros_total, 2), round(ventas_total, 2),
                round(p_bryan, 2), round(p_jose, 2), round(p_klever, 2),
                round(p_total, 2),
                round(ventas_total - p_bryan, 2),
                round(ventas_total - p_total, 2),
            ]
        })
        resumen.to_excel(writer, index=False, sheet_name="RESUMEN")
    return output.getvalue()

excel_bytes = build_excel_bytes()
st.download_button(
    "⬇️ Descargar Excel",
    data=excel_bytes,
    file_name=f"Control_Semanal_{inicio.strftime('%Y-%m-%d')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

st.caption("Si deseas que la app recuerde datos entre sesiones (base de datos) se puede agregar SQLite.")
