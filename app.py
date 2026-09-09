"""A browser front end for the simulator: run a railway, or draw one first.

    pip install --user streamlit
    streamlit run app.py

Two things only, because there are only two questions a person has. *Show me
this railway* - pick one of the scenarios in this repository, pick the
signalling systems to put it under, and read the comparison off. *Let me build
one* - name some stations and their kilometres, set the dozen numbers that are
actually decisions, and the same comparison comes back for a railway that did
not exist a minute ago.

WHAT THIS DELIBERATELY IS NOT

A track editor. Drawing rails with a mouse, dropping signals on them and
dragging point ends about is the largest part of every commercial simulator
and it answers none of the questions here: the layout is one-dimensional, so a
table of names and kilometres says everything a drawing would. The 176 lines of
scenarios/ring/infrastructure.yaml and the 373 of its timetable are not what
anyone typed - they are what a generator wrote from about a dozen numbers, and
this puts a form in front of those numbers instead.

Nothing under trainsim/core or trainsim/scenario imports this file, so the
simulator still runs on a bare Python install with pip blocked. This is a view.
"""

import os
import tempfile

import pandas as pd
import streamlit as st
from matplotlib.figure import Figure

from trainsim.analysis import kpi, trace
from trainsim.core import signalling
from trainsim.core.units import format_delay
from trainsim.scenario.generate import LineSpec, book
from trainsim.scenario.loader import ScenarioError, build_simulation, load_scenario

HERE = os.path.dirname(os.path.abspath(__file__))
COL = {name: index for index, name in enumerate(trace.COLUMNS)}
#: Every fifth simulated second is plenty for a train graph and keeps a long
#: run to a few thousand rows rather than a few hundred thousand.
SAMPLE_S = 5.0

TURKISH = {
    "fixed_block_3aspect": "Sabit blok (3 aspektli)",
    "etcs_l1": "ETCS Seviye 1",
    "etcs_l2": "ETCS Seviye 2",
    "etcs_hybrid_l3": "ETCS Hibrit Seviye 3",
    "etcs_moving_block": "Hareketli blok (ETCS L3)",
    "virtual_coupling": "Sanal koşum",
}


# ------------------------------------------------------------------- the runs

def run_systems(path, systems, duration_s=None, as_fitted=False):
    """One run per signalling system over the same railway and the same plan."""
    results = []
    overrides = {"duration_s": duration_s} if duration_s else {}
    progress = st.progress(0.0)
    for position, name in enumerate(systems):
        progress.progress(position / len(systems),
                          "%s koşuyor..." % TURKISH.get(name, name))
        # A fresh scenario each time: a signalling system may hold state, and a
        # timetable must not carry anything over from the previous run.
        scenario = load_scenario(path)
        scenario.signalling_spec = {"system": name}
        if not as_fitted:
            signalling.fit_timetable(scenario.timetable, name)
            scenario.driver_config = signalling.fit_driver(
                scenario.driver_config, name)
        sim = build_simulation(scenario, overrides)
        recorder = trace.TraceRecorder(interval_s=SAMPLE_S)
        sim.step_hooks.append(recorder)
        metrics = kpi.measure(sim)
        results.append({"name": name, "metrics": metrics,
                        "rows": recorder.rows, "sim": sim})
    progress.empty()
    return results


# ---------------------------------------------------------------- the pictures

def kpi_frame(results):
    baseline = results[0]["metrics"]
    rows = []
    for result in results:
        m = result["metrics"]
        rows.append({
            "Sistem": TURKISH.get(m.system, m.system),
            "Sefer süresi": _mmss(m.mean_journey_s),
            "Farkı": _delta(m, baseline),
            "Ort. gecikme (s)": round(m.mean_delay_s, 1),
            "Kısıtlı geçen (s)": round(m.total_restrained_s),
            "En dar aralık (s)": round(m.min_headway_s) if m.min_headway_s else None,
            "Ort. yetki (m)": round(m.mean_authority_m),
            "Biten": "%d/%d" % (m.completed, m.services),
            "İhlal": m.violations,
        })
    return pd.DataFrame(rows)


def _delta(metrics, baseline):
    """A difference, not a delay - so zero reads as "the same", not "on time"."""
    if metrics is baseline:
        return "-"
    difference = metrics.mean_journey_s - baseline.mean_journey_s
    return "aynı" if abs(difference) < 0.5 else format_delay(difference)


