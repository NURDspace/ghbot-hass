#! /usr/bin/python3

# either install 'python3-paho-mqtt' or 'pip3 install paho-mqtt'

import arrow
from hasscfg import *
import json
import paho.mqtt.client as mqtt
import re
import socket
import threading
import time
import urllib.parse
import urllib.request

# hasscfg.py should contain:
#token        = '...'
#api_url      = '...'


mqtt_server  = 'mqtt.vm.nurd.space'
topic_prefix = 'GHBot/'
channels     = ['nurdbottest', 'nurds', 'nurdsbofh']
prefix       = '!'

last_ring    = None

ignore_devices = []

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

def announce_commands(client):
    target_topic = f'{topic_prefix}to/bot/register'

    client.publish(target_topic, 'cmd=sth|agrp=members|descr=Space climate')
    client.publish(target_topic, 'cmd=octoprint|agrp=members|descr=How is the 3D print going?')
    client.publish(target_topic, 'cmd=ot|agrp=members|descr=Opentherm (status of central heating)')
    client.publish(target_topic, 'cmd=ot-set|agrp=members|descr=Set thermostat of central heating')
    client.publish(target_topic, 'cmd=sensor|agrp=members|descr=Get status of a sensor')
    client.publish(target_topic, 'cmd=sun|agrp=members|descr=All about the sun')
    client.publish(target_topic, 'cmd=power|agrp=members|descr=NURDSpace power usage')
    client.publish(target_topic, 'cmd=toggle|agrp=members|descr=Toggle power state of a device in NURDSpace')
    client.publish(target_topic, 'cmd=toggle-list|agrp=members|descr=Get a list of devices that can be toggled in NURDSpace')
    client.publish(target_topic, 'cmd=who|agrp=members|descr=Who is in NURDSpace currently? (see https://nurdspace.nl/Jarvis#Device_tracker)')
    client.publish(target_topic, 'cmd=mpdtube|agrp=members|descr=Adds a song from youtube to the playlist.')
    client.publish(target_topic, 'cmd=ticker|agrp=members|descr=Show a text on the tickers/led-scrollers in the space.')

def cmd_octoprint(client, response_topic):
    try:
        printing        = call_hass('states/binary_sensor.printer3_printing')['state']
        nozzle_temp     = call_hass('states/sensor.printer3_actual_tool0_temp')['state']
        bed_temp        = call_hass('states/sensor.printer3_actual_bed_temp')['state']
        percentage_done = call_hass('states/sensor.printer3_job_percentage')['state']

        if printing == 'off':
            client.publish(response_topic, f'Printer3 is not printing now. Bed temp: {bed_temp}, nozzle temp: {nozzle_temp}')

        else:
            # percentage
            # time_elapsed = datetime.timedelta(seconds=int((call_hass('states/sensor.printer3_time_elapsed')['state'])))
            # time_remaining = datetime.timedelta(seconds=int((call_hass('states/sensor.printer3_time_remaining')['state'])))
            client.publish(response_topic, f'Printer3 is {percentage_done}%% done. Bed temp: {bed_temp}, nozzle temp: {nozzle_temp}, elapsed time: %s, Time remaining: %s' % (0, 0))

    except Exception as e:
        client.publish(response_topic, f'Exception during "octoprint": {e}, line number: {e.__traceback__.tb_lineno}')

def cmd_sth(client, response_topic):
    try:
        bar = [
            call_hass('states/sensor.bar_temperature')['state'],
            call_hass('states/sensor.bar_humidity')['state']
        ]

        rookhok = [
            call_hass('states/sensor.smokeroom_temperature')['state'],
            call_hass('states/sensor.smokeroom_humidity')['state']
        ]

        zaal1 = [
            call_hass('states/sensor.zaal_1_temperature')['state'],
            call_hass('states/sensor.zaal_1_humidity')['state']
        ]

        zaal1_window = [
            call_hass('states/sensor.zaal_1_raam_temperature')['state'],
            call_hass('states/sensor.zaal_1_raam_humidity')['state']
        ]

        zaal3 = [
            call_hass('states/sensor.zaal_3_temperature')['state'],
            call_hass('states/sensor.zaal_3_humidity')['state']
        ]

        zaal2 = [
            call_hass('states/sensor.zaal_2_temperature')['state'],
            call_hass('states/sensor.zaal_2_humidity')['state']
        ]

        mustu = [
            call_hass('states/sensor.studio_temperature')['state'],
            call_hass('states/sensor.studio_humidity')['state']
        ]

        out = str('bar: %s°C/%s%% rookhok: %s°C/%s%% zaal1: %s°C/%s%% zaal1_window: %s°C/%s%% zaal3: %s°C/%s%% zaal2: %s°C/%s%% muziekstudio: %s°C/%s%%') % (bar[0], bar[1], rookhok[0], rookhok[1], zaal1[0], zaal1[1], zaal1_window[0], zaal1_window[1], zaal3[0], zaal3[1], zaal2[0], zaal2[1], mustu[0], mustu[1])

        client.publish(response_topic, out)

    except Exception as e:
        client.publish(response_topic, f'Exception during "sth": {e}, line number: {e.__traceback__.tb_lineno}')

