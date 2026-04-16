import pandas as pd
import numpy as np
from scipy.signal import medfilt
from numpy.polynomial import Polynomial
from sklearn.preprocessing import MinMaxScaler
from scipy.stats import pearsonr
from pathlib import Path
import matplotlib.pyplot as plt

RAW_DIR = Path(__file__).parent / "spectra/raw"
PROCESSED_DIR = Path(__file__).parent / "spectra/processed"
LIB_DIR = Path(__file__).parent / "spectra/lib"

def process_spectrum(filename, log_callback=print):
    """
    Preprocess a spectrum and compute Pearson r against library.
    Returns:
        best_match: material with highest Pearson r
        best_r: Pearson correlation coefficient
        top3: list of top 3 tuples (material_name, Pearson r)
        x: wavenumber grid (numpy array)
        y: final normalized intensity (numpy array)
    """
    if log_callback:
        log_callback(f"Processing {filename}...")

    # --- Load raw spectrum ---
    df = pd.read_csv(RAW_DIR / filename, header=None, names=["WAVE", "INTENSITY"])
    df = df[df["INTENSITY"] > 0]
    df["INTENSITY"] = df["INTENSITY"].round()
    df["WAVE"] = df["WAVE"].round()
    df = df[(df["WAVE"] >= 200) & (df["WAVE"] <= 3400)]

    # --- Interpolation ---
    x = np.arange(200, 3401, 1)
    y_interp = np.interp(x, df["WAVE"], df["INTENSITY"])

    df_proc = pd.DataFrame({"WAVE": x, "INTENSITY_RAW": y_interp})

    # --- Median filter ---
    df_proc["INTENSITY_MED"] = medfilt(df_proc["INTENSITY_RAW"], kernel_size=15)

    # --- Polynomial baseline correction ---
    p = Polynomial.fit(df_proc["WAVE"], df_proc["INTENSITY_MED"], deg=7)
    baseline = p(df_proc["WAVE"])
    df_proc["INTENSITY_CORR"] = df_proc["INTENSITY_MED"] - baseline

    # --- SNV normalization ---
    snv = (df_proc["INTENSITY_CORR"] - df_proc["INTENSITY_CORR"].mean()) / df_proc["INTENSITY_CORR"].std()
    df_proc["INTENSITY_SNV"] = snv

    # --- Min-Max scaling ---
    scaler = MinMaxScaler()
    y = scaler.fit_transform(df_proc["INTENSITY_SNV"].values.reshape(-1, 1)).flatten()

    # --- Save processed spectrum ---
    stem = Path(filename).stem
    df_proc.to_csv(PROCESSED_DIR / f"{stem}_processed.csv", index=False)
    if log_callback:
        log_callback(f"Processed spectrum saved as: {stem}_processed.csv")

    # --- Load library ---
    library_file = LIB_DIR / "lib.csv"
    library_df = pd.read_csv(library_file, header=None)

    # Material names from first row, ignoring first column
    material_names = [library_df.iloc[0, col] for col in range(1, library_df.shape[1], 2)]

    # --- Pearson correlation matching ---
    best_match = None
    best_r = -np.inf
    scores = {}

    for idx, col in enumerate(range(1, library_df.shape[1], 2)):
        lib_intensity = library_df.iloc[1:, col].astype(float).values
        material_name = material_names[idx]

        if len(lib_intensity) != len(y):
            raise ValueError(f"Length mismatch for {material_name}")

        r, _ = pearsonr(y, lib_intensity)
        scores[material_name] = r

        if r > best_r:
            best_r = r
            best_match = material_name

    top3 = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]

    if log_callback:
        log_callback(f"Best match: {best_match}, Pearson r = {best_r:.4f}")
        log_callback(f"Top 3 matches with r values: {top3}")

    return best_match, best_r, top3, x, y