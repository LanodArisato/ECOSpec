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
DARK_FILE = Path(__file__).parent / "spectra/lib" / "dark.csv"

def process_spectrum(filename, log_callback=print):
    if log_callback:
        log_callback(f"Processing {filename}...")

    # --- Load raw spectrum ---
    df = pd.read_csv(RAW_DIR / filename)

    wavelength = df.iloc[:, 0].values.astype(float)
    intensity = df.iloc[:, 1].values.astype(float)

    # --- Dark subtraction (BEFORE conversion) ---
    if DARK_FILE.exists():
        dark_df = pd.read_csv(DARK_FILE)

        dark_wavelength = dark_df.iloc[:, 0].values.astype(float)
        dark_intensity = dark_df.iloc[:, 1].values.astype(float)

        # Since you said same x-axis, enforce it
        if not np.allclose(wavelength, dark_wavelength):
            raise ValueError("Dark spectrum wavelength axis mismatch")

        intensity = intensity - dark_intensity


    # --- Wavelength -> wavenumber (cm^-1) ---
    wavenumber = 1e7 / wavelength

    # Sort result
    sort_idx = np.argsort(wavenumber)
    wavenumber = wavenumber[sort_idx]
    intensity = intensity[sort_idx]

    # --- Interpolate ---
    x = np.arange(200, 3401, 1)
    y_interp = np.interp(x, wavenumber, intensity)

    # --- Processing pipeline ---
    df_proc = pd.DataFrame({"WAVENUMBER": x, "INTENSITY_RAW": y_interp})

    df_proc["INTENSITY_MED"] = medfilt(df_proc["INTENSITY_RAW"], kernel_size=15)

    p = Polynomial.fit(df_proc["WAVENUMBER"], df_proc["INTENSITY_MED"], deg=7)
    baseline = p(df_proc["WAVENUMBER"])
    df_proc["INTENSITY_CORR"] = df_proc["INTENSITY_MED"] - baseline

    snv = (df_proc["INTENSITY_CORR"] - df_proc["INTENSITY_CORR"].mean()) / df_proc["INTENSITY_CORR"].std()
    df_proc["INTENSITY_SNV"] = snv

    scaler = MinMaxScaler()
    y = scaler.fit_transform(df_proc["INTENSITY_SNV"].values.reshape(-1, 1)).flatten()

    # --- Save ---
    stem = Path(filename).stem
    df_proc.to_csv(PROCESSED_DIR / f"{stem}_processed.csv", index=False)

    if log_callback:
        log_callback(f"Processed spectrum saved as: {stem}_processed.csv")

    # --- Library matching ---
    library_df = pd.read_csv(LIB_DIR / "lib.csv", header=None)
    material_names = [library_df.iloc[0, col] for col in range(1, library_df.shape[1], 2)]

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