def cmd_ot(client, response_topic):  # opentherm
    try:
        watertemp  = call_hass('states/sensor.ch_water_temp_boiler_thermostaat')['state']
        returntemp = call_hass('states/sensor.return_water_temp_boiler_thermostaat')['state']
        otgw       = call_hass('states/climate.thermostaat')

        client.publish(response_topic, 'water temp: %s°C, return temp: %s°C, heater: %s, kitchen temp: %s°C, setpoint: %s°C, last setpoint update: %s' % (watertemp, returntemp, otgw['state'], otgw['attributes']['current_temperature'], otgw['attributes']['temperature'], arrow.get(otgw['last_updated']).to('Europe/Amsterdam').format()))

    except Exception as e:
        client.publish(response_topic, f'Exception during "sth": {e}, line number: {e.__traceback__.tb_lineno}')

def cmd_ot_set(client, response_topic, value):  # opentherm
    try:
        if value == None:
            client.publish(response_topic, 'Parameter missing')

            return

        temp = float(value)

        if temp > 23. or temp < 1.:
            client.publish(response_topic, 'Temperature range is 1...23°C')

        else:
            payload = '{ "entity_id": "climate.thermostaat", "temperature": "%s"}' % temp

            output = call_hass('services/climate/set_temperature', payload)

            if len(output) > 0:
                client.publish(response_topic, 'Thermostat set to: %s°C' % output[0]['attributes']['temperature'])

            else:
                client.publish(response_topic, 'No changes made')

    except ValueError as v:
        client.publish(response_topic, 'A number is required')

    except Exception as e:
        client.publish(response_topic, f'Exception during "ot-set": {e}, line number: {e.__traceback__.tb_lineno}')

def cmd_sensor(client, response_topic, value):
    if value == None:
        client.publish(response_topic, 'Parameter (sensor-name) missing')

        return

    try:
        states = call_hass('states')

    except Exception as e:
        client.publish(response_topic, f'Exception during "sensor": {e}, line number: {e.__traceback__.tb_lineno}')

    else:
        output = []

        for sensor in list(filter(lambda d: d['entity_id'].lower().find(value.lower()) != -1 and d['entity_id'].find('sensor') != -1, states)):
            if 'device_class' in sensor['attributes']:
                if sensor['attributes']['device_class'] == 'door':
                    sensor['state'] = 'open' if sensor['state'] == 'on' else 'closed'

                    if sensor['attributes']['device_class'] == 'lock':
                        if sensor['state'] == 'Open':
                            sensor['state'] = 'Unlocked'
                        else:
                            sensor['state'] = 'Locked'

            if 'unit_of_measurement' in sensor['attributes']:
                if 'friendly_name' in sensor['attributes']:
                    output.append(sensor['attributes']['friendly_name'] + ': ' + sensor['state'] + ' ' + sensor['attributes']['unit_of_measurement'])
                else:
                    output.append(sensor['entity_id'] + ': ' + sensor['state'] + ' ' + sensor['attributes']['unit_of_measurement'])

            else:
                if 'friendly_name' in sensor['attributes']:
                    output.append(sensor['attributes']['friendly_name'] + ': ' + sensor['state'])
                else:
                    output.append(sensor['entity_id'] + ': ' + sensor['state'])

        if len(output):
            client.publish(response_topic, ', '.join(output))

        else:
            client.publish(response_topic, 'No sensor found')

def cmd_sun(client, response_topic):
    try:
        states = call_hass('states/sun.sun')

    except Exception as e:
        client.publish(response_topic, f'Exception during "sun": {e}, line number: {e.__traceback__.tb_lineno}')

    else:
        if states['state'] == "above_horizon":
            client.publish(response_topic, 'The sun will set at %s Current elevation: %s°' % (states['attributes']['next_setting'], states['attributes']['elevation']))

        else:
            client.publish(response_topic, 'The sun will rise at ' + states['attributes']['next_rising'])

