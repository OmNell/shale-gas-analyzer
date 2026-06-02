"""Shared dataset discovery helpers for shale gas CSV files."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd


AUTO_WELL_NAMES = {"", "auto", "automatic", "default", "dataset", "any", "all"}


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
    cleaned = df[column].astype(str).str.strip().replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    return pd.to_numeric(cleaned, errors="coerce")


def read_csv_robust(csv_path: str, **kwargs: Any) -> pd.DataFrame:
    try:
        return pd.read_csv(csv_path, **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(csv_path, encoding="gbk", **kwargs)


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
