"""Robust CSV reader tool for shale gas production data."""

from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from crewai.tools import tool
except ImportError:  # pragma: no cover - compatibility with some CrewAI releases
    from crewai_tools import tool

from shale_gas_analyzer.tools.data_utils import (
    find_column,
    locate_dataset,
    numeric_series,
    preprocess_production_dataframe,
    read_csv_robust,
)


def _date_span(df: pd.DataFrame) -> str:
    date_col = find_column(df, ["Date", "date", "Production_Date", "production_date", "日期", "生产日期"])
    if date_col is None:
        return f"{len(df)} records"
    dates = pd.to_datetime(df[date_col], errors="coerce")
    valid_dates = dates.dropna()
    if valid_dates.empty:
        return f"{len(df)} records; date column exists but cannot be parsed"
    return f"{valid_dates.min().date()} to {valid_dates.max().date()}, {len(df)} records"


def _format_recent_rows(df: pd.DataFrame) -> str:
    if df.empty:
        return "Recent 30-day data is empty."
    display_df = df.copy()
    for col in display_df.columns:
        if display_df[col].dtype.kind in "fc":
            display_df[col] = display_df[col].round(4)
    return display_df.to_string(index=False, max_rows=30)


@tool("read_shale_data_tool")
def read_shale_data_tool(well_name: str = "AUTO") -> str:
    """Read the best matching CSV from data/ and return global summary plus recent 30-day records."""
    try:
        selection = locate_dataset(well_name)
    except Exception as exc:
        return f"数据集定位失败：{exc}"

    try:
        df = preprocess_production_dataframe(read_csv_robust(selection.csv_path))
    except Exception as exc:
        return f"读取数据文件失败：{selection.csv_path}；错误：{exc}"

    if df.empty:
        return f"数据文件已读取但为空：{selection.csv_path}"

    oil_pressure_col = find_column(df, ["Oil_Pressure_MPa", "oil_pressure_mpa", "油压", "油压_MPa"])
    if oil_pressure_col is not None:
        df[oil_pressure_col] = numeric_series(df, oil_pressure_col)

    gas_col = find_column(
        df,
        [
            "Daily_Gas_Production",
            "Daily_Gas_Production_10k_m3",
            "Daily_Gas_Production_104m3",
            "Gas_Production",
            "gas",
            "日产气",
            "日产气量",
        ],
    )
    water_col = find_column(
        df,
        [
            "Daily_Water_Production",
            "Daily_Water_Production_m3",
            "Daily_Water_Production_t",
            "Water_Production",
            "water",
            "日产水",
            "日产水量",
        ],
    )
    cumulative_gas_col = find_column(
        df,
        ["Cumulative_Gas_Production", "Cumulative_Gas_Production_10k_m3", "Cumulative_Gas_Production_104m3", "累计产气"],
    )
    cumulative_water_col = find_column(
        df,
        ["Cumulative_Water_Production", "Cumulative_Water_Production_m3", "Cumulative_Water_Production_t", "累计产水"],
    )

    gas = numeric_series(df, gas_col)
    water = numeric_series(df, water_col)
    cumulative_gas = numeric_series(df, cumulative_gas_col)
    cumulative_water = numeric_series(df, cumulative_water_col)
    recent_df = df.tail(30).copy()

    max_daily_gas = gas.max(skipna=True) if not gas.dropna().empty else np.nan
    total_gas = cumulative_gas.dropna().iloc[-1] if not cumulative_gas.dropna().empty else gas.sum(skipna=True)
    total_water = cumulative_water.dropna().iloc[-1] if not cumulative_water.dropna().empty else water.sum(skipna=True)

    summary = [
        f"请求井名：{selection.requested_well}",
        f"识别井名：{selection.detected_well}",
        f"数据定位说明：{selection.note}",
        f"数据文件：{selection.csv_path}",
        f"生产跨度：{_date_span(df)}",
        f"最高日产气：{max_daily_gas:.4f}" if pd.notna(max_daily_gas) else "最高日产气：无法计算，未识别日产气列",
        f"累计产气：{total_gas:.4f}" if pd.notna(total_gas) else "累计产气：无法计算，未识别累计产气或日产气列",
        f"累计产水：{total_water:.4f}" if pd.notna(total_water) else "累计产水：无法计算，未识别累计产水或日产水列",
        "",
        "最近 30 天流水数据：",
        _format_recent_rows(recent_df),
    ]
    return "\n".join(summary)
