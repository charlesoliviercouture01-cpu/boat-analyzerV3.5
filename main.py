rom flask import Flask, request, render_template_string, send_file, url_for
app = Flask(__name__)
import pandas as pd
import os
from datetime import datetime


# ================= CONFIG =================
CFG = {
    "TPS_CHEAT_MIN": 97.0,            # condition obligatoire
    "lambda_range": (0.80, 0.92),
    "fuel_range": (317, 372),
    "ambient_offset": 15,
    "cheat_delay_sec": 0.5
}

UPLOAD_DIR = "/tmp"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ================= HTML =================
HTML = """
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Boat Data Analyzer</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>

<body class="p-4 bg-dark text-light">
<div class="container">

<div class="d-flex justify-content-between align-items-center mb-4">
  <img src="{{ url_for('static', filename='precision_logo.png') }}"
       style="height:120px;" onerror="this.style.display='none'">
  <h1 class="text-center flex-grow-1">{{ etat_global }}</h1>
  <img src="{{ url_for('static', filename='image_copy.png') }}"
       style="height:120px;" onerror="this.style.display='none'">
</div>

<form method="post" action="/upload" enctype="multipart/form-data">

<div class="row mb-2">
  <div class="col"><input class="form-control" type="date" name="date_test" required></div>
  <div class="col"><input class="form-control" type="time" name="heure_session" required></div>
  <div class="col"><input class="form-control" name="num_embarcation" placeholder="Numéro embarcation" required></div>
</div>

<div class="row mb-2">
  <div class="col-md-4">
    <input class="form-control" type="number" step="0.1"
           name="ambient_temp" placeholder="Température ambiante (°C)" required>
  </div>
</div>

<input class="form-control mb-2" type="file" name="file" required>
<button class="btn btn-primary">Analyser</button>

</form>

{% if table %}
<hr>
<a class="btn btn-success" href="{{ download }}">Télécharger CSV</a>
<div class="table-responsive mt-3">{{ table|safe }}</div>
{% endif %}

</div>
</body>
</html>
"""

# ================= ANALYSE =================
def analyze_dataframe(df, ambient_temp):

    REQUIRED = [
        "TPS (%)",
        "Fuel Pressure (psi)",
        "IAT (°C)",
        "ECT (°C)",
        "Time (s)"
    ]

    for col in REQUIRED:
        if col not in df.columns:
            raise ValueError(f"Colonne manquante : {col}")

    lambda_cols = [c for c in df.columns if "lambda" in c.lower()]
    if not lambda_cols:
        raise ValueError("Aucune colonne Lambda détectée")

    df["Lambda"] = df[lambda_cols].mean(axis=1)

    df["TPS_OK"] = df["TPS (%)"] >= CFG["TPS_CHEAT_MIN"]
    df["Lambda_OK"] = df["Lambda"].between(*CFG["lambda_range"])
    df["Fuel_OK"] = df["Fuel Pressure (psi)"].between(*CFG["fuel_range"])
    df["IAT_OK"] = df["IAT (°C)"] <= ambient_temp + CFG["ambient_offset"]
    df["ECT_OK"] = df["ECT (°C)"] <= ambient_temp + CFG["ambient_offset"]

    df["OUT"] = df["TPS_OK"] & ~(df["Lambda_OK"] & df["Fuel_OK"] & df["IAT_OK"] & df["ECT_OK"])

    df["dt"] = df["Time (s)"].diff().fillna(0)

    acc = 0.0
    debut = []

    for out, dt in zip(df["OUT"], df["dt"]):
        if out:
            acc += dt
            debut.append(acc >= CFG["cheat_delay_sec"])
        else:
            acc = 0.0
            debut.append(False)

    df["Début_triche"] = debut
    df["QUALIFIÉ"] = ~df["Début_triche"].rolling(2).max().fillna(False)

    return df

# ================= ROUTES =================
@app.route("/")
def index():
    return render_template_string(HTML, table=None, download=None, etat_global="Boat Data Analyzer")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files["file"]
        ambient_temp = float(request.form["ambient_temp"])

        df = pd.read_csv(file)
        df = analyze_dataframe(df, ambient_temp)

        rows = df[df["Début_triche"]]
        etat = "PASS"
        if not rows.empty:
            etat = f"CHEAT – Début à {rows['Time (s)'].iloc[0]:.2f} s"

        fname = f"result_{datetime.now().timestamp()}.csv"
        path = os.path.join(UPLOAD_DIR, fname)
        df.to_csv(path, index=False)

        table = df.head(100).to_html(classes="table table-dark table-striped", index=False)

        return render_template_string(
            HTML,
            table=table,
            download=url_for("download", fname=fname),
            etat_global=etat
        )

    except Exception as e:
        return f"<h2>Internal Server Error</h2><pre>{e}</pre>", 500

@app.route("/download")
def download():
    fname = request.args.get("fname")
    return send_file(os.path.join(UPLOAD_DIR, fname), as_attachment=True)

