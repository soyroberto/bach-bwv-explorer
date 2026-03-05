"""
Bach BWV Explorer v2 — Streamlit App
Author: Roberto

Full multi-dimensional analysis tool:
  • BWV Search & Record Detail with prev/next navigation
  • Interactive Charts with click-to-filter drill-down tables
  • Pivot Table with row/col/value/aggregation controls + CSV export
  • Cross Report: 2-dim + 3-dim crosstab with % view
  • Listening Tracker: progress, ratings, notes, export
"""

import json
import os
from pathlib import Path

import requests
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Bach BWV Explorer",
    page_icon="🎼",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_PATH    = Path(__file__).parent / "bach_bwv_catalog.json"
TRACKER_PATH = Path(__file__).parent / "listening_tracker.json"

CITY_COLORS = {
    "Arnstadt":   "#4e79a7",
    "Mühlhausen": "#f28e2b",
    "Weimar":     "#e15759",
    "Köthen":     "#76b7b2",
    "Leipzig":    "#59a14f",
    "Unknown":    "#bab0ac",
}

# ─────────────────────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_data() -> pd.DataFrame:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.DataFrame(raw["works"])

    def bwv_num(v):
        try:
            return float(str(v).split("/")[0].rstrip("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        except Exception:
            return float("nan")

    df["bwv_num"]  = df["bwv"].apply(bwv_num)
    df["year"]     = df["date_composed"].apply(lambda d: int(str(d)[:4]) if d else None)
    df["city"]     = df["city_composed"].fillna("Unknown")
    df["mode"]     = df["key"].apply(
        lambda k: "Minor" if k and "minor" in str(k).lower()
        else ("Major" if k and "major" in str(k).lower() else "Modal/Other")
    )
    df["duration_min"] = df["duration_seconds"].apply(
        lambda x: round(x / 60, 1) if x else None
    )
    df["instruments"] = df["instruments"].apply(
        lambda x: x if isinstance(x, list) else []
    )
    df["instrument_str"] = df["instruments"].apply(
        lambda lst: ", ".join(lst) if lst else "Unknown"
    )
    df["key_display"] = df["key"].fillna("Unknown")
    df["decade"]    = df["year"].apply(
        lambda y: f"{int(y)//10*10}s" if pd.notna(y) else "Unknown"
    )
    # Primary instrument (first in list) for pivot use
    df["primary_instrument"] = df["instruments"].apply(
        lambda lst: lst[0] if lst else "Unknown"
    )
    return df


def load_tracker() -> dict:
    if TRACKER_PATH.exists():
        with open(TRACKER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_tracker(tracker: dict):
    with open(TRACKER_PATH, "w", encoding="utf-8") as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INIT
# ─────────────────────────────────────────────────────────────────────────────

def init_state():
    defaults = {
        "tracker":          {},
        "drill_year":       None,
        "drill_city":       None,
        "drill_genre":      None,
        "drill_instrument": None,
        "drill_key":        None,
        "drill_mode":       None,
        "active_bwv":       None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────────────────────────────────────

def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    out = df.copy()
    if f.get("cities"):
        out = out[out["city"].isin(f["cities"])]
    if f.get("genres"):
        out = out[out["genre"].isin(f["genres"])]
    if f.get("modes"):
        out = out[out["mode"].isin(f["modes"])]
    if f.get("instruments"):
        sel = set(f["instruments"])
        out = out[out["instruments"].apply(lambda lst: bool(sel.intersection(set(lst))))]
    yr = f.get("year_range")
    if yr:
        out = out[out["year"].between(yr[0], yr[1], inclusive="both")]
    dur = f.get("dur_range")
    if dur:
        out = out[out["duration_min"].between(dur[0], dur[1], inclusive="both")]
    if f.get("listened_only"):
        listened = {k for k, v in st.session_state["tracker"].items() if v.get("listened")}
        out = out[out["bwv"].isin(listened)]
    if f.get("unlistened_only"):
        listened = {k for k, v in st.session_state["tracker"].items() if v.get("listened")}
        out = out[~out["bwv"].isin(listened)]
    return out


def render_sidebar(df: pd.DataFrame) -> dict:
    with st.sidebar:
        st.image(
            "https://files.manuscdn.com/user_upload_by_module/session_file/107476622/LzBrFjrcvwiRcUvd.png",
            use_container_width=True,
        )
        st.title("🎼 Bach BWV Explorer")
        st.caption("Multi-dimensional analysis · 1,117 works")
        st.markdown("---")

        f = {}

        f["cities"] = st.multiselect(
            "🏙️ City / Period",
            sorted(df["city"].unique()),
            placeholder="All cities",
        )
        f["genres"] = st.multiselect(
            "🎵 Genre",
            sorted(df["genre"].dropna().unique()),
            placeholder="All genres",
        )
        f["modes"] = st.multiselect(
            "🎹 Mode",
            sorted(df["mode"].unique()),
            placeholder="All modes",
        )

        all_inst = sorted({i for lst in df["instruments"] for i in lst})
        f["instruments"] = st.multiselect(
            "🎻 Instrument",
            all_inst,
            placeholder="All instruments",
        )

        y_min, y_max = int(df["year"].min()), int(df["year"].max())
        yr = st.slider("📅 Year", y_min, y_max, (y_min, y_max))
        if yr != (y_min, y_max):
            f["year_range"] = yr

        d_min = float(df["duration_min"].min())
        d_max = float(df["duration_min"].max())
        dur = st.slider("⏱️ Duration (min)", d_min, d_max, (d_min, d_max), step=0.5)
        if dur != (d_min, d_max):
            f["dur_range"] = dur

        st.markdown("---")
        c1, c2 = st.columns(2)
        if c1.checkbox("✅ Listened"):
            f["listened_only"] = True
        if c2.checkbox("🔲 Not yet"):
            f["unlistened_only"] = True

        if st.button("🔄 Reset All", use_container_width=True):
            for key in ["drill_year","drill_city","drill_genre",
                        "drill_instrument","drill_key","drill_mode","active_bwv"]:
                st.session_state[key] = None
            st.rerun()

        # Active drill-down indicator
        drills = {k: v for k, v in {
            "Year":       st.session_state.drill_year,
            "City":       st.session_state.drill_city,
            "Genre":      st.session_state.drill_genre,
            "Instrument": st.session_state.drill_instrument,
            "Key":        st.session_state.drill_key,
            "Mode":       st.session_state.drill_mode,
        }.items() if v}
        if drills:
            st.markdown("---")
            st.markdown("**🔍 Active drill-down:**")
            for dim, val in drills.items():
                st.markdown(f"- **{dim}:** `{val}`")
            if st.button("❌ Clear drill-downs"):
                for key in ["drill_year","drill_city","drill_genre",
                            "drill_instrument","drill_key","drill_mode"]:
                    st.session_state[key] = None
                st.rerun()

    return {k: v for k, v in f.items() if v}


def apply_drilldown(df: pd.DataFrame) -> pd.DataFrame:
    """Apply any active chart drill-down selections on top of sidebar filters."""
    out = df.copy()
    if st.session_state.drill_year:
        out = out[out["year"] == st.session_state.drill_year]
    if st.session_state.drill_city:
        out = out[out["city"] == st.session_state.drill_city]
    if st.session_state.drill_genre:
        out = out[out["genre"] == st.session_state.drill_genre]
    if st.session_state.drill_instrument:
        out = out[out["instruments"].apply(
            lambda lst: st.session_state.drill_instrument in lst
        )]
    if st.session_state.drill_key:
        out = out[out["key_display"] == st.session_state.drill_key]
    if st.session_state.drill_mode:
        out = out[out["mode"] == st.session_state.drill_mode]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SHARED DRILL TABLE
# ─────────────────────────────────────────────────────────────────────────────

_drill_table_counter = [0]

def drill_table(df: pd.DataFrame, title: str = ""):
    tracker = st.session_state["tracker"]
    listened = {k for k, v in tracker.items() if v.get("listened")}
    d = df.copy()
    d["🎧"] = d["bwv"].apply(lambda b: "✅" if b in listened else "")
    d["⭐"] = d["bwv"].apply(
        lambda b: "⭐" * tracker.get(b, {}).get("rating", 0)
        if tracker.get(b, {}).get("rating", 0) > 0 else ""
    )
    cols = ["🎧", "⭐", "bwv", "title", "genre", "key_display",
            "date_composed", "city", "duration_min", "instrument_str"]
    rename = {
        "bwv": "BWV", "title": "Title", "genre": "Genre",
        "key_display": "Key", "date_composed": "Date",
        "city": "City", "duration_min": "Dur(min)",
        "instrument_str": "Instruments",
    }
    show = d[cols].rename(columns=rename).sort_values("BWV")
    if title:
        st.markdown(f"**{title} — {len(show)} works**")
    st.dataframe(
        show, use_container_width=True, height=320, hide_index=True,
        column_config={
            "BWV":      st.column_config.TextColumn("BWV", width="small"),
            "🎧":       st.column_config.TextColumn("🎧", width="small"),
            "⭐":       st.column_config.TextColumn("⭐", width="small"),
            "Dur(min)": st.column_config.NumberColumn("Dur(min)", format="%.1f"),
        },
    )
    # CSV download
    csv = show.to_csv(index=False)
    _drill_table_counter[0] += 1
    st.download_button("📥 Download as CSV", csv, "bwv_selection.csv", "text/csv",
                       key=f"dl_drill_{_drill_table_counter[0]}_{len(df)}",
                       use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# APPLE MUSIC / ITUNES PREVIEW HELPER
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _itunes_preview(bwv: str, title: str) -> dict:
    """Search iTunes API for a Bach BWV preview. Returns dict with preview info."""
    queries = [
        f"Bach BWV {bwv}",
        f"Johann Sebastian Bach {title}",
        f"Bach {title}",
    ]
    try:
        for q in queries:
            resp = requests.get(
                "https://itunes.apple.com/search",
                params={"term": q, "media": "music", "entity": "song",
                        "limit": 5, "country": "US"},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            tracks = resp.json().get("results", [])
            for t in tracks:
                name_pool = (
                    t.get("artistName", "") +
                    t.get("collectionName", "") +
                    t.get("trackName", "")
                ).lower()
                if t.get("previewUrl") and "bach" in name_pool:
                    art = t.get("artworkUrl100", "").replace("100x100bb", "300x300bb")
                    return {
                        "found": True,
                        "trackName": t.get("trackName", ""),
                        "artistName": t.get("artistName", ""),
                        "collectionName": t.get("collectionName", ""),
                        "artworkUrl": art,
                        "previewUrl": t.get("previewUrl", ""),
                        "trackViewUrl": t.get("trackViewUrl", ""),
                    }
    except Exception:
        pass
    return {"found": False}


def _render_apple_preview(bwv: str, title: str):
    """Render the Apple Music preview block inside the record card."""
    st.markdown("---")
    st.markdown("**🎵 Apple Music Preview**")

    with st.spinner("Searching Apple Music…"):
        info = _itunes_preview(bwv, title)

    if not info["found"]:
        st.caption("🚫 No preview found on Apple Music for this work.")
        return

    col_art, col_info = st.columns([1, 3])
    with col_art:
        if info["artworkUrl"]:
            st.image(info["artworkUrl"], width=110)
    with col_info:
        st.markdown(f"**{info['trackName']}**")
        st.caption(f"🎤 {info['artistName']}")
        st.caption(f"💿 {info['collectionName']}")
        if info.get("trackViewUrl"):
            st.markdown(
                f"[Open in Apple Music ↗]({info['trackViewUrl']})",
                unsafe_allow_html=False,
            )

    # Native Streamlit audio player (30-sec preview)
    st.audio(info["previewUrl"], format="audio/mp4")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — BWV SEARCH & RECORD DETAIL
# ─────────────────────────────────────────────────────────────────────────────

def tab_search(df: pd.DataFrame):
    st.markdown("## 🔍 BWV Search & Record Detail")
    st.markdown(
        "Search by BWV number, title, instrument, city, key, or any keyword. "
        "Click a row to open the full record card."
    )

    sc1, sc2, sc3 = st.columns([3, 1, 1])
    search = sc1.text_input("Search (BWV number, title, instrument, city, key…)", "")
    search_field = sc2.selectbox("Search in", ["All fields", "BWV", "Title", "Genre",
                                               "City", "Instrument", "Key"])
    sort_col = sc3.selectbox("Sort by", ["BWV", "Title", "Year", "Duration", "City", "Genre"])

    sort_map = {"BWV": "bwv_num", "Title": "title", "Year": "year",
                "Duration": "duration_min", "City": "city", "Genre": "genre"}

    result = df.copy()
    if search:
        s = search.strip().lower()
        if search_field == "All fields":
            mask = (
                result["bwv"].astype(str).str.lower().str.contains(s, na=False) |
                result["title"].astype(str).str.lower().str.contains(s, na=False) |
                result["genre"].astype(str).str.lower().str.contains(s, na=False) |
                result["city"].astype(str).str.lower().str.contains(s, na=False) |
                result["instrument_str"].astype(str).str.lower().str.contains(s, na=False) |
                result["key_display"].astype(str).str.lower().str.contains(s, na=False)
            )
        elif search_field == "BWV":
            mask = result["bwv"].astype(str).str.lower().str.contains(s, na=False)
        elif search_field == "Title":
            mask = result["title"].astype(str).str.lower().str.contains(s, na=False)
        elif search_field == "Genre":
            mask = result["genre"].astype(str).str.lower().str.contains(s, na=False)
        elif search_field == "City":
            mask = result["city"].astype(str).str.lower().str.contains(s, na=False)
        elif search_field == "Instrument":
            mask = result["instrument_str"].astype(str).str.lower().str.contains(s, na=False)
        elif search_field == "Key":
            mask = result["key_display"].astype(str).str.lower().str.contains(s, na=False)
        else:
            mask = pd.Series([True] * len(result), index=result.index)
        result = result[mask]

    result = result.sort_values(sort_map[sort_col], na_position="last")

    st.markdown(f"**{len(result)} works found**")

    # ── Stats row
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Works", len(result))
    k2.metric("Genres", result["genre"].nunique())
    k3.metric("Cities", result["city"].nunique())
    k4.metric("Keys", result["key_display"].nunique())
    total_h = round(result["duration_min"].sum() / 60, 1) if result["duration_min"].notna().any() else 0
    k5.metric("Total Duration", f"{total_h}h")

    # ── Results table
    tracker = st.session_state["tracker"]
    listened = {k for k, v in tracker.items() if v.get("listened")}
    disp = result.copy()
    disp["🎧"] = disp["bwv"].apply(lambda b: "✅" if b in listened else "")
    disp["⭐"] = disp["bwv"].apply(
        lambda b: "⭐" * tracker.get(b, {}).get("rating", 0)
        if tracker.get(b, {}).get("rating", 0) > 0 else ""
    )
    show_cols = ["🎧", "⭐", "bwv", "title", "genre", "key_display",
                 "date_composed", "city", "duration_min", "instrument_str"]
    rename = {
        "bwv": "BWV", "title": "Title", "genre": "Genre",
        "key_display": "Key", "date_composed": "Date",
        "city": "City", "duration_min": "Dur(min)",
        "instrument_str": "Instruments",
    }
    show = disp[show_cols].rename(columns=rename)

    st.dataframe(
        show, use_container_width=True, height=360, hide_index=True,
        column_config={
            "BWV":      st.column_config.TextColumn("BWV", width="small"),
            "🎧":       st.column_config.TextColumn("🎧", width="small"),
            "⭐":       st.column_config.TextColumn("⭐", width="small"),
            "Dur(min)": st.column_config.NumberColumn("Dur(min)", format="%.1f"),
        },
    )

    csv = show.to_csv(index=False)
    st.download_button("📥 Download results as CSV", csv, "bwv_search.csv", "text/csv",
                       key=f"dl_search_{len(result)}")

    # ── Record Detail Card
    st.markdown("---")
    st.markdown("### 📖 Record Detail")
    bwv_list = result["bwv"].tolist()

    # Allow setting active BWV from session state (set by chart clicks)
    default_idx = 0
    if st.session_state.active_bwv and st.session_state.active_bwv in bwv_list:
        default_idx = bwv_list.index(st.session_state.active_bwv)

    if not bwv_list:
        st.info("No works match the current search.")
        return

    sel = st.selectbox(
        "Select BWV to view full record",
        options=bwv_list,
        index=default_idx,
        format_func=lambda b: f"BWV {b} — {df[df['bwv']==b]['title'].values[0] if b in df['bwv'].values else ''}",
    )

    # Prev / Next navigation
    idx = bwv_list.index(sel)
    nav1, nav2, nav3 = st.columns([1, 6, 1])
    if nav1.button("⬅️ Prev") and idx > 0:
        st.session_state.active_bwv = bwv_list[idx - 1]
        st.rerun()
    if nav3.button("Next ➡️") and idx < len(bwv_list) - 1:
        st.session_state.active_bwv = bwv_list[idx + 1]
        st.rerun()

    row = df[df["bwv"] == sel].iloc[0]
    _render_record_card(row, tracker)


def _render_record_card(row, tracker):
    bwv = row["bwv"]
    is_listened = tracker.get(bwv, {}).get("listened", False)
    rating      = tracker.get(bwv, {}).get("rating", 0)
    notes_saved = tracker.get(bwv, {}).get("notes", "")

    # Header
    st.markdown(f"## BWV {bwv} — {row['title']}")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Composition Details**")
        st.markdown(f"- **Genre:** {row.get('genre','—')}")
        st.markdown(f"- **Key:** {row.get('key_display','—')}")
        st.markdown(f"- **Mode:** {row.get('mode','—')}")
        st.markdown(f"- **Date:** {row.get('date_composed','—')}")
        st.markdown(f"- **City:** {row.get('city','—')}")
        dur = row.get("duration_min")
        st.markdown(f"- **Duration:** {dur} min" if dur else "- **Duration:** —")

    with c2:
        st.markdown("**Instrumentation**")
        insts = row.get("instruments", [])
        if insts:
            for i in insts:
                st.markdown(f"- {i}")
        else:
            st.markdown("— unknown —")

    with c3:
        st.markdown("**Catalog Navigation**")
        prev_bwv   = row.get("preceding_bwv")
        prev_title = row.get("preceding_title", "")
        next_bwv   = row.get("following_bwv")
        next_title = row.get("following_title", "")
        if prev_bwv:
            st.markdown(f"⬅️ **BWV {prev_bwv}**")
            st.caption(prev_title)
        if next_bwv:
            st.markdown(f"➡️ **BWV {next_bwv}**")
            st.caption(next_title)

    if row.get("notes"):
        st.info(f"📝 {row['notes']}")

    # Apple Music Preview — auto-loads when BWV is selected
    _render_apple_preview(str(bwv), str(row.get("title", "")))

    # Listening tracker inline
    st.markdown("---")
    st.markdown("**🎧 Your Listening Record**")
    tc1, tc2, tc3 = st.columns([1, 2, 3])
    new_listened = tc1.checkbox("Listened", value=is_listened, key=f"lis_{bwv}")
    new_rating   = tc2.select_slider(
        "Rating", [0,1,2,3,4,5], value=rating, key=f"rat_{bwv}",
        format_func=lambda x: "⭐"*x if x else "—"
    )
    new_notes = tc3.text_input("Notes", value=notes_saved, key=f"not_{bwv}",
                               placeholder="e.g. Heard at Carnegie Hall…")
    if st.button("💾 Save record", key=f"sav_{bwv}"):
        if bwv not in tracker:
            tracker[bwv] = {}
        tracker[bwv]["listened"] = new_listened
        tracker[bwv]["rating"]   = new_rating
        tracker[bwv]["notes"]    = new_notes
        save_tracker(tracker)
        st.session_state["tracker"] = tracker
        st.success("Saved!")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — INTERACTIVE CHARTS
# ─────────────────────────────────────────────────────────────────────────────

def tab_charts(df: pd.DataFrame):
    st.markdown("## 📊 Interactive Charts")
    st.info(
        "**Click any bar, point, or segment** to drill down — a table of matching works "
        "will appear below the chart. Use the sidebar to combine with global filters."
    )

    chart_type = st.selectbox(
        "Select chart type",
        ["Timeline (Year × City)", "Heatmap (any 2 dims)", "Scatter (Year vs Duration)",
         "Sunburst (City → Mode → Key)", "Bar Chart (any dimension)",
         "Treemap (City → Genre)", "Line (Yearly output by dimension)",
         "🎼 Life & Works — Biographical Timeline"],
    )

    st.markdown("---")

    # ── TIMELINE
    if chart_type == "Timeline (Year × City)":
        sub = df.dropna(subset=["year"]).copy()
        yearly = sub.groupby(["year", "city"]).size().reset_index(name="count")
        fig = px.bar(
            yearly, x="year", y="count", color="city",
            color_discrete_map=CITY_COLORS,
            barmode="stack",
            labels={"year": "Year", "count": "Works", "city": "City"},
            title="Works per Year — click a bar to drill down",
        )
        fig.update_layout(height=420, margin=dict(l=10,r=10,t=50,b=10),
                          legend=dict(orientation="h", y=-0.2))
        event = st.plotly_chart(fig, use_container_width=True, on_select="rerun",
                                selection_mode=["points"])
        if event and event.selection and event.selection.get("points"):
            pt = event.selection["points"][0]
            yr_val = int(pt.get("x", 0))
            city_val = pt.get("legendgroup") or pt.get("curveNumber")
            st.session_state.drill_year = yr_val
            # Try to get city from legend
            if isinstance(city_val, str):
                st.session_state.drill_city = city_val

        # Manual year selector as fallback
        st.markdown("**Or select a year manually:**")
        years_avail = sorted(sub["year"].dropna().unique().astype(int).tolist())
        sel_yr = st.selectbox("Year", ["— all —"] + years_avail,
                              index=0 if not st.session_state.drill_year
                              else (years_avail.index(st.session_state.drill_year)+1
                                    if st.session_state.drill_year in years_avail else 0))
        if sel_yr != "— all —":
            st.session_state.drill_year = int(sel_yr)
        else:
            st.session_state.drill_year = None

        drill = apply_drilldown(df)
        lbl = f"Year = {st.session_state.drill_year}" if st.session_state.drill_year else "All years"
        drill_table(drill, lbl)

    # ── HEATMAP
    elif chart_type == "Heatmap (any 2 dims)":
        DIM = {"City": "city", "Genre": "genre", "Mode": "mode",
               "Decade": "decade", "Key": "key_display",
               "Primary Instrument": "primary_instrument"}
        hc1, hc2 = st.columns(2)
        row_lbl = hc1.selectbox("Row dimension", list(DIM.keys()), index=0)
        col_lbl = hc2.selectbox("Column dimension", list(DIM.keys()), index=1)
        row_col, col_col = DIM[row_lbl], DIM[col_lbl]

        if row_col == col_col:
            st.warning("Select two different dimensions.")
            return

        pivot = pd.crosstab(df[row_col], df[col_col])
        top_r = pivot.sum(axis=1).nlargest(20).index
        top_c = pivot.sum(axis=0).nlargest(20).index
        pivot = pivot.loc[top_r, top_c]

        fig = px.imshow(
            pivot, text_auto=True, color_continuous_scale="YlOrRd",
            aspect="auto",
            labels={"x": col_lbl, "y": row_lbl, "color": "Works"},
            title=f"{row_lbl} × {col_lbl} — click a cell to drill down",
        )
        fig.update_layout(height=520, margin=dict(l=10,r=10,t=50,b=10))
        st.plotly_chart(fig, use_container_width=True)

        # Cell drill-down
        st.markdown("**Drill into a cell:**")
        dc1, dc2 = st.columns(2)
        row_vals = ["— all —"] + sorted(df[row_col].dropna().unique().tolist(), key=str)
        col_vals = ["— all —"] + sorted(df[col_col].dropna().unique().tolist(), key=str)
        sel_r = dc1.selectbox(f"Select {row_lbl}", row_vals)
        sel_c = dc2.selectbox(f"Select {col_lbl}", col_vals)

        drill = df.copy()
        if sel_r != "— all —":
            drill = drill[drill[row_col] == sel_r]
        if sel_c != "— all —":
            drill = drill[drill[col_col] == sel_c]
        drill_table(drill, f"{row_lbl}={sel_r} × {col_lbl}={sel_c}")

    # ── SCATTER
    elif chart_type == "Scatter (Year vs Duration)":
        color_by = st.selectbox("Color by", ["city", "genre", "mode", "decade"])
        color_map = CITY_COLORS if color_by == "city" else {}
        sub = df.dropna(subset=["year", "duration_min"]).copy()
        sub = sub[sub["duration_min"] > 0]
        fig = px.scatter(
            sub, x="year", y="duration_min",
            color=color_by,
            color_discrete_map=color_map,
            hover_data={"bwv": True, "title": True, "genre": True,
                        "key_display": True, "city": True,
                        "year": True, "duration_min": True},
            labels={"year": "Year", "duration_min": "Duration (min)",
                    "bwv": "BWV", "title": "Title"},
            title="Year vs Duration — hover for details, select to filter",
            opacity=0.75,
        )
        fig.update_traces(marker=dict(size=9))
        fig.update_layout(height=450, margin=dict(l=10,r=10,t=50,b=10),
                          legend=dict(orientation="h", y=-0.2))
        event = st.plotly_chart(fig, use_container_width=True, on_select="rerun",
                                selection_mode=["points"])

        selected_bwvs = []
        if event and event.selection and event.selection.get("points"):
            pts = event.selection["points"]
            selected_bwvs = [p.get("customdata", [None])[0] for p in pts if p.get("customdata")]

        if selected_bwvs:
            drill = df[df["bwv"].isin(selected_bwvs)]
            drill_table(drill, f"Selected {len(drill)} works")
        else:
            # Year range selector
            st.markdown("**Or select a year range to filter:**")
            yr_min, yr_max = int(sub["year"].min()), int(sub["year"].max())
            yr_sel = st.slider("Year range for drill-down", yr_min, yr_max, (yr_min, yr_max))
            drill = sub[(sub["year"] >= yr_sel[0]) & (sub["year"] <= yr_sel[1])]
            drill_table(drill, f"Year {yr_sel[0]}–{yr_sel[1]}")

    # ── SUNBURST
    elif chart_type == "Sunburst (City → Mode → Key)":
        path_opts = {
            "City → Mode → Key": ["city", "mode", "key_display"],
            "City → Genre":      ["city", "genre"],
            "Mode → City → Genre": ["mode", "city", "genre"],
            "Decade → City → Genre": ["decade", "city", "genre"],
        }
        path_sel = st.selectbox("Hierarchy", list(path_opts.keys()))
        path = path_opts[path_sel]
        fig = px.sunburst(
            df, path=path,
            color=path[0],
            color_discrete_map=CITY_COLORS if path[0] == "city" else {},
            title=f"{path_sel} — click to drill down",
        )
        fig.update_layout(height=520, margin=dict(l=10,r=10,t=50,b=10))
        st.plotly_chart(fig, use_container_width=True)

        # Manual drill-down
        st.markdown("**Drill down by selecting values:**")
        cols_sel = st.columns(len(path))
        filters_drill = {}
        for i, dim in enumerate(path):
            vals = ["— all —"] + sorted(df[dim].dropna().unique().tolist(), key=str)
            sel = cols_sel[i].selectbox(dim.replace("_", " ").title(), vals, key=f"sb_{dim}")
            if sel != "— all —":
                filters_drill[dim] = sel

        drill = df.copy()
        for dim, val in filters_drill.items():
            drill = drill[drill[dim] == val]
        drill_table(drill, " × ".join(f"{k}={v}" for k, v in filters_drill.items()) or "All works")

    # ── BAR CHART
    elif chart_type == "Bar Chart (any dimension)":
        bc1, bc2, bc3 = st.columns(3)
        DIM = {"City": "city", "Genre": "genre", "Mode": "mode",
               "Decade": "decade", "Key": "key_display",
               "Primary Instrument": "primary_instrument", "Year": "year"}
        x_lbl  = bc1.selectbox("X axis", list(DIM.keys()), index=0)
        clr_lbl = bc2.selectbox("Color by", ["None"] + list(DIM.keys()), index=0)
        top_n  = bc3.slider("Top N", 5, 40, 20)

        x_col = DIM[x_lbl]
        counts = df[x_col].value_counts().head(top_n).reset_index()
        counts.columns = [x_col, "count"]

        if clr_lbl != "None":
            clr_col = DIM[clr_lbl]
            agg = df.groupby([x_col, clr_col]).size().reset_index(name="count")
            top_x = counts[x_col].tolist()
            agg = agg[agg[x_col].isin(top_x)]
            fig = px.bar(agg, x=x_col, y="count", color=clr_col,
                         color_discrete_map=CITY_COLORS if clr_col == "city" else {},
                         barmode="stack",
                         labels={x_col: x_lbl, "count": "Works"},
                         title=f"{x_lbl} colored by {clr_lbl}")
        else:
            fig = px.bar(counts, x=x_col, y="count",
                         color=x_col,
                         color_discrete_map=CITY_COLORS if x_col == "city" else {},
                         labels={x_col: x_lbl, "count": "Works"},
                         title=f"Works by {x_lbl}")
        fig.update_layout(height=420, margin=dict(l=10,r=10,t=50,b=10),
                          showlegend=(clr_lbl != "None"),
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)

        # Drill-down
        st.markdown("**Click a bar — or select a value to drill down:**")
        all_vals = ["— all —"] + sorted(df[x_col].dropna().unique().tolist(), key=str)
        sel_val = st.selectbox(f"Select {x_lbl}", all_vals)
        drill = df if sel_val == "— all —" else df[df[x_col] == sel_val]
        drill_table(drill, f"{x_lbl} = {sel_val}")

    # ── TREEMAP
    elif chart_type == "Treemap (City → Genre)":
        path_opts = {
            "City → Genre":           ["city", "genre"],
            "City → Mode → Genre":    ["city", "mode", "genre"],
            "Decade → City → Genre":  ["decade", "city", "genre"],
            "Genre → City":           ["genre", "city"],
        }
        path_sel = st.selectbox("Hierarchy", list(path_opts.keys()))
        path = path_opts[path_sel]
        fig = px.treemap(
            df, path=path,
            color=path[0],
            color_discrete_map=CITY_COLORS if path[0] == "city" else {},
            title=f"{path_sel} Treemap — click to drill down",
        )
        fig.update_layout(height=520, margin=dict(l=10,r=10,t=50,b=10))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Drill down:**")
        cols_sel = st.columns(len(path))
        filters_drill = {}
        for i, dim in enumerate(path):
            vals = ["— all —"] + sorted(df[dim].dropna().unique().tolist(), key=str)
            sel = cols_sel[i].selectbox(dim.replace("_", " ").title(), vals, key=f"tm_{dim}")
            if sel != "— all —":
                filters_drill[dim] = sel

        drill = df.copy()
        for dim, val in filters_drill.items():
            drill = drill[drill[dim] == val]
        drill_table(drill, " × ".join(f"{k}={v}" for k, v in filters_drill.items()) or "All works")

    # ── LINE CHART
    elif chart_type == "Line (Yearly output by dimension)":
        DIM = {"City": "city", "Genre": "genre", "Mode": "mode",
               "Primary Instrument": "primary_instrument"}
        lc1, lc2 = st.columns(2)
        dim_lbl = lc1.selectbox("Break down by", list(DIM.keys()))
        top_n   = lc2.slider("Top N categories", 3, 15, 6)
        dim_col = DIM[dim_lbl]

        sub = df.dropna(subset=["year"]).copy()
        top_cats = sub[dim_col].value_counts().head(top_n).index.tolist()
        sub2 = sub[sub[dim_col].isin(top_cats)]
        yearly = sub2.groupby(["year", dim_col]).size().reset_index(name="count")

        fig = px.line(
            yearly, x="year", y="count", color=dim_col,
            color_discrete_map=CITY_COLORS if dim_col == "city" else {},
            markers=True,
            labels={"year": "Year", "count": "Works", dim_col: dim_lbl},
            title=f"Yearly output by {dim_lbl} (top {top_n})",
        )
        fig.update_layout(height=420, margin=dict(l=10,r=10,t=50,b=10),
                          legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Drill down by year + category:**")
        dl1, dl2 = st.columns(2)
        yr_vals = ["— all —"] + sorted(sub["year"].dropna().unique().astype(int).tolist())
        cat_vals = ["— all —"] + sorted(top_cats, key=str)
        sel_yr  = dl1.selectbox("Year", yr_vals)
        sel_cat = dl2.selectbox(dim_lbl, cat_vals)
        drill = sub.copy()
        if sel_yr != "— all —":
            drill = drill[drill["year"] == int(sel_yr)]
        if sel_cat != "— all —":
            drill = drill[drill[dim_col] == sel_cat]
        drill_table(drill, f"Year={sel_yr} × {dim_lbl}={sel_cat}")


    # ── BIOGRAPHICAL TIMELINE
    elif chart_type == "🎼 Life & Works — Biographical Timeline":
        _render_bio_timeline(df)


# ─────────────────────────────────────────────────────────────────────────────
# BIOGRAPHICAL TIMELINE HELPER
# ─────────────────────────────────────────────────────────────────────────────

def _render_bio_timeline(df: pd.DataFrame):
    """Interactive chart overlaying Bach's life events onto his compositional output."""

    import plotly.graph_objects as go

    # ── Biographical data ────────────────────────────────────────────────────
    MARRIAGES = [
        {"year": 1707.79, "label": "Marriage 1\nMaria Barbara", "short": "Marriage 1",
         "color": "#2196F3", "symbol": "💍",
         "detail": "Married Maria Barbara Bach on 17 Oct 1707 in Dornheim"},
        {"year": 1721.92, "label": "Marriage 2\nAnna Magdalena", "short": "Marriage 2",
         "color": "#9C27B0", "symbol": "💍",
         "detail": "Married Anna Magdalena Wilcke on 3 Dec 1721 in Köthen"},
    ]

    DEATHS = [
        {"year": 1720.52, "label": "Maria Barbara\ndied", "short": "Maria Barbara died",
         "color": "#E91E63", "symbol": "✝️",
         "detail": "Maria Barbara Bach died 7 Jul 1720, age 35, while Bach was away in Carlsbad"},
        {"year": 1750.58, "label": "Bach died", "short": "J.S. Bach died",
         "color": "#212121", "symbol": "✝️",
         "detail": "Johann Sebastian Bach died 28 Jul 1750, age 65, in Leipzig"},
    ]

    # All 20 children — (birth_year_decimal, name, mother, survived_to_adulthood, birth_str, death_str)
    CHILDREN = [
        # Children with Maria Barbara
        (1708.99, "1. Catharina Dorothea",    "Maria Barbara", True,  "29 Dec 1708", "14 Jan 1774"),
        (1710.89, "2. Wilhelm Friedemann",     "Maria Barbara", True,  "22 Nov 1710", "1 Jul 1784"),
        (1713.14, "3. Maria Sophia (twin)",    "Maria Barbara", False, "23 Feb 1713", "15 Mar 1713"),
        (1713.14, "4. Johann Christoph (twin)","Maria Barbara", False, "23 Feb 1713", "23 Feb 1713"),
        (1714.18, "5. Carl Philipp Emanuel",   "Maria Barbara", True,  "8 Mar 1714",  "14 Dec 1788"),
        (1715.36, "6. Johann Gottfried Bernhard","Maria Barbara",True, "11 May 1715", "27 May 1739"),
        (1718.87, "7. Leopold Augustus",       "Maria Barbara", False, "15 Nov 1718", "29 Sep 1719"),
        # Children with Anna Magdalena
        (1723.42, "8. Christiana Sophia Henrietta","Anna Magdalena",False,"Spring 1723","29 Jun 1726"),
        (1724.16, "9. Gottfried Heinrich",     "Anna Magdalena", True,  "27 Feb 1724", "12 Feb 1763"),
        (1725.28, "10. Christian Gottlieb",    "Anna Magdalena", False, "14 Apr 1725", "21 Sep 1728"),
        (1726.27, "11. Elisabeth Juliana Friderica","Anna Magdalena",True,"5 Apr 1726","24 Aug 1781"),
        (1727.83, "12. Ernestus Andreas",      "Anna Magdalena", False, "30 Oct 1727", "1 Nov 1727"),
        (1728.78, "13. Regina Johanna",        "Anna Magdalena", False, "10 Oct 1728", "25 Apr 1733"),
        (1730.01, "14. Christiana Benedicta",  "Anna Magdalena", False, "1 Jan 1730",  "4 Jan 1730"),
        (1731.21, "15. Christiana Dorothea",   "Anna Magdalena", False, "18 Mar 1731", "31 Aug 1732"),
        (1732.47, "16. Johann Christoph Friedrich","Anna Magdalena",True,"21 Jun 1732","26 Jan 1795"),
        (1733.85, "17. Johann August Abraham", "Anna Magdalena", False, "5 Nov 1733",  "6 Nov 1733"),
        (1735.68, "18. Johann Christian",      "Anna Magdalena", True,  "5 Sep 1735",  "1 Jan 1782"),
        (1737.80, "19. Johanna Carolina",      "Anna Magdalena", True,  "30 Oct 1737", "16 Aug 1781"),
        (1742.14, "20. Regina Susanna",        "Anna Magdalena", True,  "22 Feb 1742", "14 Dec 1809"),
    ]

    # ── UI controls ──────────────────────────────────────────────────────────
    st.markdown("### 🎼 Bach’s Life & Works — Biographical Timeline")
    st.markdown(
        "Overlay Bach’s key life events onto his compositional output. "
        "Hover over any marker for full details. Use the controls below to customise the view."
    )

    ctrl1, ctrl2, ctrl3 = st.columns(3)
    bg_mode = ctrl1.radio(
        "Background layer",
        ["Works per year (bar)", "Works per year (line)", "Individual BWV works (dots)", "Both (bars + dots)"],
        index=0, horizontal=False,
    )
    show_children   = ctrl2.checkbox("Show children births",   value=True)
    show_marriages  = ctrl2.checkbox("Show marriages",          value=True)
    show_deaths     = ctrl2.checkbox("Show deaths",             value=True)
    survived_only   = ctrl3.checkbox("Children: survived only", value=False)
    color_children  = ctrl3.radio("Colour children by",
                                   ["Mother (wife)", "Survived to adulthood"], index=0)

    sub = df.dropna(subset=["year"]).copy()
    sub["year"] = sub["year"].astype(int)
    yearly = sub.groupby("year").size().reset_index(name="count")

    fig = go.Figure()

    # ── Background: works per year ───────────────────────────────────────────
    if bg_mode in ("Works per year (bar)", "Both (bars + dots)"):
        fig.add_trace(go.Bar(
            x=yearly["year"], y=yearly["count"],
            name="Works / year",
            marker_color="rgba(180,180,180,0.45)",
            hovertemplate="<b>%{x}</b><br>Works composed: %{y}<extra></extra>",
        ))

    if bg_mode == "Works per year (line)":
        fig.add_trace(go.Scatter(
            x=yearly["year"], y=yearly["count"],
            mode="lines+markers",
            name="Works / year",
            line=dict(color="rgba(150,150,150,0.7)", width=2),
            marker=dict(size=5, color="rgba(150,150,150,0.7)"),
            hovertemplate="<b>%{x}</b><br>Works composed: %{y}<extra></extra>",
        ))

    if bg_mode in ("Individual BWV works (dots)", "Both (bars + dots)"):
        # Jitter y slightly so overlapping dots are visible
        import numpy as np
        dot_df = sub.copy()
        dot_df["jitter"] = np.random.default_rng(42).uniform(-0.3, 0.3, len(dot_df))
        dot_df["y_pos"] = 0.5 + dot_df["jitter"]
        fig.add_trace(go.Scatter(
            x=dot_df["year"],
            y=dot_df["y_pos"] if bg_mode == "Individual BWV works (dots)" else
              dot_df["year"].map(yearly.set_index("year")["count"]) + dot_df["jitter"] * 2,
            mode="markers",
            name="BWV works",
            marker=dict(size=6, color="#7a5c1e", opacity=0.55),
            customdata=dot_df[["bwv", "title", "genre", "key_display", "city"]].values,
            hovertemplate=(
                "<b>BWV %{customdata[0]}</b> — %{customdata[1]}<br>"
                "Genre: %{customdata[2]}<br>"
                "Key: %{customdata[3]}<br>"
                "City: %{customdata[4]}<br>"
                "Year: %{x}<extra></extra>"
            ),
        ))

    # ── Children markers ─────────────────────────────────────────────────────
    if show_children:
        children_to_show = [c for c in CHILDREN if (not survived_only or c[3])]

        # Separate by mother or survival
        if color_children == "Mother (wife)":
            groups = {
                "Maria Barbara's child": ([c for c in children_to_show if c[2] == "Maria Barbara"],
                                           "#2196F3", "circle"),
                "Anna Magdalena's child": ([c for c in children_to_show if c[2] == "Anna Magdalena"],
                                            "#9C27B0", "circle"),
            }
        else:
            groups = {
                "Survived to adulthood": ([c for c in children_to_show if c[3]],  "#4CAF50", "circle"),
                "Died in childhood":     ([c for c in children_to_show if not c[3]], "#F44336", "x"),
            }

        for grp_name, (grp_children, grp_color, grp_symbol) in groups.items():
            if not grp_children:
                continue
            # Place child markers at a fixed y position above the bars
            y_max = int(yearly["count"].max()) if len(yearly) > 0 else 20
            child_y = y_max * 1.12
            fig.add_trace(go.Scatter(
                x=[c[0] for c in grp_children],
                y=[child_y] * len(grp_children),
                mode="markers+text",
                name=grp_name,
                marker=dict(size=12, color=grp_color, symbol=grp_symbol,
                            line=dict(width=1.5, color="white")),
                text=[c[1].split(".")[0] + "." for c in grp_children],  # just the number
                textposition="top center",
                textfont=dict(size=8),
                customdata=[[c[1], c[2], c[4], c[5], "Survived" if c[3] else "Died in childhood"]
                             for c in grp_children],
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Mother: %{customdata[1]}<br>"
                    "Born: %{customdata[2]}<br>"
                    "Died: %{customdata[3]}<br>"
                    "%{customdata[4]}<extra></extra>"
                ),
            ))

    # ── Marriage vertical lines ───────────────────────────────────────────────
    if show_marriages:
        for m in MARRIAGES:
            fig.add_vline(
                x=m["year"],
                line_width=2, line_dash="dash", line_color=m["color"],
                annotation_text=m["symbol"] + " " + m["short"],
                annotation_position="top",
                annotation_font_size=10,
                annotation_font_color=m["color"],
            )

    # ── Death vertical lines ──────────────────────────────────────────────────
    if show_deaths:
        for d in DEATHS:
            fig.add_vline(
                x=d["year"],
                line_width=2.5, line_dash="dot", line_color=d["color"],
                annotation_text=d["symbol"] + " " + d["short"],
                annotation_position="top right",
                annotation_font_size=10,
                annotation_font_color=d["color"],
            )

    # ── Layout ────────────────────────────────────────────────────────────────
    y_max_val = int(yearly["count"].max()) if len(yearly) > 0 else 20
    fig.update_layout(
        title="Bach’s Life & Works — Biographical Timeline (1700–1750)",
        xaxis=dict(
            title="Year",
            range=[1699, 1752],
            tickmode="linear", dtick=5,
            showgrid=True, gridcolor="rgba(200,200,200,0.4)",
        ),
        yaxis=dict(
            title="Works composed",
            range=[0, y_max_val * 1.35],
            showgrid=True, gridcolor="rgba(200,200,200,0.4)",
        ),
        height=560,
        margin=dict(l=10, r=10, t=60, b=10),
        legend=dict(orientation="h", y=-0.18, font=dict(size=11)),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hovermode="closest",
    )

    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun",
                            selection_mode=["points"])

    # ── Legend / reference table ──────────────────────────────────────────────
    with st.expander("📚 Full children reference table", expanded=False):
        child_rows = []
        for c in CHILDREN:
            child_rows.append({
                "#": c[1].split(".")[0] + ".",
                "Name": c[1].split(". ", 1)[1] if ". " in c[1] else c[1],
                "Mother": c[2],
                "Born": c[4],
                "Died": c[5],
                "Survived to adulthood": "✅ Yes" if c[3] else "❌ No",
            })
        st.dataframe(pd.DataFrame(child_rows), use_container_width=True, hide_index=True)

    # ── Drill-down on click or year select ────────────────────────────────────
    st.markdown("---")
    st.markdown("**🔍 Select a year to see all works composed that year:**")
    years_avail = sorted(sub["year"].dropna().unique().astype(int).tolist())
    sel_yr = st.selectbox("Year", ["— all —"] + years_avail, key="bio_yr")
    if sel_yr != "— all —":
        drill = sub[sub["year"] == int(sel_yr)]
        # Also show life events in that year
        events_that_year = []
        for m in MARRIAGES:
            if int(m["year"]) == int(sel_yr):
                events_that_year.append(f"💍 {m['detail']}")
        for d in DEATHS:
            if int(d["year"]) == int(sel_yr):
                events_that_year.append(f"✝️ {d['detail']}")
        for c in CHILDREN:
            if int(c[0]) == int(sel_yr):
                survived = "survived to adulthood" if c[3] else "died in childhood"
                events_that_year.append(f"👶 {c[1]} born {c[4]}, {survived}")
        if events_that_year:
            st.info("**Life events in " + str(sel_yr) + ":**\n" + "\n".join(events_that_year))
        drill_table(drill, f"Year = {sel_yr}")
    else:
        drill_table(sub, "All works")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — PIVOT TABLE
# ─────────────────────────────────────────────────────────────────────────────

def tab_pivot(df: pd.DataFrame):
    st.markdown("## 🔀 Pivot Table")
    st.markdown(
        "Build any cross-tabulation. Choose rows, columns, the value to aggregate, "
        "and the aggregation function. Totals are included. Export as CSV."
    )

    DIM = {
        "City":              "city",
        "Genre":             "genre",
        "Mode":              "mode",
        "Decade":            "decade",
        "Key":               "key_display",
        "Primary Instrument":"primary_instrument",
        "Year":              "year",
    }
    VAL = {
        "Count of works":    ("bwv", "count"),
        "Unique BWV count":  ("bwv", "nunique"),
        "Total duration (min)": ("duration_min", "sum"),
        "Mean duration (min)":  ("duration_min", "mean"),
        "Max duration (min)":   ("duration_min", "max"),
    }

    pc1, pc2, pc3 = st.columns(3)
    row_lbl  = pc1.selectbox("Rows",       list(DIM.keys()), index=0)
    col_lbl  = pc2.selectbox("Columns",    list(DIM.keys()), index=1)
    val_lbl  = pc3.selectbox("Values",     list(VAL.keys()), index=0)

    row_col = DIM[row_lbl]
    col_col = DIM[col_lbl]
    val_col, agg_fn = VAL[val_lbl]

    if row_col == col_col:
        st.warning("Please select two different dimensions for rows and columns.")
        return

    # Build pivot
    try:
        if agg_fn == "count":
            pivot = pd.crosstab(df[row_col], df[col_col], margins=True, margins_name="TOTAL")
        else:
            pivot = pd.crosstab(
                df[row_col], df[col_col],
                values=df[val_col], aggfunc=agg_fn,
                margins=True, margins_name="TOTAL"
            ).round(1)
    except Exception as e:
        st.error(f"Could not build pivot: {e}")
        return

    # Limit columns for display
    max_cols = 30
    if len(pivot.columns) > max_cols:
        top_cols = pivot.drop("TOTAL", axis=1).sum().nlargest(max_cols - 1).index.tolist()
        pivot = pivot[top_cols + ["TOTAL"]]
        st.caption(f"Showing top {max_cols-1} columns by total count.")

    # Style
    # Use bar-based highlighting (no matplotlib dependency)
    numeric_cols = [c for c in pivot.columns if c != "TOTAL"]
    styled = pivot.style.bar(subset=numeric_cols, color="#c6dbef", axis=None)
    if agg_fn in ("sum", "mean", "max"):
        styled = styled.format("{:.1f}", na_rep="—")

    st.dataframe(styled, use_container_width=True, height=480)

    # Download
    csv = pivot.to_csv()
    st.download_button("📥 Download pivot as CSV", csv, "pivot_table.csv", "text/csv",
                       key="dl_pivot")

    # ── Drill into a cell
    st.markdown("---")
    st.markdown("**🔍 Drill into a cell — select row and column values:**")
    dc1, dc2 = st.columns(2)
    row_vals = ["— all —"] + sorted(df[row_col].dropna().unique().tolist(), key=str)
    col_vals = ["— all —"] + sorted(df[col_col].dropna().unique().tolist(), key=str)
    sel_r = dc1.selectbox(f"{row_lbl}", row_vals, key="piv_r")
    sel_c = dc2.selectbox(f"{col_lbl}", col_vals, key="piv_c")

    drill = df.copy()
    if sel_r != "— all —":
        drill = drill[drill[row_col] == sel_r]
    if sel_c != "— all —":
        drill = drill[drill[col_col] == sel_c]
    drill_table(drill, f"{row_lbl}={sel_r} × {col_lbl}={sel_c}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — CROSS REPORT
# ─────────────────────────────────────────────────────────────────────────────

def tab_cross(df: pd.DataFrame):
    st.markdown("## 📑 Cross Report — Multi-Dimensional Analysis")
    st.markdown(
        "Build 2-dimension or 3-dimension cross-tabulations. "
        "View raw counts, percentages, and drill into any combination."
    )

    DIM = {
        "City":              "city",
        "Genre":             "genre",
        "Mode":              "mode",
        "Decade":            "decade",
        "Key":               "key_display",
        "Primary Instrument":"primary_instrument",
        "Year":              "year",
    }

    mode = st.radio("Cross-tab mode", ["2 Dimensions", "3 Dimensions"], horizontal=True)

    if mode == "2 Dimensions":
        cc1, cc2 = st.columns(2)
        d1_lbl = cc1.selectbox("Dimension 1 (rows)", list(DIM.keys()), index=0, key="cr_d1")
        d2_lbl = cc2.selectbox("Dimension 2 (columns)", list(DIM.keys()), index=1, key="cr_d2")
        d1, d2 = DIM[d1_lbl], DIM[d2_lbl]

        if d1 == d2:
            st.warning("Select two different dimensions.")
            return

        cross = pd.crosstab(df[d1], df[d2], margins=True, margins_name="TOTAL")
        max_cols = 25
        if len(cross.columns) > max_cols:
            top_cols = cross.drop("TOTAL", axis=1).sum().nlargest(max_cols-1).index.tolist()
            cross = cross[top_cols + ["TOTAL"]]
            st.caption(f"Showing top {max_cols-1} columns.")

        st.markdown(f"#### Count: {d1_lbl} × {d2_lbl}")
        _nc = [c for c in cross.columns if c != "TOTAL"]
        st.dataframe(
            cross.style.bar(subset=_nc, color="#c6dbef", axis=None),
            use_container_width=True, height=400,
        )

        # Percentage view
        with st.expander("📊 Percentage view (row %)"):
            pct = cross.drop("TOTAL", axis=1).drop("TOTAL", axis=0)
            pct_row = pct.div(pct.sum(axis=1), axis=0).mul(100).round(1)
            st.dataframe(
                pct_row.style.bar(color="#c7e9c0", axis=1).format("{:.1f}%"),
                use_container_width=True, height=400,
            )

        with st.expander("📊 Percentage view (column %)"):
            pct_col = pct.div(pct.sum(axis=0), axis=1).mul(100).round(1)
            st.dataframe(
                pct_col.style.bar(color="#fdd0a2", axis=0).format("{:.1f}%"),
                use_container_width=True, height=400,
            )

        csv = cross.to_csv()
        st.download_button("📥 Download cross-tab CSV", csv, "cross_report.csv", "text/csv",
                           key="dl_cross2")

        # Drill-down
        st.markdown("---")
        st.markdown("**🔍 Drill into a cell:**")
        dr1, dr2 = st.columns(2)
        v1 = dr1.selectbox(f"{d1_lbl}", ["— all —"] + sorted(df[d1].dropna().unique().tolist(), key=str), key="cr_v1")
        v2 = dr2.selectbox(f"{d2_lbl}", ["— all —"] + sorted(df[d2].dropna().unique().tolist(), key=str), key="cr_v2")
        drill = df.copy()
        if v1 != "— all —":
            drill = drill[drill[d1] == v1]
        if v2 != "— all —":
            drill = drill[drill[d2] == v2]
        drill_table(drill, f"{d1_lbl}={v1} × {d2_lbl}={v2}")

    else:  # 3 Dimensions
        cc1, cc2, cc3 = st.columns(3)
        d1_lbl = cc1.selectbox("Dimension 1", list(DIM.keys()), index=0, key="cr3_d1")
        d2_lbl = cc2.selectbox("Dimension 2", list(DIM.keys()), index=1, key="cr3_d2")
        d3_lbl = cc3.selectbox("Dimension 3 (columns)", list(DIM.keys()), index=2, key="cr3_d3")
        d1, d2, d3 = DIM[d1_lbl], DIM[d2_lbl], DIM[d3_lbl]

        if len({d1, d2, d3}) < 3:
            st.warning("Select three different dimensions.")
            return

        try:
            cross3 = pd.crosstab([df[d1], df[d2]], df[d3])
            max_cols = 20
            if len(cross3.columns) > max_cols:
                top_cols = cross3.sum().nlargest(max_cols).index.tolist()
                cross3 = cross3[top_cols]
                st.caption(f"Showing top {max_cols} columns.")

            st.markdown(f"#### {d1_lbl} + {d2_lbl} vs {d3_lbl}")
            st.dataframe(
                cross3.style.bar(color="#c6dbef", axis=None),
                use_container_width=True, height=480,
            )

            with st.expander("📊 Row % view"):
                pct = cross3.div(cross3.sum(axis=1), axis=0).mul(100).round(1)
                st.dataframe(
                    pct.style.bar(color="#c7e9c0", axis=1).format("{:.1f}%"),
                    use_container_width=True, height=480,
                )

            csv = cross3.to_csv()
            st.download_button("📥 Download 3-dim CSV", csv, "cross3_report.csv", "text/csv",
                               key="dl_cross3")

        except Exception as e:
            st.error(f"Could not build 3-dim cross-tab: {e}")
            return

        # Drill-down
        st.markdown("---")
        st.markdown("**🔍 Drill into a combination:**")
        dr1, dr2, dr3 = st.columns(3)
        v1 = dr1.selectbox(d1_lbl, ["— all —"] + sorted(df[d1].dropna().unique().tolist(), key=str), key="cr3_v1")
        v2 = dr2.selectbox(d2_lbl, ["— all —"] + sorted(df[d2].dropna().unique().tolist(), key=str), key="cr3_v2")
        v3 = dr3.selectbox(d3_lbl, ["— all —"] + sorted(df[d3].dropna().unique().tolist(), key=str), key="cr3_v3")
        drill = df.copy()
        if v1 != "— all —": drill = drill[drill[d1] == v1]
        if v2 != "— all —": drill = drill[drill[d2] == v2]
        if v3 != "— all —": drill = drill[drill[d3] == v3]
        drill_table(drill, f"{d1_lbl}={v1} × {d2_lbl}={v2} × {d3_lbl}={v3}")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — LISTENING TRACKER
# ─────────────────────────────────────────────────────────────────────────────

def tab_tracker(df: pd.DataFrame):
    tracker = st.session_state["tracker"]
    listened_bwvs = {k for k, v in tracker.items() if v.get("listened")}

    st.markdown("## 🎧 Listening Tracker")

    # ── KPIs
    total = len(df)
    n_listened = df["bwv"].isin(listened_bwvs).sum()
    pct = round(100 * n_listened / total, 1) if total else 0
    listened_df = df[df["bwv"].isin(listened_bwvs)]
    total_min = listened_df["duration_min"].sum() or 0
    hrs, mins = int(total_min // 60), int(total_min % 60)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Works Listened", f"{n_listened} / {total}")
    k2.metric("Completion", f"{pct}%")
    k3.metric("Time Listened", f"{hrs}h {mins}m")
    k4.metric("Remaining", f"{total - n_listened} works")

    st.markdown("---")

    # ── Progress charts
    pc1, pc2 = st.columns([1, 2])
    with pc1:
        fig_donut = go.Figure(go.Pie(
            labels=["Listened", "Not Yet"],
            values=[n_listened, total - n_listened],
            hole=0.6,
            marker_colors=["#59a14f", "#e0e0e0"],
            textinfo="label+percent",
        ))
        fig_donut.add_annotation(
            text=f"{n_listened}<br>/{total}", x=0.5, y=0.5,
            font_size=16, showarrow=False,
        )
        fig_donut.update_layout(title="Overall Progress", height=300,
                                margin=dict(l=10,r=10,t=40,b=10),
                                showlegend=True, legend=dict(orientation="h", y=-0.1))
        st.plotly_chart(fig_donut, use_container_width=True)

    with pc2:
        df2 = df.copy()
        df2["status"] = df2["bwv"].apply(lambda b: "Listened" if b in listened_bwvs else "Not Yet")
        counts = df2.groupby(["genre", "status"]).size().reset_index(name="count")
        top_g = df2["genre"].value_counts().head(12).index
        counts = counts[counts["genre"].isin(top_g)]
        fig_genre = px.bar(
            counts, x="count", y="genre", color="status",
            color_discrete_map={"Listened": "#59a14f", "Not Yet": "#e0e0e0"},
            orientation="h", barmode="stack",
            title="Progress by Genre",
            labels={"count": "Works", "genre": "Genre"},
        )
        fig_genre.update_layout(height=340, margin=dict(l=10,r=10,t=40,b=10),
                                yaxis=dict(autorange="reversed"),
                                legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig_genre, use_container_width=True)

    # ── Progress by city
    city_rows = []
    for city in df["city"].unique():
        cdf = df[df["city"] == city]
        city_rows.append({
            "City": city,
            "Listened": cdf["bwv"].isin(listened_bwvs).sum(),
            "Remaining": (~cdf["bwv"].isin(listened_bwvs)).sum(),
            "Total": len(cdf),
        })
    city_prog = pd.DataFrame(city_rows).sort_values("Total", ascending=False)
    fig_city = px.bar(
        city_prog.melt(id_vars="City", value_vars=["Listened", "Remaining"]),
        x="value", y="City", color="variable",
        color_discrete_map={"Listened": "#59a14f", "Remaining": "#e0e0e0"},
        orientation="h", barmode="stack",
        title="Progress by City / Life Period",
        labels={"value": "Works", "variable": "Status"},
    )
    fig_city.update_layout(height=300, margin=dict(l=10,r=10,t=40,b=10),
                            yaxis=dict(autorange="reversed"),
                            legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig_city, use_container_width=True)

    # ── Rated works
    st.markdown("---")
    st.markdown("### ⭐ Your Rated Works")
    rated = []
    for bwv, data in tracker.items():
        if data.get("rating", 0) > 0:
            title = df[df["bwv"] == bwv]["title"].values[0] if bwv in df["bwv"].values else "Unknown"
            rated.append({
                "BWV": bwv, "Title": title,
                "Rating": "⭐" * data["rating"],
                "Notes": data.get("notes", ""),
            })
    if rated:
        rated_df = pd.DataFrame(rated).sort_values("Rating", ascending=False)
        st.dataframe(rated_df, use_container_width=True, height=280, hide_index=True)
    else:
        st.info("No rated works yet. Use the Search tab to rate individual BWVs.")

    # ── Bulk actions
    st.markdown("---")
    st.markdown("### ⚡ Bulk Actions on Current Filter")
    ba1, ba2 = st.columns(2)
    if ba1.button("✅ Mark ALL filtered works as Listened", use_container_width=True):
        for bwv in df["bwv"]:
            if bwv not in tracker:
                tracker[bwv] = {}
            tracker[bwv]["listened"] = True
        save_tracker(tracker)
        st.session_state["tracker"] = tracker
        st.success(f"Marked {len(df)} works as listened.")
        st.rerun()
    if ba2.button("🔲 Unmark ALL filtered works", use_container_width=True):
        for bwv in df["bwv"]:
            if bwv in tracker:
                tracker[bwv]["listened"] = False
        save_tracker(tracker)
        st.session_state["tracker"] = tracker
        st.success(f"Unmarked {len(df)} works.")
        st.rerun()

    # ── Export
    st.markdown("---")
    if tracker:
        st.download_button(
            "⬇️ Export listening_tracker.json",
            json.dumps(tracker, indent=2, ensure_ascii=False),
            "listening_tracker.json", "application/json",
            key="dl_tracker",
        )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    init_state()

    df = load_data()

    if "tracker" not in st.session_state or not st.session_state["tracker"]:
        st.session_state["tracker"] = load_tracker()

    filters = render_sidebar(df)
    filtered_df = apply_filters(df, filters)

    # Active filter banner
    if filters:
        st.info(
            f"🔍 **{len(filtered_df)} of {len(df)} works** match current sidebar filters. "
            "Clear in the sidebar to restore the full catalog."
        )

    # Global KPI strip
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Works", len(filtered_df))
    dated = filtered_df.dropna(subset=["year"])
    yr_range = (f"{int(dated['year'].min())}–{int(dated['year'].max())}"
                if not dated.empty else "—")
    k2.metric("Year Range", yr_range)
    k3.metric("Genres", filtered_df["genre"].nunique())
    k4.metric("Keys", filtered_df["key_display"].nunique())
    k5.metric("Cities", filtered_df["city"].nunique())
    total_h = round(filtered_df["duration_min"].sum() / 60, 1) \
        if filtered_df["duration_min"].notna().any() else 0
    k6.metric("Duration", f"{total_h}h")

    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🔍 Search & Detail",
        "📊 Interactive Charts",
        "🔀 Pivot Table",
        "📑 Cross Report",
        "🎧 Listening Tracker",
    ])

    with tab1:
        tab_search(filtered_df)
    with tab2:
        tab_charts(filtered_df)
    with tab3:
        tab_pivot(filtered_df)
    with tab4:
        tab_cross(filtered_df)
    with tab5:
        tab_tracker(filtered_df)

    # ── Footer ───────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        """
        <div style="
            text-align: center;
            color: #888888;
            font-size: 0.82rem;
            padding: 8px 0 16px 0;
            font-family: 'Georgia', serif;
            letter-spacing: 0.04em;
        ">
            &copy; All rights reserved &mdash; Made by <strong>Roberto</strong>
            &nbsp;(<a href="mailto:bach@rober.to" style="color:#888888;text-decoration:none;">bach@rober.to</a>)&nbsp;
            <span style="font-variant: small-caps;">MMX</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
