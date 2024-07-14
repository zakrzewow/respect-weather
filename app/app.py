import datetime as dt
import os

import pandas as pd
import requests
import streamlit as st
from modules import config, get_weather_forecast, login

# constants
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
locations = pd.read_csv(os.path.join(BASE_DIR, "locations.csv"), index_col="id")


# configuration
st.set_page_config(
    page_title="Respect Weather",
    page_icon="🌍",
    layout="wide",
)
if "publication_date" not in st.session_state:
    date = (
        dt.date.today()
        if dt.datetime.now().hour >= 12
        else dt.date.today() - dt.timedelta(days=1)
    )
    st.session_state.publication_date = date


# header
st.title("Respect Weather 🌍")
login()


# location
location = st.selectbox(
    "Select location:",
    options=locations["location"].tolist(),
    index=st.session_state.get("location_id", 876),
    placeholder="Location...",
    label_visibility="collapsed",
)
location_id = int(locations[locations["location"] == location].index[0])
latitiude = locations.at[location_id, "latitude"]
longitude = locations.at[location_id, "longitude"]


# main box
main_box = st.container(border=True)

col1, col2 = main_box.columns(2)
col1.markdown("#### " + location)


def favourite_toggle_click(location_id):
    favourites = st.session_state.get("favourites", [])
    id_token = st.session_state.get("id_token", "")
    headers = {"Authorization": f"Bearer {id_token}"}
    url = f"{config.API_URL}/favourites/{location_id}"
    if location_id in favourites:
        favourites.remove(location_id)
        requests.delete(url, headers=headers)
    else:
        favourites.append(location_id)
        requests.put(url, headers=headers)
    st.session_state["favourites"] = favourites


if st.session_state.get("id_token") is not None:
    col2.toggle(
        "Favourite ⭐",
        value=location_id in st.session_state.get("favourites", []),
        key="favourite_toggle",
        args=(location_id,),
        on_change=favourite_toggle_click,
    )
    st.markdown(
        """
    <style>
    .stCheckbox {
        display: flex;
        justify-content: right;
    }
    """,
        unsafe_allow_html=True,
    )

weather_forecast = get_weather_forecast(latitiude, longitude)
main_box.dataframe(weather_forecast)

col1, col2 = main_box.columns([10, 2])
col2.date_input(
    "Publication date",
    min_value=dt.date(2024, 5, 26),
    max_value=dt.date.today(),
    key="publication_date",
)


# favorites
def favourite_button_click(location_id):
    if not location_id in locations.index:
        return
    st.session_state["location_id"] = location_id


if st.session_state.get("id_token") is not None:
    st.markdown("#### Favorites ⭐")
    for i, favourite_id in enumerate(st.session_state.get("favourites", [])):
        favourite_location = locations.at[favourite_id, "location"]

        if i % 3 == 0:
            cols = st.columns(3)

        with cols[i % 3]:
            st.button(
                favourite_location,
                on_click=favourite_button_click,
                args=(favourite_id,),
                use_container_width=True,
            )
