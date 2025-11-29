#! /usr/bin/python3

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

from hasscfg import *
import json
import paho.mqtt.client as mqtt
import random
import requests
import threading
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

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'
    client.publish(target_topic, 'cmd=kostdat|descr=Wat kost dat?')

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

def td_to_str(td):
    if td < 7200:
        return f'{td:.2f} seconds'
    if td < 86400:
        return f'{td / 3600:.2f} hours'
    return f'{td / 86400:.2f} days'

def on_message(client, userdata, message):
    global open_gas_start
    global closed_gas_start
    global open_electries_start
    global closed_electries_start
    global prev_space_state
    global prev_space_state_change

    print(message.topic, message.payload)

    try:
        text = message.payload.decode('utf-8')

        now = time.time()
        time_diff = now - prev_space_state_change
        time_diff_str = td_to_str(time_diff)

        current_gas = gas()
        current_electries = electries()
        prices = get_prices()

        print(prices, current_gas, current_electries)

        if 'space/statedigit' in message.topic:
            space_state = True if text == '1' else False

            if space_state != prev_space_state:
                prev_space_state = space_state
                prev_space_state_change = now

                output = ''

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
        else:
            topic = message.topic[len(topic_prefix):]

            if topic == 'from/bot/command' and text == 'register':
                announce_commands(client)
                return

            if len(text) == 0:
                return

            parts   = topic.split('/')
            channel = parts[2] if len(parts) >= 3 else 'nurds'
            nick    = parts[3] if len(parts) >= 4 else 'jemoeder'

            if text[0] != prefix:
                return

            command = text[1:].split(' ')[0]

            if channel in channels or (len(channel) >= 1 and channel[0] == '\\'):
                response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'

                if command == 'kostdat':
                    gass_diff = None
                    if prev_space_state == False:
                        gass_diff = current_gas - open_gas_start
                    elif current_gas != None:
                        gass_diff = current_gas - closed_gas_start

                    stroom_diff = None
                    if prev_space_state == False:
                        stroom_diff = current_electries - open_electries_start
                    elif current_electries != None:
                        stroom_diff = current_electries - closed_electries_start

                    output = f'Space state duration: {time_diff_str}'

                    if not stroom_diff is None and not prices[0] is None:
                        output += f' Electricity cost us: {stroom_diff * prices[0]:.2f} euro.'
                    if not gass_diff is None and not prices[1] is None:
                        output += f' Gas cost us: {gass_diff * prices[1]:.2f} euro.'

                    response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'
                    client.publish(response_topic, output)

    except Exception as e:
        send_bot(f'EXCEPTION (gas): {e}')

def on_connect(client, userdata, flags, rc):
    client.subscribe(f'space/statedigit')
    client.subscribe(f'{topic_prefix}from/irc/#')
    client.subscribe(f'{topic_prefix}from/bot/command')

def announce_thread(client):
    while True:
        try:
            time.sleep(4.1)
            announce_commands(client)
        except Exception as e:
            print(f'Failed to announce: {e}')
            time.sleep(0.5)

client = mqtt.Client()
client.on_message = on_message
client.on_connect = on_connect
client.connect(mqtt_server, port=1883, keepalive=4, bind_address='')

t1 = threading.Thread(target=announce_thread, args=(client,))
t1.start()

client.loop_forever()
