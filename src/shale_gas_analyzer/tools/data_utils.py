"""Shared dataset discovery helpers for shale gas CSV files."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd


AUTO_WELL_NAMES = {"", "auto", "automatic", "default", "dataset", "any", "all"}
DATE_CANDIDATES = ["Date", "date", "Production_Date", "production_date", "日期", "生产日期", "鏃ユ湡", "鐢熶骇鏃ユ湡"]
MISSING_TOKENS = {
    "",
    " ",
    "-",
    "--",
    "---",
    "nan",
    "NaN",
    "NAN",
    "none",
    "None",
    "NULL",
    "null",
    "N/A",
    "n/a",
    "#N/A",
}


@dataclass(frozen=True)
class DatasetSelection:
    requested_well: str
    detected_well: str
    csv_path: str
    note: str


def project_root() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(current_dir, os.pardir, os.pardir, os.pardir))


def data_dir() -> str:
    return os.path.join(project_root(), "data")


def extract_well_name(value: Any) -> str:
    if isinstance(value, dict):
        candidate = (
            value.get("well_name")
            or value.get("well")
            or value.get("name")
            or value.get("dataset")
            or value.get("dataset_file")
        )
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                payload = json.loads(text)
                candidate = (
                    payload.get("well_name")
                    or payload.get("well")
                    or payload.get("name")
                    or payload.get("dataset")
                    or payload.get("dataset_file")
                )
            except json.JSONDecodeError:
                candidate = text
        else:
            candidate = text
    else:
        candidate = str(value).strip()

    safe_name = os.path.basename(str(candidate or "AUTO").strip()).replace(".csv", "")
    return safe_name or "AUTO"


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    normalized = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        found = normalized.get(candidate.lower())
        if found is not None:
            return found
    return None


def numeric_series(df: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None or column not in df.columns:
        return pd.Series(dtype=float)
    cleaned = (
        df[column]
        .astype(str)
        .str.strip()
        .replace({token: pd.NA for token in MISSING_TOKENS})
        .str.replace(",", "", regex=False)
    )
    cleaned = cleaned.str.extract(r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)", expand=False)
    return pd.to_numeric(cleaned, errors="coerce")


def read_csv_robust(csv_path: str, **kwargs: Any) -> pd.DataFrame:
    encodings = [None, "utf-8-sig", "gbk", "gb18030"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            if encoding is None:
                return pd.read_csv(csv_path, **kwargs)
            return pd.read_csv(csv_path, encoding=encoding, **kwargs)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    return pd.read_csv(csv_path, **kwargs)


def preprocess_production_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a raw production CSV into a safer analysis dataframe."""
    if df.empty:
        return df.copy()

    cleaned = df.copy()
    cleaned.columns = [str(col).strip() for col in cleaned.columns]
    cleaned = cleaned.loc[:, [col for col in cleaned.columns if col and not str(col).lower().startswith("unnamed:")]]
    if cleaned.empty:
        return cleaned

    cleaned = cleaned.replace({token: pd.NA for token in MISSING_TOKENS})
    cleaned = cleaned.dropna(axis=0, how="all").dropna(axis=1, how="all")
    if cleaned.empty:
        return cleaned

    for col in cleaned.select_dtypes(include=["object"]).columns:
        cleaned[col] = cleaned[col].map(lambda value: value.strip() if isinstance(value, str) else value)

    date_col = find_column(cleaned, DATE_CANDIDATES)
    if date_col is not None:
        parsed = pd.to_datetime(cleaned[date_col], errors="coerce")
        cleaned = cleaned.assign(__parsed_date=parsed)
        cleaned = cleaned.sort_values("__parsed_date", na_position="last").drop(columns=["__parsed_date"])

    cleaned = cleaned.reset_index(drop=True)
    return cleaned


def _csv_files() -> list[str]:
    folder = data_dir()
    if not os.path.isdir(folder):
        return []
    return sorted(
        [
            os.path.join(folder, name)
            for name in os.listdir(folder)
            if name.lower().endswith(".csv") and os.path.isfile(os.path.join(folder, name))
        ],
        key=lambda path: os.path.getmtime(path),
        reverse=True,
    )


def _forced_csv_file() -> str | None:
    value = os.getenv("SHALE_GAS_DATA_FILE", "").strip().strip('"').strip("'")
    if not value:
        return None
    path = os.path.abspath(os.path.expanduser(value))
    if not os.path.isfile(path):
        raise FileNotFoundError(f"SHALE_GAS_DATA_FILE does not exist: {path}")
    if not path.lower().endswith(".csv"):
        raise ValueError(f"SHALE_GAS_DATA_FILE must be a CSV file: {path}")
    return path


def _detect_well_id(csv_path: str) -> str:
    try:
        sample = read_csv_robust(csv_path, nrows=1000)
    except Exception:
        return os.path.splitext(os.path.basename(csv_path))[0]

    sample.columns = [str(col).strip() for col in sample.columns]
    well_col = find_column(sample, ["Well_ID", "well_id", "WellName", "well_name", "井号", "井名"])
    if well_col is None:
        return os.path.splitext(os.path.basename(csv_path))[0]

    values = sample[well_col].dropna().astype(str).str.strip()
    values = values[values != ""]
    if values.empty:
        return os.path.splitext(os.path.basename(csv_path))[0]
    return values.mode().iloc[0] if not values.mode().empty else values.iloc[0]


def locate_dataset(well_name: Any) -> DatasetSelection:
    requested = extract_well_name(well_name)
    requested_key = requested.strip().lower()

    forced_csv = _forced_csv_file()
    if forced_csv:
        return DatasetSelection(
            requested_well=requested,
            detected_well=_detect_well_id(forced_csv),
            csv_path=forced_csv,
            note="Using CSV uploaded from the web console for this run.",
        )

    files = _csv_files()

    if not files:
        raise FileNotFoundError(f"No CSV files found in data directory: {data_dir()}")

    if requested_key not in AUTO_WELL_NAMES:
        for csv_path in files:
            stem = os.path.splitext(os.path.basename(csv_path))[0].lower()
            if stem == requested_key:
                return DatasetSelection(
                    requested_well=requested,
                    detected_well=_detect_well_id(csv_path),
                    csv_path=csv_path,
                    note="Matched dataset by case-insensitive file name.",
                )

        well_matches: list[str] = []
        for csv_path in files:
            detected = _detect_well_id(csv_path)
            if detected.strip().lower() == requested_key:
                well_matches.append(csv_path)

        if len(well_matches) == 1:
            csv_path = well_matches[0]
            return DatasetSelection(
                requested_well=requested,
                detected_well=_detect_well_id(csv_path),
                csv_path=csv_path,
                note="Matched dataset by Well_ID column, independent of file name.",
            )

        if len(well_matches) > 1:
            csv_path = well_matches[0]
            return DatasetSelection(
                requested_well=requested,
                detected_well=_detect_well_id(csv_path),
                csv_path=csv_path,
                note="Multiple matching Well_ID datasets found; selected the newest modified file.",
            )

    if len(files) == 1:
        csv_path = files[0]
        return DatasetSelection(
            requested_well=requested,
            detected_well=_detect_well_id(csv_path),
            csv_path=csv_path,
            note="Only one CSV exists in data directory; selected it automatically.",
        )

    csv_path = files[0]
    return DatasetSelection(
        requested_well=requested,
        detected_well=_detect_well_id(csv_path),
        csv_path=csv_path,
        note="No exact match found; selected the newest modified CSV in data directory.",
    )
