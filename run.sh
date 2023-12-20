python ./ComfyUI/main.py --listen --port 10030 --cpu &
python ./miners/comfy/miner.py --netuid 5 --comfyui.port 10030 --subtensor.chain_endpoint wss://bittensor-finney.api.onfinality.io/public-ws --subtensor.network local  --wallet.name ruvo --wallet.hotkey ruvo1
