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

    # --- Load and sum 40 2D frames ---
    sum2D = None
    count = 0
    base_name = Path(filename).stem

    for i in range(1, 41):
        file_path = RAW_DIR / f"{base_name}_{i}.csv"

        if not file_path.exists():
            continue

        M = pd.read_csv(file_path, header=None).values.astype(float)
        M[np.isnan(M)] = 0

        if sum2D is None:
            sum2D = np.zeros_like(M, dtype=float)

        if M.shape != sum2D.shape:
            raise ValueError(f"Size mismatch in {file_path.name}")

        sum2D += M
        count += 1

    # ✅ check AFTER loop
    if count == 0:
        raise FileNotFoundError(f"No spectra found for base name: {base_name}")

    if log_callback:
        log_callback(f"Summed {count} 2D frames")

    # --- Dark subtraction (2D ONLY) ---
    if DARK_FILE.exists():
        dark2D = pd.read_csv(DARK_FILE, header=None).values.astype(float)
        dark2D[np.isnan(dark2D)] = 0

        if dark2D.shape != sum2D.shape:
            raise ValueError("Dark frame size mismatch")

        sum2D = sum2D - dark2D

    # --- Collapse 2D → 1D ---
    spec1D = np.sum(sum2D, axis=0)

    # --- Map pixel → wavelength ---
    x_pixels = np.arange(len(spec1D))
    x = np.arange(200, 3401, 1)
    y_sample = np.interp(x, x_pixels, spec1D)

    # OPTIONAL (recommended)
    # y_sample = y_sample / count

    # ❌ REMOVE this entire second dark subtraction block
    y_input = y_sample

    # --- Processing pipeline ---
    df_proc = pd.DataFrame({"WAVE": x, "INTENSITY_RAW": y_input})

    df_proc["INTENSITY_MED"] = medfilt(df_proc["INTENSITY_RAW"], kernel_size=15)

    p = Polynomial.fit(df_proc["WAVE"], df_proc["INTENSITY_MED"], deg=7)
    baseline = p(df_proc["WAVE"])
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