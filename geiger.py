#! /usr/bin/python3

# by FvH, released under Apache License v2.0

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'
# also pip3 install homeassistant-api

from homeassistant_api import Client
from hasscfg import *
import paho.mqtt.client as mqtt
import threading
import time

mqtt_server  = 'mqtt.vm.nurd.space'
topic_prefix = 'GHBot/'
channels     = ['nurdbottest', 'nurds', 'nurdsbofh']
prefix       = '!'

measurements = []
timestamps   = []

def poll_thread():
    global measurements
    global timestamps

    last_update  = None

    while True:
        try:
            with Client(api_url, token) as client:
                state = client.get_state(entity_id='sensor.geiger_counter')

                if state.last_updated != last_update:
                    last_update = state.last_updated

                    # 151.5 cpm = about 1uSv/h
                    measurements.append(float(state.state) / 151.5)

                    timestamps.append(state.last_updated.timestamp())

                    while len(measurements) > 300:
                        del measurements[0]
                        del timestamps  [0]

        except Exception as e:
            print(f'poll_thread: {e}')

        time.sleep(5)

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=geigertrend|descr=Show trend of the geiger counter measurements')

# see https://stackoverflow.com/questions/10048571/python-finding-a-trend-in-a-set-of-numbers
def linreg(X, Y):
    """
    return a,b in solution to y = ax + b such that root mean square distance between trend line and original points is minimized
    """
    N = len(X)
    Sx = Sy = Sxx = Syy = Sxy = 0.0
    for x, y in zip(X, Y):
        Sx = Sx + x
        Sy = Sy + y
        Sxx = Sxx + x*x
        Syy = Syy + y*y
        Sxy = Sxy + x*y
    det = Sxx * N - Sx * Sx
    return (Sxy * N - Sy * Sx)/det, (Sxx * Sy - Sx * Sxy)/det

def on_message(client, userdata, message):
    global last_ring
    global prefix

    text = message.payload.decode('utf-8')

    topic = message.topic[len(topic_prefix):]

    if topic == 'from/bot/command' and text == 'register':
        announce_commands(client)

        return

    if topic == 'from/bot/parameter/prefix':
        prefix = text

        return

    if len(text) == 0:
        return

    parts   = topic.split('/')
    channel = parts[2] if len(parts) >= 3 else 'nurds'
    nick    = parts[3] if len(parts) >= 4 else 'jemoeder'

    if text[0] != prefix:
        return

    command = text[1:].split(' ')[0]

    if channel in channels:
        response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'

        if command == 'geigertrend':
            if len(measurements) < 2:
                client.publish(response_topic, 'Not enough measurements performed yet (please wait aprox. 60 seconds to try again)')

            else:
                a, b = linreg(timestamps, measurements)

                client.publish(response_topic, f'Geiger counter: for y = ax + b, a={a:.8e} and b={b:.8e} giving a uSv/h of {a * (time.time() + 3600) + b:.5f} after 1 hour. Calculated over {len(measurements)} measurements in {timestamps[-1] - timestamps[0]:.2f} seconds')

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(f'{topic_prefix}from/irc/#')

        client.subscribe(f'{topic_prefix}from/bot/command')

def announce_thread(client):
    while True:
        try:
            announce_commands(client)

            time.sleep(4.1)

        except Exception as e:
            print(f'Failed to announce: {e}')

client = mqtt.Client()
client.connect(mqtt_server, port=1883, keepalive=4, bind_address="")
client.on_message = on_message
client.on_connect = on_connect

t1 = threading.Thread(target=announce_thread, args=(client,))
t1.start()

t2 = threading.Thread(target=poll_thread)
t2.start()

client.loop_forever()
