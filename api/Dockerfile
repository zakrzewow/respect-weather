# Use the official image as a parent image
FROM python:3.9

# Set the working directory
WORKDIR /api

# Copy the current directory contents into the container at /api
COPY . /api

# Install the necessary packages
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8080 available to the world outside this container
EXPOSE 8080

# Run streamlit when the container launches
CMD ["flask", "--app", "api", "run", "--host=0.0.0.0", "--port=8080"]
