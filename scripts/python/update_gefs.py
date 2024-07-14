import datetime as dt
import os
import urllib.request

import numpy as np
import pandas as pd
import pandas_gbq
import xarray as xr

longitude = np.concatenate(
    [
        np.linspace(0, 45, 46),
        np.linspace(300, 359, 60),
    ]
)
latitude = np.linspace(30, 90, 61)
coords = np.array([[x0, y0] for x0 in longitude for y0 in latitude])
coords = pd.DataFrame(coords).drop_duplicates().to_numpy()
lon = xr.DataArray(coords[:, 0], dims="idx")
lat = xr.DataArray(coords[:, 1], dims="idx")


def get_links_to_download():

    existing_rows = pandas_gbq.read_gbq(
        """
        SELECT DISTINCT time, valid_time, number
        FROM `meteo_dataset.gefs`
        WHERE time = ( SELECT MAX(time) FROM `meteo_dataset.gefs` )
    """,
        progress_bar_type=None,
    ).assign(
        time=lambda x: x.time.dt.tz_localize(None),
        valid_time=lambda x: x.valid_time.dt.tz_localize(None),
    )

    if existing_rows.empty:
        start_date = dt.datetime(2024, 5, 26)
    else:
        start_date = existing_rows["time"].max()

    end_date = dt.datetime.today()
    if end_date.hour > 12:
        end_date = end_date.replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        end_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)

    def get_valid_time(time):
        if time.hour == 0:
            time = time + pd.Timedelta(hours=12)
            end_time = time + pd.Timedelta(days=15, hours=12)
        elif time.hour == 12:
            end_time = time + pd.Timedelta(days=15)
        return pd.date_range(start=time, end=end_time, freq="1d")

    correct_df = (
        pd.DataFrame({"time": pd.date_range(start_date, end_date, freq="12h")})
        .assign(
            valid_time=lambda df: df["time"].apply(get_valid_time),
        )
        .explode("valid_time")
        .assign(number=lambda x: -1)
    )

    missing_rows = (
        pd.merge(
            left=correct_df,
            right=existing_rows.assign(right=1),
            on=["time", "valid_time", "number"],
            how="left",
        )
        .loc[lambda x: x["right"].isna(), ["time", "valid_time", "number"]]
        .reset_index(drop=True)
    )

    def number_to_g(number):
        if number == -1:
            return "geavg"
        elif number == 0:
            return "gec00"
        else:
            return f"gep{number:02d}"

    links = (
        missing_rows.assign(
            date=lambda x: x.time.dt.strftime("%Y%m%d"),
            p1="atmos/pgrb2ap5",
            p2="pgrb2a.0p50.",
            g=lambda x: x.number.map(number_to_g),
            hour=lambda x: x.time.map(lambda x: f"{x.hour:02}"),
            t=lambda x: x.hour.map("t{}z".format),
            f__=lambda x: ((x.valid_time - x.time).dt.total_seconds() // 3600).astype(
                int
            ),
            f=lambda x: x.f__.map("f{:03}".format),
            link=lambda df: df.apply(
                lambda x: f"https://noaa-gefs-pds.s3.amazonaws.com/gefs.{x.date}/{x.hour}/{x.p1}/{x.g}.{x.t}.{x.p2}{x.f}",
                axis=1,
            ),
        )
        .sort_values(by=["time", "valid_time"], ascending=True)
        .loc[:, "link"]
        .to_list()
    )
    return links


def process_url(url):
    filename = url.split("https://noaa-gefs-pds.s3.amazonaws.com/gefs.")[1].replace(
        "/", "."
    )
    try:
        urllib.request.urlretrieve(url, filename)
        surface = process_file(filename)
        os.remove(filename)
        return surface
    except Exception as e:
        print(url, e)


def process_file(filename):
    is_f000_file = filename.endswith("f000") or filename.endswith("f00")

    filter_by_keys_list = [
        {"typeOfLevel": "heightAboveGround", "level": 2},
        {"typeOfLevel": "heightAboveGround", "level": 10},
        {"typeOfLevel": "meanSea"},
        {"typeOfLevel": "surface"},
    ]

    if not is_f000_file:
        filter_by_keys_list.append({"typeOfLevel": "atmosphere"})

    surface = (
        pd.concat(
            [
                xr.open_dataset(
                    filename,
                    engine="cfgrib",
                    filter_by_keys=filter_by_keys,
                    indexpath="",
                )
                .drop_vars(
                    [
                        "step",
                        "surface",
                        "meanSea",
                        "atmosphere",
                        "heightAboveGround",
                        "nominalTop",
                        "unknown",
                        "icetk",
                        "level",
                    ],
                    errors="ignore",
                )
                .sel(longitude=lon, latitude=lat)
                .to_dataframe()
                .pipe(
                    lambda df: (
                        df.assign(number=-1) if "number" not in df.columns else df
                    )
                )
                .set_index(["longitude", "latitude", "number", "time", "valid_time"])
                for filter_by_keys in filter_by_keys_list
            ],
            axis=1,
        )
        .reset_index()
        .assign(
            longitude=lambda x: np.where(
                x["longitude"] > 180, x["longitude"] - 360, x["longitude"]
            )
        )
    )

    if is_f000_file:
        surface = surface.assign(
            tp=np.nan,
            tcc=np.nan,
        )

    surface = surface.loc[
        :,
        [
            "time",
            "valid_time",
            "latitude",
            "longitude",
            "number",
            "u10",
            "v10",
            "tp",
            "tcc",
            "t2m",
            "prmsl",
        ],
    ]
    return surface


def main():
    links = get_links_to_download()

    if not len(links):
        return

    surface_frames = []

    for link in links:
        surface = process_url(link)
        if surface is not None:
            surface_frames.append(surface)

    frame_to_upload = pd.concat(surface_frames, axis=0).reset_index(drop=True)

    pandas_gbq.to_gbq(
        frame_to_upload, "meteo_dataset.gefs", if_exists="append", progress_bar=False
    )


if __name__ == "__main__":
    main()
