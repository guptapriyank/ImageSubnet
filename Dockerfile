FROM python:3.10

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt && pip install bittensor
RUN apt update && apt install nodejs npm -y && npm install -g pm2

# Copy the source code into the container.
COPY . .

# Expose the port that the application listens on.
EXPOSE 3000

# Run the application.
CMD ["bash"]
