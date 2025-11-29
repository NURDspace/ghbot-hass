#! /usr/bin/python3

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

from hasscfg import *
import json
import paho.mqtt.client as mqtt
import random
import requests
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
prev_space_state_change = time.time()

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

# (electricity, gas)
def get_prices():
#    headers = { 'User-Agent': 'nurdbot' }
#    r = requests.get('http://stofradar.nl:9001/electricity/price', timeout=2, headers=headers)
#    j = json.loads(r.content.decode('ascii'))

    # per 1 april 2025
    return (0.16 + 0.14762, 1.41882)

def on_message(client, userdata, message):
    global open_gas_start
    global closed_gas_start
    global open_electries_start
    global closed_electries_start
    global prev_space_state
    global prev_space_state_change

    try:
        text = message.payload.decode('utf-8')
        space_state = True if text == '1' else False

        if space_state != prev_space_state:
            prev_space_state = space_state
            now = time.time()
            time_diff = now - prev_space_state_change
            prev_space_state_change = now

            current_gas = gas()

            output = ''

            time_diff_str = ''
            if time_diff < 7200:
                time_diff_str = f'{time_diff:.2f} seconds'
            elif time_diff < 86400:
                time_diff_str = f'{time_diff / 3600:.2f} hours'
            else:
                time_diff_str = f'{time_diff / 86400:.2f} days'

            prices = get_prices()
            gass_diff = None
            if space_state == False:
                if current_gas != None:
                    closed_gas_start = current_gas
                    if open_gas_start != None:
                        gass_diff = current_gas - open_gas_start
                        output += f'Space is now closed after {time_diff_str}. We used {gass_diff:.4f} m3 gas while open ({gass_diff * 3600/ time_diff:.4f} m3/hour)'
            elif current_gas != None:
                gass_diff = current_gas - closed_gas_start
                open_gas_start = current_gas
                output += f'Space is now open, was closed for {time_diff_str}. We used {gass_diff:.4f} m3 gas while closed ({gass_diff * 3600/ time_diff:.4f} m3/hour)'
            if output == '':
                output += f'Space is now closed after {time_diff_str}. It looks like we used no gas'

            current_electries = electries()

            output += ' '

            stroom_diff = None
            if space_state == False:
                if current_electries != None:
                    closed_electries_start = current_electries
                    if open_electries_start != None:
                        stroom_diff = current_electries - open_electries_start
                        output += f'and {stroom_diff:.4f} kWh electricity ({stroom_diff * 3600 / time_diff:.4f} kWh/hour).'
            elif current_electries != None:
                stroom_diff = current_electries - closed_electries_start
                open_electries_start = current_electries
                output += f'and {current_electries - closed_electries_start:.4f} kWh electricity ({stroom_diff * 3600  / time_diff:.4f} kWh/hour).'
            else:
                output += '.'

            if not stroom_diff is None and not prices[0] is None:
                output += f' Electricity cost us: {stroom_diff * prices[0]:.2f} euro.'
            if not gass_diff is None and not prices[1] is None:
                output += f' Gas cost us: {gass_diff * prices[1]:.2f} euro.'

            send_bot(output)

    except Exception as e:
        send_bot(f'EXCEPTION (gas): {e}')

def on_connect(client, userdata, flags, rc):
    client.subscribe(f'space/statedigit')

client = mqtt.Client()
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=1883, keepalive=4, bind_address='')
client.loop_forever()
