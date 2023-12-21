# The MIT License (MIT)
# Copyright © 2021 Yuma Rao
# Copyright © 2023 Opentensor Foundation
# Copyright © 2023 Opentensor Technologies Inc

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the “Software”), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
import io
import json
import random
import urllib
import uuid
from typing import List

import imagehash
import requests
import torchvision.transforms as transforms
from PIL import Image

from config import config
from protocol import *

# this object is downloaded from comfyui "Save (API Format)", must enable dev mode
# open prompts/text_to_image.txt
print(config)
server_address = config.comfyui.address + ":" + str(config.comfyui.port)
client_id = str(uuid.uuid4())
print(server_address)


# returns list of images
def t2i(synapse: TextToImage) -> List[Image.Image]:
    prompt = synapse.text
    negative_prompt = synapse.negative_prompt
    height = synapse.height
    width = synapse.width
    num_images_per_prompt = synapse.num_images_per_prompt

    if synapse.seed == -1:
        seed = random.randint(0, 2 ** 32 - 1)
    else:
        seed = synapse.seed

    bt.logging.trace(f"Calling text to image. prompt: {prompt}, "
                     f"negative_prompt: {negative_prompt}, seed: {seed}, samples: {num_images_per_prompt}, "
                     f"width: {width}, height: {height}")

    api_key = config.stablediffusion.apikey

    if api_key is None:
        raise Exception("stablediffusionapi.apikey can not be null")

    api_url = config.stablediffusion.t2i_url

    api_payload = {
        'key': api_key,
        'prompt': prompt,
        'negative_prompt': negative_prompt,
        'seed': seed,
        'num_inference_steps': '20',
        "samples": num_images_per_prompt,
        'width': width,
        'height': height
    }

    api_payload = {k: v for k, v in api_payload.items() if v}

    headers = {
        'Content-Type': 'application/json'
    }

    json_response = requests.request("POST", api_url, headers=headers, data=json.dumps(api_payload)).json()

    if json_response['status'] == 'success':
        image_urls = json_response['output']
    else:
        raise Exception(
            f"An error occurred while calling text to image stablediffusionapi, prompt: {prompt}, "
            f"negative_prompt: {negative_prompt}, seed: {seed}, samples: {num_images_per_prompt}, "
            f"width: {width}, height: {height}, response error message: {json_response['message']}, "
            f"tip: {json_response['tip']} ")

    images = []
    for url in image_urls:
        try:
            response = requests.get(url)
            image = Image.open(io.BytesIO(response.content))
            if image.size[0] != width or image.size[1] != height:
                image = image.resize((width, height), Image.ANTIALIAS)
            images.append(image)
        except Exception as e:
            raise Exception(f"An error occurred while loading image: {e}")
    return images


def get_cloudflare_upload_url(account_id, api_token, image_byte_stream, uid):
    """
    upload an image to Cloudflare using bytes buffer.

    :param account_id: Cloudflare account ID
    :param api_token: Cloudflare API token
    :param image_byte_stream: byte steam of image
    :param uid: name for the image
    :return: image url and image id
    """

    # URL for Cloudflare's image optimization API
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1"

    # Headers including the authorization token
    headers = {
        "Authorization": f"Bearer {api_token}"
    }

    # Prepare the image data as multipart/form-data
    files = {'file': (f'{uid}.png', image_byte_stream, 'image/png')}

    # Send the POST request
    response = requests.post(url, files=files, headers=headers).json()

    if response["success"]:
        return response["result"]["variants"][0], response["result"]["id"]
    else:
        raise Exception(f'cloudflare upload failed, {response["errors"]}')


def delete_cloudflare_image(account_id, api_token, image_id):
    """
    Deletes an image from Cloudflare using the Image ID.

    :param account_id: Cloudflare account ID
    :param image_id: ID of the image to be deleted
    :param api_token: Cloudflare API token
    :return: Response from the Cloudflare API success status
    """

    # URL for deleting an image
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/images/v1/{image_id}"

    # Headers including the authorization token
    headers = {
        "Authorization": f"Bearer {api_token}"
    }

    # Send the DELETE request
    response = requests.delete(url, headers=headers).json()

    return response["success"]