def train_graph(rows, title):
    """Time across, distance up, one line per train - the oldest railway picture."""
    paths = {}
    for row in rows:
        paths.setdefault(row[COL["train"]], []).append(
            (row[COL["time_s"]], row[COL["chainage_m"]]))
    figure = Figure(figsize=(8, 4.5), dpi=110)
    axes = figure.subplots()
    if paths:
        origin = min(point[0] for points in paths.values() for point in points)
        for train_id in sorted(paths):
            points = paths[train_id]
            axes.plot([(t - origin) / 60.0 for t, _ in points],
                      [c / 1000.0 for _, c in points], linewidth=1.1)
    axes.set_xlabel("koşunun kaçıncı dakikası")
    axes.set_ylabel("hat boyunca km")
    axes.set_title(title, fontsize=10)
    axes.grid(True, linewidth=0.3, alpha=0.5)
    figure.tight_layout()
    return figure


def arrivals_frame(sim):
    rows = []
    for train in sorted(sim.trains.values(), key=lambda t: t.id):
        rows.append({
            "Sefer": train.id,
            "Adı": train.name,
            "Durum": train.state,
            "Gecikme": format_delay(train.delay_s),
            "Duruş sayısı": len(train.actual_arrivals),
        })
    return pd.DataFrame(rows)


def show(results, key):
    st.subheader("Karşılaştırma")
    st.caption("Aynı hat, aynı tarife, aynı tren. Değişen tek şey trene ne "
               "söylendiği ve ne zaman söylendiği.")
    st.dataframe(kpi_frame(results), width="stretch", hide_index=True)

    problems = [r for r in results if r["metrics"].violations]
    if problems:
        st.error("Blok ihlali var: " + ", ".join(
            "%s (%d)" % (r["name"], r["metrics"].violations) for r in problems))

    st.subheader("Tren grafiği")
    st.caption("Eğim hızdır. Öndekine takılan tren bükülür, kendisiyle "
               "boğuşan bir sefer dizisi yelpaze açar.")
    columns = st.columns(min(len(results), 2))
    for position, result in enumerate(results):
        with columns[position % len(columns)]:
            st.pyplot(train_graph(
                result["rows"], TURKISH.get(result["name"], result["name"])))

    with st.expander("Sefer sefer varışlar"):
        chosen = st.selectbox("Sistem", [r["name"] for r in results],
                              format_func=lambda n: TURKISH.get(n, n),
                              key="arrivals_%s" % key)
        picked = next(r for r in results if r["name"] == chosen)
        st.dataframe(arrivals_frame(picked["sim"]), width="stretch",
                     hide_index=True)


