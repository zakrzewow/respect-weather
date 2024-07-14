import json
import os

import pandas_gbq
import sqlalchemy
from flask import Flask, jsonify, make_response, request
from google.auth.transport import requests
from google.cloud.alloydb.connector import Connector
from google.oauth2 import id_token

app = Flask(__name__)

## constants
with open(
    os.path.join(os.path.abspath(os.path.dirname(__file__)), "credentials.json")
) as f:
    credentials = json.load(f)
CLIENT_ID = credentials["web"]["client_id"]
PROJECT_ID = credentials["web"]["project_id"]

## database connection
connector = Connector()


def getconn():
    conn = connector.connect(
        f"projects/{PROJECT_ID}/locations/europe-west1/clusters/alloydb-cluster/instances/alloydb-instance",
        "pg8000",
        user="alloydb_user",
        password="alloydb_password",
        db="postgres",
    )
    return conn


pool = sqlalchemy.create_engine(
    "postgresql+pg8000://",
    creator=getconn,
)

## database functions
check_sql = sqlalchemy.text(
    "SELECT COUNT(*) FROM favourites WHERE user_id = :user_id AND location_id = :location_id;"
)
insert_sql = sqlalchemy.text(
    "INSERT INTO favourites (user_id, location_id) VALUES (:user_id, :location_id);"
)
select_sql = sqlalchemy.text(
    "SELECT location_id FROM favourites WHERE user_id=:user_id;"
)
delete_sql = sqlalchemy.text(
    "DELETE FROM favourites WHERE user_id=:user_id AND location_id=:location_id;"
)


def add_favourite(user_id, location_id):
    with pool.connect() as conn:
        result = conn.execute(
            check_sql.bindparams(user_id=user_id, location_id=location_id)
        ).fetchone()
        if result[0] == 0:
            conn.execute(
                insert_sql.bindparams(user_id=user_id, location_id=location_id)
            )
            conn.commit()


def remove_favourite(user_id, location_id):
    with pool.connect() as conn:
        conn.execute(delete_sql.bindparams(user_id=user_id, location_id=location_id))
        conn.commit()


def list_favourites(user_id):
    with pool.connect() as conn:
        favourites = conn.execute(select_sql.bindparams(user_id=user_id)).fetchall()
        return [favourite[0] for favourite in favourites]


## authorization
def authorize():
    auth_header = request.headers.get("Authorization")

    if auth_header:
        bearer, token = auth_header.split()
        if bearer.lower() != "bearer":
            return jsonify({"message": "Invalid Authorization header format"}), 400
        try:
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), CLIENT_ID)
            return idinfo["sub"]
        except Exception as e:
            return (
                jsonify({"message": "Token verification failed", "error": str(e)}),
                401,
            )
    else:
        return jsonify({"message": "Authorization header missing"}), 401


## endpoints
@app.route("/", methods=["GET"])
def main():
    return "Hello, Respect Weather API!"


@app.route("/forecasts", methods=["GET"])
def get_data():
    longitude = request.args.get("longitude", type=float)
    latitude = request.args.get("latitude", type=float)
    publication_date = request.args.get("publication_date")

    min_latitude = int(latitude)
    max_latitude = int(latitude) + 1

    min_longitude = int(longitude)
    max_longitude = int(longitude) + 1

    query = f"""
    SELECT
    *
    FROM `meteo_dataset.gefs`
    WHERE time = '{publication_date} 00:00:00 UTC'
    and latitude in ({min_latitude}, {max_latitude})
    and longitude in ({min_longitude}, {max_longitude})
    order by time, valid_time
    """

    df = pandas_gbq.read_gbq(query, progress_bar_type=None)

    csv_data = df.to_csv(index=False)
    response = make_response(csv_data)
    response.headers["Content-Type"] = "text/csv"

    return response


@app.route("/favourites", methods=["GET"])
def get_favourites():
    authorization_result = authorize()
    if type(authorization_result) == tuple:
        return authorization_result
    else:
        user_id = authorization_result

    favourites = list_favourites(user_id)
    return jsonify(favourites), 200


@app.route("/favourites/<int:location_id>", methods=["PUT", "DELETE"])
def modify_favourite(location_id):
    authorization_result = authorize()
    if type(authorization_result) == tuple:
        return authorization_result
    else:
        user_id = authorization_result

    if request.method == "PUT":
        add_favourite(user_id, location_id)
    elif request.method == "DELETE":
        remove_favourite(user_id, location_id)

    return jsonify({"success": True}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
