import os

import google_auth_oauthlib.flow
import requests
import streamlit as st
from googleapiclient.discovery import build

from .config import API_URL, SELF_URL

SIGN_IN_OUT_BUTTON = """
<style>
div:has(> #login-box) {{
    height: 0px;
}}
</style>
<div id="login-box" style="display: flex; justify-content: right; position: relative; top: -60px;">
    <a href="{href}" target="_self" style="text-decoration: none; text-align: center; cursor: pointer; padding: 8px 12px; border-radius: 4px; display: flex; align-items: center; border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 0.5rem; color: rgb(49, 51, 63);">
    {content}
    </a>
</div>
"""


def _set_favourites():
    id_token = st.session_state.get("id_token", "")
    headers = {"Authorization": f"Bearer {id_token}"}
    r = requests.get(f"{API_URL}/favourites", headers=headers)
    st.session_state["favourites"] = r.json()


def login():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        os.path.join(os.path.abspath(os.path.dirname(__file__)), "credentials.json"),
        scopes=["openid", "https://www.googleapis.com/auth/userinfo.email"],
    )
    flow.redirect_uri = SELF_URL

    auth_code = st.query_params.get("code")
    st.query_params.clear()
    if auth_code:
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials
        user_info_service = build(
            serviceName="oauth2",
            version="v2",
            credentials=credentials,
        )
        user_info = user_info_service.userinfo().get().execute()
        st.session_state["email"] = user_info.get("email")
        st.session_state["id_token"] = credentials.id_token
        _set_favourites()

    email = st.session_state.get("email")
    if email is not None:
        html_content = SIGN_IN_OUT_BUTTON.format(href=SELF_URL, content="Sign out")
        st.markdown(html_content, unsafe_allow_html=True)
        st.markdown("Signed in as: " + email + " 🎉")
    else:
        auth_uri, _ = flow.authorization_url()
        content = """<img src="https://lh3.googleusercontent.com/COxitqgJr1sJnIDe8-jiKhxDx1FrYbtRHKJ9z_hELisAlapwE9LUPh6fcXIfb5vwpbMl4xl9H9TRFPc5NOO8Sb3VSgIBrfRYvW6cUA" alt="Google logo" style="margin-right: 8px; width: 20px; height: 20px; background-color: white; border: 2px solid white; border-radius: 4px;">
        Sign in with Google"""
        html_content = SIGN_IN_OUT_BUTTON.format(href=auth_uri, content=content)
        st.markdown(html_content, unsafe_allow_html=True)
