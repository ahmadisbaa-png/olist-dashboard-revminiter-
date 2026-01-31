import pandas as pd
import streamlit as st
import plotly.express as px
import folium
from streamlit_folium import st_folium
from pathlib import Path

st.set_page_config(page_title="Olist Dashboard", layout="wide")

@st.cache_data
def load_data(path: Path):
    return pd.read_csv(path, parse_dates=["order_purchase_timestamp"])

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR
DATA_PATH = DATA_DIR / "main_data.csv"

if not DATA_PATH.exists():
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    if not csv_files:
        st.error(f"Tidak ada file .csv di folder: {DATA_DIR}")
        st.stop()
    DATA_PATH = csv_files[0]

st.caption(f"Memakai data: {DATA_PATH.name}")

df = load_data(DATA_PATH)

def create_rfm_segment_df(df):
    seg = (df.groupby("rfm_segment")["customer_unique_id"]
           .nunique()
           .reset_index(name="customers")
           .sort_values("customers", ascending=False))
    return seg

def create_rfm_revenue_df(df):
    seg_rev = (df.groupby("rfm_segment")["order_revenue"]
               .sum()
               .reset_index(name="total_revenue")
               .sort_values("total_revenue", ascending=False))
    return seg_rev

# ✅ NEW: avg revenue per customer per segment
def create_avg_rev_per_customer_df(df):
    avg_df = (df.groupby("rfm_segment")
              .agg(
                  customers=("customer_unique_id", "nunique"),
                  total_revenue=("order_revenue", "sum")
              )
              .reset_index())
    avg_df["avg_revenue_per_customer"] = (
        avg_df["total_revenue"] / avg_df["customers"].replace(0, pd.NA)
    )
    avg_df = avg_df.sort_values("avg_revenue_per_customer", ascending=False)
    return avg_df

def create_state_perf_df(df):
    state_perf = (df.groupby("customer_state")
                  .agg(total_orders=("order_id","nunique"),
                       total_revenue=("order_revenue","sum"))
                  .reset_index()
                  .sort_values("total_revenue", ascending=False))
    return state_perf

# --- Title ---
st.title("📦 Olist Brazilian E-Commerce Dashboard")
st.caption("Menjawab 2 pertanyaan: Segmentasi RFM & performa penjualan per state.")

# --- Sidebar filter ---
st.sidebar.header("Filter")

min_date = df["order_purchase_timestamp"].min().date()
max_date = df["order_purchase_timestamp"].max().date()

start_date, end_date = st.sidebar.date_input(
    "Rentang Tanggal",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

state_opt = ["(All)"] + sorted(df["customer_state"].dropna().unique().tolist())
state = st.sidebar.selectbox("State", state_opt)

seg_opt = ["(All)"] + sorted(df["rfm_segment"].dropna().unique().tolist())
seg = st.sidebar.selectbox("RFM Segment", seg_opt)

# Filter main df
df_f = df[(df["order_purchase_timestamp"].dt.date >= start_date) &
          (df["order_purchase_timestamp"].dt.date <= end_date)]

if state != "(All)":
    df_f = df_f[df_f["customer_state"] == state]
if seg != "(All)":
    df_f = df_f[df_f["rfm_segment"] == seg]

# --- KPI ---
col1, col2, col3, col4 = st.columns(4)
total_revenue = df_f["order_revenue"].sum()
total_orders = df_f["order_id"].nunique()
total_customers = df_f["customer_unique_id"].nunique()
aov = total_revenue / total_orders if total_orders else 0

col1.metric("Total Revenue", f"R$ {total_revenue:,.0f}")
col2.metric("Total Orders", f"{total_orders:,.0f}")
col3.metric("Total Customers", f"{total_customers:,.0f}")
col4.metric("AOV", f"R$ {aov:,.2f}")

st.divider()

# --- Pertanyaan 1: RFM ---
st.subheader("1) RFM Analysis — Segmentasi Pelanggan")

# ✅ jadi 3 kolom: total revenue, jumlah customer, avg revenue/customer
c1, c2, c3 = st.columns(3)

with c1:
    seg_rev_df = create_rfm_revenue_df(df_f)
    fig = px.bar(
        seg_rev_df, x="rfm_segment", y="total_revenue",
        labels={"rfm_segment":"Segment", "total_revenue":"Revenue (R$)"},
        title="Total Revenue per RFM Segment"
    )
    st.plotly_chart(fig, use_container_width=True)

with c2:
    seg_cnt_df = create_rfm_segment_df(df_f)
    fig2 = px.bar(
        seg_cnt_df, x="rfm_segment", y="customers",
        labels={"rfm_segment":"Segment", "customers":"Customers"},
        title="Jumlah Customer per RFM Segment"
    )
    st.plotly_chart(fig2, use_container_width=True)

with c3:
    avg_rev_df = create_avg_rev_per_customer_df(df_f)
    fig3a = px.bar(
        avg_rev_df, x="rfm_segment", y="avg_revenue_per_customer",
        labels={"rfm_segment":"Segment", "avg_revenue_per_customer":"Avg Revenue/Customer (R$)"},
        title="Avg Revenue per Customer per Segment"
    )
    st.plotly_chart(fig3a, use_container_width=True)

st.divider()

# --- Pertanyaan 2: State ---
st.subheader("2) Geospatial (State) — Top Orders & Revenue")

state_perf = create_state_perf_df(df_f)

c4, c5 = st.columns(2)
with c4:
    fig4 = px.bar(
        state_perf.head(10), x="customer_state", y="total_revenue",
        title="Top 10 State by Revenue",
        labels={"customer_state":"State", "total_revenue":"Revenue (R$)"}
    )
    st.plotly_chart(fig4, use_container_width=True)

with c5:
    fig5 = px.bar(
        state_perf.sort_values("total_orders", ascending=False).head(10),
        x="customer_state", y="total_orders",
        title="Top 10 State by Orders",
        labels={"customer_state":"State", "total_orders":"Orders"}
    )
    st.plotly_chart(fig5, use_container_width=True)

# --- Optional map ---
st.subheader("Peta Sebaran Customer (Sample)")
if {"geolocation_lat","geolocation_lng"}.issubset(df_f.columns) and df_f[["geolocation_lat","geolocation_lng"]].dropna().shape[0] > 0:
    df_map = df_f.dropna(subset=["geolocation_lat","geolocation_lng"]).copy()
    if len(df_map) > 3000:
        df_map = df_map.sample(3000, random_state=42)

    center = [df_map["geolocation_lat"].mean(), df_map["geolocation_lng"].mean()]
    m = folium.Map(location=center, zoom_start=4, tiles="CartoDB positron")
    for _, r in df_map.iterrows():
        folium.CircleMarker(
            location=[r["geolocation_lat"], r["geolocation_lng"]],
            radius=2, fill=True, fill_opacity=0.4, weight=0
        ).add_to(m)
    st_folium(m, height=520)
else:
    st.info("Kolom geolocation_lat/lng tidak ada atau data kosong. Jalankan proses join geolocation di notebook.")