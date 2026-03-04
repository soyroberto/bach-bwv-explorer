# Bach BWV Explorer — Streamlit App

**Author:** Roberto

An interactive Power BI-style web application for exploring Johann Sebastian Bach's complete BWV catalog (1,117 works). Filter by any combination of dimensions, pivot any two fields against each other, drill into individual works, and track which compositions you have listened to.

---

## 1. Prerequisites

You need Python 3.9+ and the following packages:

```bash
sudo pip3 install streamlit plotly pandas
```

---

## 2. File Structure

Place all three files in the same directory:

```
bach_app/
├── app.py                  ← The Streamlit application
├── bach_bwv_catalog.json   ← The BWV catalog data (1,117 works)
└── listening_tracker.json  ← Created automatically when you save listening data
```

---

## 3. How to Run

```bash
cd bach_app
streamlit run app.py
```

The app will open automatically in your browser at `http://localhost:8501`.

To run on a specific port or make it accessible on your network:

```bash
streamlit run app.py --server.port 8888 --server.address 0.0.0.0
```

---

## 4. App Features

The app has five tabs, each serving a distinct purpose.

### Tab 1 — 📊 Overview

A high-level dashboard showing the entire catalog (or your filtered selection) at a glance.

- **KPI row**: Total works, year range, number of genres, unique keys, and total duration in hours.
- **Works per Year by City**: Stacked bar chart showing Bach's output over time, colored by city (Arnstadt, Mühlhausen, Weimar, Köthen, Leipzig).
- **City → Genre Treemap**: Click any city block to drill into its genres.
- **City → Mode → Key Sunburst**: Click to drill from city down to mode (Major/Minor) and then to the specific key.
- **Year vs. Duration Scatter**: Each dot is one work. Hover to see the BWV number, title, genre, and key.

---

### Tab 2 — 🔀 Pivot Explorer

A fully interactive cross-tabulation tool, similar to a Power BI matrix visual.

- Select any **Row dimension** and **Column dimension** from: City, Genre, Mode, Decade, Key.
- The heatmap updates instantly to show the count of works at each intersection.
- Use the **Drill down into a cell** section below the heatmap to select a specific row and column value and see the full list of matching works.

---

### Tab 3 — 🎻 Instruments

Explore how Bach used instruments across cities and time periods.

- **Instrument × City bubble chart**: Bubble size represents the number of works. The top 18 instruments are shown.
- **Instrument Timeline**: Select any instrument from the dropdown to see a year-by-year bar chart of works featuring that instrument, colored by city.
- Below the timeline, a table lists every work featuring the selected instrument.

---

### Tab 4 — 📋 Works & Detail

A searchable, sortable table of all works matching your current filters.

- **Search box**: Filter the table further by any text (title, BWV number, genre, etc.).
- **Listened / Rating columns**: Works you have marked as listened show a ✅ checkmark; rated works show ⭐ stars.
- **Quick actions**: Bulk-mark all visible works as listened or unlistened with a single click.
- **Drill into a specific work**: Select any BWV from the dropdown to open its detail panel, where you can:
  - Mark it as **Listened** with a checkbox.
  - Give it a **Rating** from 0 to 5 stars.
  - Add **Personal notes** (e.g., a favourite recording, a concert you attended).
  - Click **Save** to persist your data to `listening_tracker.json`.

---

### Tab 5 — 🎧 Listening Tracker

A personal progress dashboard for your Bach listening journey.

- **Donut chart**: Shows the ratio of listened vs. not-yet-listened works in your current filter.
- **Metrics**: Works listened, completion percentage, and total listening time accumulated.
- **Progress by Genre**: Stacked bar chart showing listened vs. remaining for each genre.
- **Progress by City**: Stacked bar chart showing progress across Bach's five life periods.
- **Your Rated Works**: A table of all works you have rated, sorted by rating.
- **Export**: Download your full `listening_tracker.json` file for backup or sharing.

---

## 5. Sidebar Filters

All filters in the left sidebar apply instantly across all five tabs.

| Filter | Description |
|---|---|
| **City / Life Period** | Filter by one or more cities (Arnstadt, Mühlhausen, Weimar, Köthen, Leipzig, Unknown) |
| **Genre** | Filter by one or more genres (80 genres available) |
| **Mode** | Filter by Major, Minor, or Modal/Other |
| **Instrument** | Filter by one or more instruments (any work containing that instrument is included) |
| **Year Range** | Slider to restrict the composition year range (1704–1750) |
| **Duration** | Slider to restrict the duration range (1.5–180 minutes) |
| **Listened only** | Show only works you have marked as listened |
| **Not listened** | Show only works you have not yet listened to |
| **Reset All Filters** | Clear all filters and return to the full catalog |

---

## 6. Listening Data Persistence

Your listening data (listened status, ratings, and notes) is saved automatically to `listening_tracker.json` in the same directory as the app whenever you click **Save** on a work's detail panel or use the bulk-mark buttons.

This file persists between sessions. You can back it up, share it, or export it from the Listening Tracker tab.

---

## 7. Tips for Deep Analysis

- **Combine filters with the Pivot Explorer**: For example, filter to "Leipzig" in the sidebar, then open the Pivot tab and set Row = Genre, Column = Decade to see how Bach's output evolved during his Leipzig years.
- **Instrument timeline**: Select "Harpsichord" in the Instruments tab to see the exact years Bach was writing keyboard concertos vs. solo suites.
- **Year vs. Duration scatter**: Look for the cluster of long works (Passions, Oratorios, Mass in B minor) in the top-right of the scatter chart on the Overview tab.
- **Sunburst drill-down**: Click "Leipzig" in the sunburst, then "Minor" to see which minor keys Bach favoured during his Leipzig period.