def cmd_power(client, response_topic):
    try:
        groepa = call_hass('states/sensor.groepenkast_a_power')
        groepb = call_hass('states/sensor.groepenkast_b_power')

        totaal = call_hass('states/sensor.power')

        #poe    = call_hass('states/sensor.switch_core_poe_power')
        poe    = dict()
        poe['state'] = -1.

        laag   = call_hass('states/sensor.energy_monthly_offpeak')
        hoog   = call_hass('states/sensor.energy_monthly_peak')
        dlaag  = call_hass('states/sensor.energy_daily_offpeak')
        dhoog  = call_hass('states/sensor.energy_daily_peak')

        kwh    = float(laag['state'])  + float(hoog['state'])
        dkwh   = float(dlaag['state']) + float(dhoog['state'])

        client.publish(response_topic, 'Groep A: %sW Groepen B: %sW POE: %.2fW Totaal: %sW Day: %.2fkWh Month: %.2fkWh' % (groepa['state'], groepb['state'], float(poe['state']) / 1000, totaal['state'], dkwh, kwh))

    except Exception as e:
        client.publish(response_topic, f'Exception during "power": {e}, line number: {e.__traceback__.tb_lineno}')

def get_togglelist():
    states   = call_hass('states')
    switches = []
    friendly = []
    state     = []

    for switch in list(filter(lambda d: d['entity_id'].find('switch') != -1, states)):
        if 'friendly_name' not in switch['attributes']:
            continue

        friendly.append(switch['attributes']['friendly_name'])

        state.append(switch['state'])

        switches.append(switch['entity_id'])

    return switches, friendly, state

def get_togglelist_filtered():
    """ Filter based on devices we want to ignore, sorted based on friendly name """
    devices          = []
    devices_filtered = []

    togglelist       = get_togglelist()

    for device, friendly_name, state in zip(*togglelist):
        ignore_device = False

        for ignore_regexp in ignore_devices:
            if re.search(ignore_regexp, device):
                ignore_device = True

                break

        if not ignore_device:
            devices.append({"device": device, "friendly_name": friendly_name, "state": state})

    # Itterate over the devices again and add the id based on sorted by friendly_name
    for pos, device in enumerate(sorted(devices, key=lambda d:d['friendly_name'])):
        device['id'] = pos + 1
        devices_filtered.append(device)

    return devices_filtered

def toggle_device(device):
    """
        Toggles a device and returns a message of the
        new state to be send to IRC
    """

    try:
        reply = ''

        if device['state'] == 'off':
            reply = 'Switching on %s (id: %s)' % (device['friendly_name'], device['id'])

        elif device['state'] == 'on':
            reply = 'Switching off %s (id: %s)' % (device['friendly_name'], device['id'])

        call_hass('services/switch/toggle', '{"entity_id": "%s"}' % device['device'])

        return reply

    except Exception as e:
        return f'toggle_device({device}) failed: {e}'

def find_devices(devices, match):
    devices_found = []

    for device in devices:
        if device_match(device, match):
            devices_found.append(device)

    return devices_found

def cmd_toggle(client, response_topic, value):
    if value == None:
        client.publish(response_topic, 'Enter a space separated list of device names. See "!toggle-list" for a list.')

        return

    try:
        togglelist = get_togglelist_filtered()

        response = []

        for device_name in value.split(' '):
            # When the user wants to toggle based on array index
            if device_name.isdigit():
                device_pos = int(device_name) - 1

                # Make sure we can't go out of bounds
                if device_pos < 0:
                    device_pos = 0

                elif device_pos >= len(togglelist):
                    device_pos = len(togglelist) - 1

                response.append(toggle_device(togglelist[device_pos]))

            else: # Match based on word
                devices = find_devices(togglelist, device_name)

                if len(devices) == 1:
                    response.append(toggle_device(devices[0]))

                # found too many matches
                else:
                    if len(devices) == 0:
                        resp = "Can't find any devices."

                    else:
                        resp = "Too many devices; pick: "

                        for device in devices:
                           resp += "%s: %s, " % (device['id'], device['friendly_name'])

                    response.append(resp[:-1])

        client.publish(response_topic, ', '.join(response))

    except Exception as e:
        client.publish(response_topic, f'Exception during "toggle": {e}, line number: {e.__traceback__.tb_lineno}')

def device_match(device, match):
    """ Search both the friendly_name and device name using regex 
        and return True if either matches."""

    if re.search(match, device['device'], re.IGNORECASE):
        return True

    if re.search(match, device['friendly_name'], re.IGNORECASE):
        return True

    return False

def cmd_toggle_list(client, response_topic, value):
    try:
        response      = []
        devices_found = []

        for pos, device in enumerate(get_togglelist_filtered()):
            # filter based on user input
            if len(value) >= 1:
                if device['device'] not in devices_found and device_match(device, value):
                    response.append("%s: %s" % (pos + 1, device['friendly_name']))

                    devices_found.append(device['device'])

            else:
                # Just shows everything
                response.append("%s: %s" % (pos + 1, device['friendly_name']))

        if len(response) >= 1:
            client.publish(response_topic, ', '.join(response))

        else:
            client.publish(response_topic, f"Can't find any matching devies for search-query '{value}'")

    except Exception as e:
        client.publish(response_topic, f'Exception during "toggle-list": {e}, line number: {e.__traceback__.tb_lineno}')