def i2i(synapse: ImageToImage) -> List[Image.Image]:
    print("inside image 2 image")
    prompt = synapse.text
    negative_prompt = synapse.negative_prompt
    height = synapse.height
    width = synapse.width
    num_images_per_prompt = synapse.num_images_per_prompt

    if synapse.seed == -1:
        seed = random.randint(0, 2 ** 32 - 1)
    else:
        seed = synapse.seed

    bt.logging.trace(f"Calling image to image. prompt: {prompt}, "
                     f"negative_prompt: {negative_prompt}, seed: {seed}, samples: {num_images_per_prompt}, "
                     f"width: {width}, height: {height}")

    # right now, image is bt.Tensor, we need to deserialize it and convert to PIL image
    image = bt.Tensor.deserialize(synapse.image)
    pil_img = transforms.ToPILImage()(image)

    # generate hash for image using dhash
    image_hash = imagehash.dhash(pil_img)
    image_hash = str(image_hash)

    # generate uid from hash
    uid = uuid.uuid5(uuid.NAMESPACE_DNS, image_hash)
    uid = str(uid)

    # Save the image to an in-memory bytes buffer
    byte_stream = io.BytesIO()
    pil_img.save(byte_stream, format="png")

    # cloudflare config
    account_id = config.cloudflare.account_id
    api_token = config.cloudflare.api_token

    if account_id is None or api_token is None:
        raise Exception("Either cloudflare account_id or cloudflare api_token are not defined")

    # get cloudflare uploaded image url
    init_image_url, image_id = get_cloudflare_upload_url(account_id, api_token, byte_stream, uid)

    api_key = config.stablediffusion.apikey

    if api_key is None:
        raise Exception("stablediffusionapi.apikey can not be null")

    api_url = config.stablediffusion.i2i_url

    # denoise = {"low": 0.8, "medium": 0.5, "high": 0.15}.get(synapse.similarity, 0.0)

    api_payload = {
        'key': api_key,
        'prompt': prompt,
        'negative_prompt': negative_prompt,
        "init_image": init_image_url,
        'seed': seed,
        'num_inference_steps': '25',
        "samples": num_images_per_prompt,
        'width': width,
        'height': height
    }

    api_payload = {k: v for k, v in api_payload.items() if v}

    headers = {
        'Content-Type': 'application/json'
    }

    json_response = requests.request("POST", api_url, headers=headers, data=json.dumps(api_payload)).json()

    if json_response['status'] == 'success':
        image_urls = json_response['output']
    else:
        raise Exception(
            f"An error occurred while calling image to image stablediffusionapi, prompt: {prompt}, "
            f"negative_prompt: {negative_prompt}, init_image: {init_image_url}, seed: {seed}, "
            f"samples: {num_images_per_prompt}, width: {width}, height: {height}, "
            f"response error message: {json_response['message']}, tip: {json_response['tip']} ")

    # cleanup of uploaded images to cloudflare
    delete_cloudflare_image(account_id, api_token, image_id)

    images = []
    for url in image_urls:
        try:
            response = requests.get(url)
            image = Image.open(io.BytesIO(response.content))
            images.append(image)
        except Exception as e:
            raise Exception(f"An error occurred while loading image: {e}")
    return images


def queue_prompt(prompt):
    p = {"prompt": prompt, "client_id": client_id}
    data = json.dumps(p).encode('utf-8')
    req = urllib.request.Request("http://{}/prompt".format(server_address), data=data)
    return json.loads(urllib.request.urlopen(req).read())


def get_image(filename, subfolder, folder_type):
    data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    url_values = urllib.parse.urlencode(data)
    with urllib.request.urlopen("http://{}/view?{}".format(server_address, url_values)) as response:
        return response.read()


def get_history(prompt_id):
    with urllib.request.urlopen("http://{}/history/{}".format(server_address, prompt_id)) as response:
        return json.loads(response.read())


def get_images(ws, prompt):
    prompt_id = queue_prompt(prompt)['prompt_id']
    output_images = {}
    while True:
        out = ws.recv()
        if isinstance(out, str):
            message = json.loads(out)
            if message['type'] == 'executing':
                data = message['data']
                if data['node'] is None and data['prompt_id'] == prompt_id:
                    break  # Execution is done
        else:
            continue  # previews are binary data

    history = get_history(prompt_id)[prompt_id]
    for o in history['outputs']:
        for node_id in history['outputs']:
            node_output = history['outputs'][node_id]
            if 'images' in node_output:
                images_output = []
                for image in node_output['images']:
                    image_data = get_image(image['filename'], image['subfolder'], image['type'])
                    images_output.append(image_data)
            output_images[node_id] = images_output

    return output_images