def _mmss(seconds):
    if not seconds:
        return "-"
    total = int(round(seconds))
    return "%d:%02d" % (total // 60, total % 60)


def scenario_paths():
    """Every scenario.yaml under scenarios/, as {label: path}."""
    found = {}
    root = os.path.join(HERE, "scenarios")
    for railway in sorted(os.listdir(root)):
        directory = os.path.join(root, railway)
        if not os.path.isdir(directory):
            continue
        for filename in sorted(os.listdir(directory)):
            if filename.startswith("scenario") and filename.endswith(".yaml"):
                label = "%s / %s" % (railway, filename[:-5])
                found[label] = os.path.join(directory, filename)
    return found


# ------------------------------------------------------------------------ page

st.set_page_config(page_title="trainsim", layout="wide")
st.title("trainsim")
st.caption("Mikroskopik demiryolu benzetimi - sinyalizasyon sistemlerinin "
           "kapasiteye etkisi.")

existing, builder = st.tabs(["Hazır hat", "Yeni hat kur"])

with existing:
    scenarios = scenario_paths()
    left, right = st.columns([2, 3])
    with left:
        label = st.selectbox("Senaryo", list(scenarios), index=None,
                             placeholder="bir senaryo seç")
        duration = st.number_input("Koşu süresi (s, 0 = senaryonunki)",
                                   0, 60000, 0, step=600)
        as_fitted = st.checkbox(
            "Donanımı olduğu gibi bırak",
            help="Kapalıyken her sistem kendi gerektirdiği donanımla koşar. "
                 "Açıkken tarifenin beyan ettiği donanım kullanılır - o zaman "
                 "ölçtüğün şey sistemin değeri değil, bu filoya değeri olur.")
    with right:
        systems = st.multiselect(
            "Sinyalizasyon sistemleri", list(signalling.LADDER),
            default=["fixed_block_3aspect", "etcs_moving_block",
                     "virtual_coupling"],
            format_func=lambda n: TURKISH.get(n, n))

    if st.button("Koştur", type="primary", disabled=not (label and systems)):
        try:
            st.session_state["existing"] = run_systems(
                scenarios[label], systems, duration or None, as_fitted)
        except ScenarioError as exc:
            st.error(str(exc))
    if st.session_state.get("existing"):
        show(st.session_state["existing"], "hazir")

with builder:
    st.caption("Bir hat kurmak için karar vermen gereken her şey bu sayfada. "
               "Bloklar, sinyaller, peronlar ve tarifenin tamamı bunlardan "
               "türetiliyor - tarife, hat boşken bir tren koşturulup onun "
               "tuttuğu zamanlardan yazılıyor.")
    left, middle, right = st.columns(3)

    with left:
        st.markdown("**İstasyonlar**")
        default = pd.DataFrame({
            "ad": ["Aydın", "Bolu", "Ceyhan", "Demirci", "Edirne"],
            "km": [1.0, 9.0, 18.0, 27.0, 36.0],
        })
        table = st.data_editor(default, num_rows="dynamic", width="stretch",
                               key="stations")
        st.markdown("**Hat**")
        line_speed = st.slider("Hat hızı (km/h)", 40, 200, 100, 5)
        block_length = st.slider("Blok uzunluğu (m)", 300, 3000, 1200, 100)
        platforms = st.slider("İstasyon başına peron", 1, 4, 1)

    with middle:
        st.markdown("**Araç**")
        stock_length = st.slider("Uzunluk (m)", 40, 400, 120, 10)
        max_speed = st.slider("Azami hız (km/h)", 40, 200, 100, 5)
        max_accel = st.slider("Kalkış ivmesi (m/s²)", 0.3, 1.5, 1.0, 0.05)
        service = st.slider("Servis freni (m/s²)", 0.3, 1.5, 1.0, 0.05)
        emergency = st.slider("Acil fren (m/s²)", 0.5, 2.5, 1.5, 0.05)
        if emergency < service:
            st.warning("Acil fren servis freninden zayıf - bu tersine bir araç.")

    with right:
        st.markdown("**Sefer**")
        trains = st.slider("Tren sayısı", 2, 30, 10)
        headway = st.slider("Sefer aralığı (s)", 20, 600, 120, 5)
        dwell = st.slider("İstasyonda bekleme (s)", 0, 180, 30, 5)
        st.markdown("**Karşılaştırma**")
        new_systems = st.multiselect(
            "Sinyalizasyon sistemleri", list(signalling.LADDER),
            default=["fixed_block_3aspect", "etcs_moving_block",
                     "virtual_coupling"],
            format_func=lambda n: TURKISH.get(n, n), key="new_systems")
        duration_new = st.number_input("Koşu süresi (s)", 600, 60000, 9000,
                                       step=600)

    named = sorted(((str(row["ad"]).strip(), float(row["km"]))
                    for _, row in table.dropna(subset=["km"]).iterrows()),
                   key=lambda entry: entry[1])
    stations = [("S%02d" % (position + 1), name or "İstasyon %d" % (position + 1), km)
                for position, (name, km) in enumerate(named)]

    if len(stations) < 2:
        st.info("En az iki istasyon gerekiyor.")
    elif st.button("Kur ve koştur", type="primary", disabled=not new_systems):
        spec = LineSpec(
            name="ozel", stations=stations,
            line_speed_kmh=line_speed, block_length_m=block_length,
            platforms_per_station=platforms,
            stock_length_m=stock_length, max_speed_kmh=max_speed,
            max_accel=max_accel, service_brake=service,
            emergency_brake=emergency,
            trains=trains, headway_s=headway, dwell_s=dwell,
            duration_s=duration_new)
        if "builder_dir" not in st.session_state:
            st.session_state["builder_dir"] = tempfile.mkdtemp(prefix="trainsim-ui-")
        directory = st.session_state["builder_dir"]
        try:
            with st.spinner("Hat boş koşuluyor, tarife bundan yazılıyor..."):
                booked = book(directory, spec)
            if booked is None:
                st.error("Tek başına koşan tren bile hattı bitiremedi: koşu "
                         "süresi kısa, ya da plan bu hatta yürümüyor.")
            else:
                st.success("%.1f km, %d istasyon. Boş hatta sefer süresi %s."
                           % (spec.last_km, len(stations),
                              _mmss(booked[-1][0] - spec.first_departure_s)))
                st.session_state["built"] = run_systems(
                    directory, new_systems, duration_new)
        except (ScenarioError, ValueError) as exc:
            st.error(str(exc))

    if st.session_state.get("built"):
        show(st.session_state["built"], "yeni")
        with st.expander("Üretilen YAML"):
            directory = st.session_state["builder_dir"]
            for filename in ("infrastructure.yaml", "timetable.yaml",
                             "scenario.yaml"):
                with open(os.path.join(directory, filename)) as handle:
                    text = handle.read()
                st.markdown("`%s` - %d satır" % (filename, text.count("\n")))
                st.code(text[:4000], language="yaml")
