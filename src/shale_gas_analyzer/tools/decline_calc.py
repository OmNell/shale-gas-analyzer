"""Decline and production metric calculator for shale gas wells."""

from __future__ import annotations

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


def _safe_mean(series: pd.Series) -> float:
    valid = series.dropna()
    return float(valid.mean()) if not valid.empty else float("nan")


def _safe_endpoint_change(series: pd.Series) -> tuple[float, float, float]:
    valid = series.dropna()
    if len(valid) < 2:
        return float("nan"), float("nan"), float("nan")
    first = float(valid.iloc[0])
    last = float(valid.iloc[-1])
    total_change_rate = float("nan") if first == 0 else (last - first) / abs(first) * 100.0
    avg_daily_change_rate = total_change_rate / max(len(valid) - 1, 1) if pd.notna(total_change_rate) else float("nan")
    return total_change_rate, avg_daily_change_rate, last - first


def _fmt(value: float, suffix: str = "") -> str:
    if pd.isna(value):
        return "无法计算"
    return f"{value:.4f}{suffix}"


@tool("calculate_decline_metrics_tool")
def calculate_decline_metrics_tool(well_name: str = "AUTO") -> str:
    """Calculate recent 30-day decline, pressure and gas-water metrics from the matched CSV in data/."""
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

    recent_df = df.tail(30).copy()

    gas_col = find_column(
        recent_df,
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
        recent_df,
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
    casing_pressure_col = find_column(
        recent_df,
        ["Casing_Pressure_MPa", "casing_pressure_mpa", "Casing_Pressure", "套压", "套压_MPa"],
    )
    oil_pressure_col = find_column(
        recent_df,
        ["Oil_Pressure_MPa", "oil_pressure_mpa", "Oil_Pressure", "油压", "油压_MPa"],
    )

    gas = numeric_series(recent_df, gas_col)
    water = numeric_series(recent_df, water_col)
    casing_pressure = numeric_series(recent_df, casing_pressure_col)
    oil_pressure = numeric_series(recent_df, oil_pressure_col)

    gas_total_rate, gas_avg_daily_rate, gas_absolute_change = _safe_endpoint_change(gas)
    _, casing_avg_daily_rate, casing_absolute_change = _safe_endpoint_change(casing_pressure)
    pressure_diff = casing_pressure - oil_pressure if not casing_pressure.empty and not oil_pressure.empty else pd.Series(dtype=float)
    avg_gas = _safe_mean(gas)
    avg_water = _safe_mean(water)
    gas_water_ratio = avg_gas / avg_water if pd.notna(avg_gas) and pd.notna(avg_water) and avg_water != 0 else float("nan")
    avg_pressure_diff = _safe_mean(pressure_diff)

    return "\n".join(
        [
            f"请求井名：{selection.requested_well}",
            f"识别井名：{selection.detected_well}",
            f"数据定位说明：{selection.note}",
            f"数据文件：{selection.csv_path}",
            f"计算窗口：最近 {len(recent_df)} 条记录",
            f"日产气列：{gas_col or '未识别'}",
            f"日产水列：{water_col or '未识别'}",
            f"套压列：{casing_pressure_col or '未识别'}",
            f"油压列：{oil_pressure_col or '未识别'}",
            "",
            "最近 30 天量化指标：",
            f"产气量总变化率：{_fmt(gas_total_rate, '%')}",
            f"产气量日均变化率：{_fmt(gas_avg_daily_rate, '%/d')}",
            f"产气量绝对变化：{_fmt(gas_absolute_change)}",
            f"套压平均日消耗速率：{_fmt(abs(casing_avg_daily_rate), '%/d')}；套压绝对变化：{_fmt(casing_absolute_change, ' MPa')}",
            f"平均日产气：{_fmt(avg_gas)}",
            f"平均日产水：{_fmt(avg_water)}",
            f"气水比：{_fmt(gas_water_ratio)}",
            f"平均油套压差（套压-油压）：{_fmt(avg_pressure_diff, ' MPa')}",
            f"油套压差最小值：{_fmt(float(pressure_diff.min()) if not pressure_diff.dropna().empty else float('nan'), ' MPa')}",
            f"油套压差最大值：{_fmt(float(pressure_diff.max()) if not pressure_diff.dropna().empty else float('nan'), ' MPa')}",
            "",
            "工程解释提示：产气快速下滑且产水升高、气水比下降、油套压差异常扩大或套压持续消耗时，应重点复核井底积液或携液能力不足；若产水不高但压力与产气同步衰减，应关注地层能量衰竭或裂缝导流能力下降。",
        ]
    )
