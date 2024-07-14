import io

import pandas as pd
import requests
import seaborn as sns
import streamlit as st

from .config import API_URL


@st.cache_data
def _download_data(longitude, latitude, publication_date):
    publication_date_str = publication_date.strftime("%Y-%m-%d")
    url = f"{API_URL}/forecasts?longitude={longitude}&latitude={latitude}&publication_date={publication_date_str}"
    r = requests.get(url)
    df = pd.read_csv(io.StringIO(r.text), parse_dates=["time", "valid_time"])
    return df


def get_weather_forecast(latitude, longitude):
    # downloading data
    publication_date = st.session_state.publication_date
    df = _download_data(longitude, latitude, publication_date)

    # calculating weights to average the values between 4 points
    df["weight"] = 2 - (
        (df["latitude"] - latitude) ** 2 + (df["longitude"] - longitude) ** 2
    )
    weight_norm = (
        df.groupby(["time", "valid_time"])[["weight"]]
        .sum()
        .reset_index()
        .rename(columns={"weight": "weight_norm"})
    )
    df = df.merge(weight_norm, on=["time", "valid_time"])

    # averaging the values between 4 points and transfoming the data
    df = (
        df.assign(
            weight=lambda x: x["weight"] / x["weight_norm"],
            u10=lambda x: x["u10"] * x["weight"],
            v10=lambda x: x["v10"] * x["weight"],
            tp=lambda x: x["tp"] * x["weight"],
            tcc=lambda x: x["tcc"] * x["weight"],
            t2m=lambda x: x["t2m"] * x["weight"],
            prmsl=lambda x: x["prmsl"] * x["weight"],
        )
        .groupby(["time", "valid_time"])
        .sum()
        .reset_index()
        .assign(
            w=lambda x: (x["u10"] ** 2 + x["v10"] ** 2) ** 1 / 2,
            t2m=lambda x: x["t2m"] - 273.15,
            prmsl=lambda x: x["prmsl"] / 100,
        )
        .drop(columns=["u10", "v10", "time"])
        .assign(valid_time=lambda x: x["valid_time"].dt.strftime("%d/%m"))
        .set_index("valid_time")
        .rename_axis(None, axis=0)
        .loc[:, ["tcc", "t2m", "tp", "w", "prmsl"]]
    )

    # formatting the data
    gmap = df.copy()

    def format_tcc(x):
        emoji = ""
        if 0 <= x.tcc < 30:
            emoji = "☀️"
        if 30 <= x.tcc < 60:
            emoji = "🌤️"
        if 60 <= x.tcc < 90:
            if x.tp > 0.5:
                emoji = "🌦️"
            else:
                emoji = "🌥️"
        if 80 <= x.tcc:
            if x.tp > 0.5:
                emoji = "🌧️"
            else:
                emoji = "☁️"
        return f"{emoji} {x.tcc/100:.0%}"

    df["tcc"] = df.apply(format_tcc, axis=1)
    df["tp"] = df["tp"].apply(lambda x: f"{x:.1f}")
    df["t2m"] = df["t2m"].apply(lambda x: f"{x:.0f}°")
    df["w"] = df["w"].apply(lambda x: f"{x:.1f}")
    df["prmsl"] = df["prmsl"].apply(lambda x: f"{x:.0f}")

    column_mapper = {
        "tcc": "🌥️ Cloudiness [%]",
        "t2m": "🌡️ Temperature [°C]",
        "tp": "💧 Precipitation [mm]",
        "w": "💨 Wind [km/h]",
        "prmsl": "🌀 Pressure [hPa]",
    }

    df = df.rename(columns=column_mapper).T
    gmap = gmap.rename(columns=column_mapper).T

    # styling the data
    t2m_cmap = sns.diverging_palette(
        h_neg=255, h_pos=0, s=99, l=95, sep=46, as_cmap=True
    )
    tp_cmap = sns.cubehelix_palette(
        start=2.2,
        rot=0.2,
        gamma=5,
        hue=1,
        light=0.9,
        dark=1,
        reverse=True,
        as_cmap=True,
    )
    w_cmap = sns.cubehelix_palette(
        start=2.3,
        rot=-1,
        gamma=4.8,
        hue=0,
        light=0.95,
        dark=1,
        reverse=True,
        as_cmap=True,
    )

    df = (
        df.style.background_gradient(
            cmap=t2m_cmap,
            axis=1,
            subset=pd.IndexSlice["🌡️ Temperature [°C]":"🌡️ Temperature [°C]"],
            gmap=gmap.loc["🌡️ Temperature [°C]"],
        )
        .background_gradient(
            cmap=tp_cmap,
            axis=1,
            subset=pd.IndexSlice["💧 Precipitation [mm]":"💧 Precipitation [mm]"],
            gmap=gmap.loc["💧 Precipitation [mm]"],
            vmin=0,
            vmax=10,
        )
        .background_gradient(
            cmap=w_cmap,
            axis=1,
            subset=pd.IndexSlice["💨 Wind [km/h]":"💨 Wind [km/h]"],
            gmap=gmap.loc["💨 Wind [km/h]"],
            vmin=0,
            vmax=20,
        )
    )

    return df