def cmd_who(client, response_topic):
    try:
        states = call_hass('states')

        spacestatesensor = call_hass('states/binary_sensor.space_state')

        if spacestatesensor['state'] == 'off':
            client.publish(response_topic, 'Note: the space is closed')

        persons = []

        for person in list(filter(lambda d: d['entity_id'].startswith('person') and d['state'] == 'home', states)):
            persons.append(person['attributes']['friendly_name'])

        if persons:
            client.publish(response_topic, 'People in the space: ' + ', '.join(persons))

        else:
            client.publish(response_topic, 'The space is empty.')

    except Exception as e:
        client.publish(response_topic, f'Exception during "who": {e}, line number: {e.__traceback__.tb_lineno}')

def cmd_mpdtube(client, response_topic, nick, channel, value):
    topic = 'mpd/youtube-dl/play/nurdbot'

    try:
        if '!' in nick:
            nick = nick[0:nick.find('!')]

        payload = json.dumps({'user': str(nick), 'query': value, 'channel': channel})

        client.publish(response_topic, f'{value} requested')

        client.publish(topic, payload)

    except Exception as e:
        client.publish(response_topic, f'Exception during "mpdtube": {e}, line number: {e.__traceback__.tb_lineno}')

def cmd_ticker(client, response_topic, value):
    try:
        if call_hass('states/switch.epc4_2')['state'] == 'off':
            client.publish(response_topic, 'Ticker in zaal 1 is off')

            return

        if value == None:
            client.publish(response_topic, 'Usage: !ticker <text to show on tickers>')

            return

        UDP_IP = 'ticker-proxy.vm.nurd.space'  # ticker proxy
        UDP_PORT = 5001

        txt = value.strip()
        txt = txt.replace('$i$', '')
        txt = txt.encode('utf-8', 'ignore')

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        s.sendto(txt, (UDP_IP, UDP_PORT))

        s.close()

        client.publish(response_topic, 'Your text has been sent to the ticker-proxy.')

    except Exception as e:
        client.publish(response_topic, f'Exception during "ticker": {e}, line number: {e.__traceback__.tb_lineno}')

def on_message(client, userdata, message):
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

    if text[0] != prefix:
        return

    try:
        parts   = topic.split('/')
        channel = parts[2] if len(parts) >= 3 else 'nurds'
        nick    = parts[3] if len(parts) >= 4 else 'jemoeder'

        parts     = text.split(' ')
        command   = parts[0][1:]
        value     = parts[1]  if len(parts) >= 2 else None
        value_all = parts[1:] if len(parts) >= 2 else None

        if channel in channels:
            response_topic = f'{topic_prefix}to/irc/{channel}/privmsg'

            if command == 'sth':
                cmd_sth(client, response_topic)

            elif command == 'octoprint':
                cmd_octoprint(client, response_topic)

            elif command == 'ot':
                cmd_ot(client, response_topic)

            elif command == 'ot-set':
                cmd_ot_set(client, response_topic, value)

            elif command == 'sensor':
                cmd_sensor(client, response_topic, value)

            elif command == 'sun':
                cmd_sun(client, response_topic)

            elif command == 'power':
                cmd_power(client, response_topic)

            elif command == 'toggle':
                cmd_toggle(client, response_topic, value)

            elif command == 'toggle-list':
                cmd_toggle_list(client, response_topic, value)

            elif command == 'who':
                cmd_who(client, response_topic)

            elif command == 'mpdtube':
                cmd_mpdtube(client, response_topic, nick, channel, ' '.join(value_all))

            elif command == 'ticker':
                cmd_ticker(client, response_topic, ' '.join(value_all))

    except Exception as e:
        client.publish(response_topic, f'Exception during "on_message": {e}, line number: {e.__traceback__.tb_lineno}')

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        client.subscribe(f'{topic_prefix}from/irc/#')

        client.subscribe(f'{topic_prefix}from/bot/command')

def announce_thread(client):
    while True:
        try:
            announce_commands(client)

            time.sleep(2.5)

        except Exception as e:
            print(f'Failed to announce: {e}')

client = mqtt.Client()
client.connect(mqtt_server, port=1883, keepalive=4, bind_address='')
client.on_message = on_message
client.on_connect = on_connect

t = threading.Thread(target=announce_thread, args=(client,))
t.start()

client.loop_forever()
