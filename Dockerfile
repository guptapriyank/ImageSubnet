FROM python:3.10

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt && apt install nodejs npm -y && npm install -g pm2 && pip install bittensor

# Copy the source code into the container.
COPY . .

# Expose the port that the application listens on.
EXPOSE 3000

# Run the application.
ENTRYPOINT python ./ComfyUI/main.py --listen --port 10030 & python ./miners/comfy/miner.py --netuid 5 --comfyui.port 10030 --subtensor.chain_endpoint wss://bittensor-finney.api.onfinality.io/public-ws --subtensor.network local  --wallet.name ruvo --wallet.hotkey ruvo1
