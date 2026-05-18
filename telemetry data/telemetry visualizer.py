from pathlib import Path

import pandas as pd
import plotly.express as px


def load_telemetry(file_path):
    phases = {}
    current_phase = None
    rows = []

    with open(file_path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()

            if line.startswith("Phase"):
                if current_phase and rows:
                    df_phase = pd.DataFrame(rows, columns=["Time", "Wh"])
                    phases[current_phase] = df_phase
                    rows = []
                current_phase = line

            elif line and not line.startswith("Time"):
                parts = line.split(" , ")
                if len(parts) == 2:
                    rows.append(parts)

    if current_phase and rows:
        df_phase = pd.DataFrame(rows, columns=["Time", "Wh"])
        phases[current_phase] = df_phase
    return phases


def clean_phase_data(df):
    df["Time"] = pd.to_datetime(df["Time"], dayfirst=True)
    df["Wh"] = pd.to_numeric(df["Wh"])
    return df


DATA_DIR = Path("./telemetry data")
files = list(DATA_DIR.glob("*.csv"))
all_data = []

for file in files:
    phases = load_telemetry(file)

    for phase_name, df in phases.items():
        df = clean_phase_data(df)
        df["phase"] = phase_name
        df["source"] = file.name.split("_")[0]
        all_data.append(df)

df = pd.concat(all_data)

fig = px.line(df, x="Time", y="Wh", color="phase", facet_row="source", title="Power telemetry")

fig.show()
