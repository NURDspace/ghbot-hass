#! /usr/bin/python3

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

from hasscfg import *
import json
import paho.mqtt.client as mqtt
import random
import time
import urllib.parse
import urllib.request

# hasscfg.py should contain:
#token        = '...'
#api_url      = '...'

import socket
import sys

mqtt_server  = 'mqtt.nurd.space'
topic_prefix = 'GHBot/'
channels     = ['nurdbottest', 'nurds']
prefix       = '!'

prev_space_state = None

def call_hass(sensor, payload = None):
    url        = api_url + sensor
    headers    = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token }

    if payload != None:
        req    = urllib.request.Request(url, data=payload.encode('ascii'), headers=headers)
    else:
        req    = urllib.request.Request(url, data=None, headers=headers)

    with urllib.request.urlopen(req) as response:
        return json.loads(response.read())

    return None

def gas():
    try:
        total = call_hass('states/sensor.gas_meter_gas')
        return float(total['state'])
    except Exception as e:
        print(e)
    return None

open_gas_start = gas()
closed_gas_start = gas()

def electries():
    try:
        total = call_hass('states/sensor.p1_meter_energy_import')
        return float(total['state'])
    except Exception as e:
        print(e)
    return None

open_electries_start = electries()
closed_electries_start = electries()

def send_bot(txt):
    for channel in channels:
        response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'
        client.publish(response_topic, txt)

def on_message(client, userdata, message):
    global open_gas_start
    global closed_gas_start
    global open_electries_start
    global closed_electries_start
    global prev_space_state

    text = message.payload.decode('utf-8')
    space_state = True if text == '1' else False

    if space_state != prev_space_state:
        prev_space_state = space_state

        current_gas = gas()

        if space_state == False:
            if current_gas != None:
                closed_gas_start = current_gas
                if open_gas_start != None:
                    if random.randint(0, 10) == 3:
                        send_bot(f'Space is now closed. We used aproximately {current_gas - open_gas_start:.4f} m3 gas (WITTE WEL WA DA KOST?!).')
                    else:
                        send_bot(f'Space is now closed. We used aproximately {current_gas - open_gas_start:.4f} m3 gas while open.')
        elif current_gas != None:
            open_gas_start = current_gas
            send_bot(f'Space is now open. We used aproximately {current_gas - closed_gas_start:.4f} m3 gas while closed.')

        current_electries = electries()

        if space_state == False:
            if current_electries != None:
                closed_electries_start = current_electries
                if open_electries_start != None:
                    send_bot(f'We used aproximately {current_electries - open_electries_start:.4f} kWh while open.')
        elif current_electries != None:
            open_electries_start = current_electries
            send_bot(f'We used aproximately {current_electries - closed_electries_start:.4f} kWh while closed.')

def on_connect(client, userdata, flags, rc):
    client.subscribe(f'space/statedigit')

client = mqtt.Client(f'{socket.gethostname()}_{sys.argv[0]}', clean_session=False)
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=1883, keepalive=4, bind_address='')
client.loop_forever()
