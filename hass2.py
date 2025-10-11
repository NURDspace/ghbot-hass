#! /usr/bin/env python3
from __future__ import annotations

import time
import ldap3
import logging
import threading
import paho.mqtt.client as mqtt 
import socket
import os
import httpx
import re
import arrow
import math
import cloudscraper
import requests
import json
from bs4 import BeautifulSoup
from functools import lru_cache
from typing import Dict, List, Tuple, Any, Iterable
import math
# pip3 install httpx cloudscraper bs4

"""
    This is a rewrite of the original hass.py plugin by Melan. (2024)
"""


PLUG_AUTHOR = "Melan"
HASS_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiI0ZGU3ZDNiYWJhNWY0Zjc4YjhmNjFkYzkxYTRmNTc1MSIsImlhdCI6MTU1MjE3NjA1MywiZXhwIjoxODY3NTM2MDUzfQ.vzpS0u4eBr-F4Zi4XoJRpkM3oL61NiDZdNQB21tHlxo'
HASS_URL = 'http://jarvis.vm.nurd.space:8123/api'


class PluginCommand():
    def __init__(self, call, command, descr, agrp="") -> None:
        self.call = call
        self.command = command
        self.descr = descr
        self.author = PLUG_AUTHOR
        self.agrp =  agrp
        self.loc = f"{os.path.basename(__file__)} ({socket.gethostname()})"

class Plugin():
    log = logging.getLogger(os.path.basename(__file__))
     
    def __init__(self) -> None:
        self.mqtt = mqtt.Client()
        self.mqtt.on_message = self.onMqttMessageWrapper
        self.mqtt.on_connect = self.onMqttConnect
    
    def run(self):
        threading.Thread(target=self.backgroundThread).start()
        self.mqtt.connect("mqtt.nurd.space", 1883, 60)
        self.mqtt.loop_forever()
        
    def reply(self, response_topic, text):
        color_pattern = r'[\x02\x0F\x16\x1D\x1F]|\x03(\d{,2}(,\d{,2})?)?'; # regex to strip irc color codes
        logging.info(f"[{response_topic}] :: {re.sub(color_pattern, '', text)}")
        try:
            self.mqtt.publish(response_topic, text)
        except Exception as e:
            self.log.error(f"[{os.path.basename(__file__)}] An exception occurred during mqtt publish ({e}). Line: {e.__traceback__.tb_lineno}")
            import traceback
            traceback.print_exc()

    def backgroundThread(self):
        self.log.info("Background thread starting up.")
        while True:
            self.mqttAnnounceCommands()
            time.sleep(10) # sleep for 10 seconds so we don't spam
    
    def mqttAnnounceCommands(self):
        target_topic = f'GHBot/to/bot/register'

        for plugin in self.plugins:
            command_str = f"cmd={plugin.command}|descr=\"{plugin.descr}|athr={plugin.author}|loc={plugin.loc}\""
            if plugin.agrp:
                command_str += f"|agrp={plugin.agrp}"
            self.mqtt.publish(target_topic, command_str)

    def onMqttConnect(self, client, userdata, flags, rc):
        self.mqtt.subscribe('GHBot/from/irc/#')
        self.mqtt.subscribe('GHBot/to/irc/#')
        self.log.info("Connected to MQTT.")
        self.mqttAnnounceCommands() # announce commands on connect

    def onMqttMessageWrapper(self, client, userdata, message):
        try:
            self.onMqttMessage(client, userdata, message)
        except Exception as e:
            self.log.error(f"[{os.path.basename(__file__)}] An exception occurred during on_message ({e}). Line: {e.__traceback__.tb_lineno}")
            import traceback
            traceback.print_exc()

    def onMqttMessage(self, client, userdata, message):
        text = message.payload.decode('utf-8')
        topic = message.topic[len("GHBot"):]
        parts = topic[6:].split('/')
        command = parts[-1]

        response_topic = f'GHBot/to/irc/{parts[1]}/privmsg'

        for plugin in self.plugins:
            if plugin.command == command:
                self.log.info(f"Executing plugin {plugin.command}")
                try:
                    plugin.call(text, topic, response_topic)
                except Exception as e:
                    import traceback
                    self.log.error(f"[{os.path.basename(__file__)}] An exception occurred during on_message ({e}). Line: {e.__traceback__.tb_lineno}")
                    traceback.print_exc()
                    self.reply(response_topic, f"[\x0309{os.path.basename(__file__)}\x0f] \x0304An exception occurred during on_message ({e})\x0f (Line: \x0308{e.__traceback__.tb_lineno}\x0f)")
                return
     
class hassPlugin(Plugin):
    
    def __init__(self) -> None:
        super().__init__() # call parent constructor
    
        self.plugins = [
           PluginCommand(self.cmd_power, "power", "Display NURDSpace power usage"),
           PluginCommand(self.cmd_who, "who", "Display who is in the space"),
           PluginCommand(self.cmd_sth, "sth", "Display temperature and humidity in the space"),
           PluginCommand(self.cmd_ot, "ot", "Opentherm (status of the central heating)"),
           PluginCommand(self.cmd_ot_set, "ot-set", "Opentherm (Set the setpoint of the central heating)", "members"),
           PluginCommand(self.cmd_sun, "sun", "Display sunrise and sunset times"),
           PluginCommand(self.cmd_calender, "calendar", "Display calendars in HASS"),
           PluginCommand(self.cmd_sensor, "sens", "Display calendars in HASS"),
           PluginCommand(self.cmd_spacehex, "spacehex", "Display the current space color"),
           PluginCommand(self.spacergb, "spacergb", "Set the space color"),
           PluginCommand(self.cmd_regen, "regen", "Display the current rain forecast"),
           PluginCommand(self.cmd_rack, "rack", "Display the rack temp and power usage."),
           PluginCommand(self.cmd_spacestation, "spacestation", "Display the current weatherstation on top of the space"),
           PluginCommand(self.cmd_zaal2wled, "zaal2wled", "Change the colour in zaal 1 to what the rgb sensor sees."),
           PluginCommand(self.cmd_zaalrgb, "zaalrgb", "Change the colour of zaal 1 to r,g,b")
        ]
    
    def request(self, url, asJson=False):
        with httpx.Client() as client:
            r = client.get(url)
            if r.status_code == 200:
                if asJson:
                    return r.json()
                return r.content
            else:
                self.log.error(f"Error requesting URL: {r.status_code} ({url})")
                raise Exception(f"Error requesting URL: {r.status_code} ({url})")
    
    def call_hass(self, sensor, payload=None):
        headers = { "Content-Type": "application/json", 
                   "Authorization": f"Bearer {HASS_TOKEN}",
                   "User-Agent": "NURDBot/1.0 Hass Plugin (By Melan)"}
        
        with httpx.Client() as client:
            URL = f"{HASS_URL}/{sensor}"
            
            if payload:
                r = client.post(URL, headers=headers, json=payload)
            else:
                r = client.get(URL, headers=headers)
            
            if r.status_code == 200:
                return r.json()
            else:
                self.log.error(f"Error calling HASS API: {r.status_code} ({URL})")
                raise Exception(f"Error calling HASS API: {r.status_code} ({URL})")
    
    def hass_find_entities(self, entity_name:str) -> list:
        """ Find an entity by entity_id """
        return list(filter(lambda d: d['entity_id'].startswith(entity_name), self.call_hass("states")))
    
    def hass_find_sensors(self, sensor_name:str, states=None) -> list:
        if not states:
            states = self.call_hass("states")

        # remove "states/" from sensor_name
        sensor_name = sensor_name.replace("states/", "")
        sensors = []
        for state in states:
            if not "sensor" in state['entity_id']: # only sensors
                continue
            if sensor_name.lower() == state['entity_id'].lower():
                sensors.append(state)
            elif "friendly_name" == state['attributes'] and \
                sensor_name.lower() in state['attributes']['friendly_name'].lower():
                sensors.append(state)
        return sensors
    
    def cmd_rack(self, text, topic, response_topic):
        # racktemp_front_temp, racktemp_back_temp
        outString = "\x0309[Rack]\x0f "
        outString += "Front:"
        try:
            front_temp = round(float(self.call_hass("states/sensor.racktemp_front_temp")['state']), 2)
            outString += f"{self.colorizeTemp(front_temp)} {front_temp}°C\x0f | "
        except Exception as e:
            outString += f"\x0304Error ({e})\x0f | "
            self.log.error(f"Error getting rack front temp: {e}")

        outString += "Back:"
        try:
            back_temp = round(float(self.call_hass("states/sensor.racktemp_back_temp")['state']), 2)
            outString += f"{self.colorizeTemp(back_temp)} {back_temp}°C\x0f | "
        except Exception as e:
            outString += f"\x0304Error ({e})\x0f | "
            self.log.error(f"Error getting rack back temp: {e}")
        
        # racktemp_front_hum, racktemp_back_hum
        outString += "Front Hum:"
        try:
            front_hum = round(float(self.call_hass("states/sensor.racktemp_front_hum")['state']), 2)
            outString += f"{self.colorizeHum(front_hum)} {front_hum}%\x0f | "
        except Exception as e:
            outString += f"\x0304Error ({e})\x0f | "
            self.log.error(f"Error getting rack front hum: {e}")
    
        outString += "Back Hum:"
        try:
            back_hum = round(float(self.call_hass("states/sensor.racktemp_back_hum")['state']), 2)
            outString += f"{self.colorizeHum(back_hum)} {back_hum}%\x0f | "
        except Exception as e:
            outString += f"\x0304Error ({e})\x0f | "
            self.log.error(f"Error getting rack back hum: {e}")
        
        outString += "Power:"
        try:
            rack_power = round(float(self.call_hass("states/sensor.hall_rack_power")['state']), 2)
            outString += f"{self.colorizeNumber(rack_power, 0.0, 400.0, 1000.0)}W\x0f"
        except Exception as e:
            outString += f"\x0304Error ({e})\x0f"
            self.log.error(f"Error getting rack power: {e}")

        self.reply(response_topic, outString)
        
    def cmd_spacestation(self, text, topic, response_topic):
        temp_sensors = ["weatherstation_bme280_temperature", 
                        "weatherstation_ht10_temperature", 
                        "weatherstation_sht3xd_temperature"]
        temp_values = [float(self.call_hass(f"states/sensor.{s}")['state']) for s in temp_sensors]
        temp_avg = sum(temp_values) / len(temp_values)
        
        self.reply(response_topic, f"\x0309[SpaceStation]\x0f {temp_avg}")

    def cmd_sensor(self, text, topic, response_topic):
        value = self.textAfterCommand(text)
        logging.info(f"Value: {value}")

        if value == None or value == "":
            return self.reply(response_topic, f"\x0309[Sensor]\x0f \x0304No sensor given")
        
        sensors = self.hass_find_sensors(value)
        if len(sensors) == 0:
            return self.reply(response_topic, f"\x0309[Sensor]\x0f \x0304No sensors found")
        
        outString = "\x0309[Sensor]\x0f "
        for sensor in sensors:
            sensorName = sensor['entity_id']
            if "friendly_name" in sensor['attributes']:
                sensorName = f"{sensor['entity_id'].split('.')[1]} ({sensor['attributes']['friendly_name']})"
                
            if not "unit_of_measurement" in sensor['attributes']:
                outString += f"{sensorName}: \x0312{sensor['state']}\x0f | "
            else:
                outString += f"{sensorName}: \x0312{sensor['state']} {sensor['attributes']['unit_of_measurement']}\x0f | "
            #sensor['attributes']['friendly_name'] + ": " + sensor['state'] + ", "
        
        self.reply(response_topic, outString[:-2])
                            
    def cmd_calender(self, text, topic, response_topic):
        calendars = self.hass_find_entities('calendar')
        
        if len(calendars) == 0:
            return self.reply(response_topic, f"\x0309[Calendars]\x0f No calendars found")
        
        outString = "\x0309[Calendars]\x0f "
        for calendar in calendars:
            #
             if calendar['attributes']['all_day']:
                start_time = calendar['attributes']['start_time'].split(" ")[0]
                end_time = calendar['attributes']['end_time'].split(" ")[0]
                outString += calendar['attributes']['friendly_name'] + ": " + calendar['attributes']['message'] + " S:" + calendar['attributes']['start_time'] + " E:" + calendar['attributes']['end_time'] + ", "
        
        self.reply(response_topic, outString[:-2])
      
    def cmd_who(self, text, topic, response_topic): 
       # get valid users because device_tracker also includes non-users (e.g. devices/hardware)
       login_dn = 'uid=device_presence,cn=users,cn=accounts,dc=nurd,dc=space'
       login_pw = 'pore5deduce+tool3North'
       server = ldap3.Server('ldaps://ipa.nurd.space')
       conn = ldap3.Connection(server, user=login_dn, password=login_pw)
       conn.bind()
       base_dn = 'cn=users,cn=accounts,dc=nurd,dc=space'
       filter = '(|(memberOf=cn=members,cn=groups,cn=accounts,dc=nurd,dc=space)(memberOf=cn=friends,cn=groups,cn=accounts,dc=nurd,dc=space))'
       attribs = ['uid']
       conn.search(base_dn, filter, attributes = attribs)
       valid_users = [entry.uid[0] for entry in conn.entries]
       conn.unbind()

       #TODO colorize people! 
       people = [p for p in self.hass_find_entities('device_tracker') if p['state'] == 'home' and p['attributes']['friendly_name'] in valid_users]
       print(people)
       people_friendly = list(map(lambda d: d['attributes']['friendly_name'], people))  
       space_state = self.call_hass('states/binary_sensor.space_state')['state']

       spelling = "is"
       if len(people) > 1:
           spelling = "are"

       if len(people) == 0:
            if space_state == 'off':
               return self.reply(response_topic, f"Nobody {spelling} in the space. (Space is \x0304closed\x0f)")
            else:
                return self.reply(response_topic, f"Nobody (registered) {spelling} in the space. (Space is \x0309open\x0f)")
        
       if people:
            friendly_str = ""
            for idx, person in enumerate(sorted(people_friendly)):
                if idx == len(people) - 2:
                    friendly_str += f"\x0309{person}\x0f and "
                elif idx == len(people) - 1:
                    friendly_str += f"\x0309{person}\x0f"
                else:
                    friendly_str += f"\x0309{person}\x0f, "
            
            if space_state == 'off':
                return self.reply(response_topic, f"{friendly_str} {spelling} in the space (Space is \x0304closed\x0f)")
            else:
                return self.reply(response_topic, f"{friendly_str} {spelling} in the space (Space is \x0309open\x0f)")
    
    def cmd_sun(self, text, topic, response_topic):
        sun_state = self.call_hass('states/sun.sun')
        if sun_state['state'] == 'above_horizon':
            self.reply(response_topic, f"\x0309[Sun]\x0f The sun is \x0308above the horizon\x0f. " \
                       f"It will set at \x0303{arrow.get(sun_state['attributes']['next_setting']).to('Europe/Amsterdam').format('HH:mm')}\x0f " \
                       f"Current elevation:\x0303 {sun_state['attributes']['elevation']}°\x0f"
                       )
        else:
            self.reply(response_topic, f"\x0309[Sun]\x0f The sun is \x0307set\x0f. " \
                f"It will rise at \x0303{arrow.get(sun_state['attributes']['next_rising']).to('Europe/Amsterdam').format('HH:mm')}\x0f " \
                f"Current elevation:\x0303 {sun_state['attributes']['elevation']}°\x0f"
                )
     
    def cmd_ot(self, text, topic, response_topic):
       """ Display opentherm info"""
       watertemp  = self.call_hass('states/sensor.ch_water_temp_boiler_thermostaat')['state']
       returntemp = self.call_hass('states/sensor.return_water_temp_boiler_thermostaat')['state']
       otgw       = self.call_hass('states/climate.thermostaat')
    
       print(otgw['attributes'])
    
       heatercolor = '\x0304' if otgw['attributes']['hvac_action'] == 'heating' else '\x0309'

       #client.publish(response_topic, 'water temp: %s°C, return temp: %s°C, heater: %s, kitchen temp: %s°C, setpoint: %s°C, last setpoint update: %s' % (watertemp, returntemp, otgw['attributes']['hvac_action'], otgw['attributes']['current_temperature'], otgw['attributes']['temperature'], arrow.get(otgw['last_updated']).to('Europe/Amsterdam').format()))
       self.reply(response_topic, 
                f"\x0309[Opentherm]\x0f " \
                f"Water temp:{self.colorizeTemp(float(watertemp))} {watertemp}°C\x0f \x0309|\x0f " \
                f"Return temp:{self.colorizeTemp(float(returntemp))} {returntemp}°C\x0f \x0309|\x0f " \
                f"Heater: {heatercolor}{otgw['attributes']['hvac_action']}\x0f \x0309|\x0f Chemostaat temp:" \
                f"{self.colorizeTemp(float(otgw['attributes']['current_temperature']))} {otgw['attributes']['current_temperature']}°C\x0f \x0309|\x0f " \
                f"Setpoint:{self.colorizeTemp(float(otgw['attributes']['temperature']))} {otgw['attributes']['temperature']}°C\x0f \x0309|\x0f " \
                f"Last setpoint: \x0309{arrow.get(otgw['last_updated']).to('Europe/Amsterdam').format()}"
       )
    
    def cmd_ot_set(self, text, topic, response_topic):
        """ Set opentherm setpoint"""
        value = self.textAfterCommand(text)
        if not value:
            return self.reply(response_topic, f"\x0309[Opentherm]\x0f \x0304No setpoint given")
        
        try:
            value = float(value)
        except:
            return self.reply(response_topic, f"\x0309[Opentherm]\x0f \x0304Invalid setpoint given")
        
        if value < 0 or value > 30:
            return self.reply(response_topic, f"\x0309[Opentherm]\x0f \x0304Invalid setpoint given (Temperature out of range of 0-30°C)")
        
        payload =  {"entity_id": "climate.thermostaat", "temperature": value}
        result = self.call_hass('services/climate/set_temperature', payload)
        
        if len(result) == 0:
            return self.reply(response_topic, f"\x0309[Opentherm]\x0f \x0307Setpoint not changed!")
        
        return self.reply(response_topic, f"\x0309[Opentherm]\x0f Setpoint set to:" \
            f"{self.colorizeTemp(float(result[0]['attributes']['temperature']))} {result[0]['attributes']['temperature']}°C\x0f " \
            f"(Current temp:{self.colorizeTemp(float(result[0]['attributes']['current_temperature']))} {result[0]['attributes']['current_temperature']}°C\x0f)")
           
    def cmd_sth(self, text, topic, response_topic):
        try:
            locations = ["zaal_1", "zaal_1_raam", "Kelder", "studio", "bar", "zaal_2", "smokeroom", "zaal_3"]
            naming = ["Zaal 1", "Raam", "Kelder", "Studio", "Bar", "Zaal 2", "Rookhok", "Zaal 3"]
            states = {}

            hass_states = self.call_hass("states")
            for location in locations:
                #TODO combine these two calls into one by just getting the whole state object
                # temp = self.call_hass(f"states/sensor.{location}_temperature")['state']
                # hum = self.call_hass(f"states/sensor.{location}_humidity")['state']
                temp = self.hass_find_sensors(f"sensor.{location}_temperature", hass_states)[0]['state']
                hum = self.hass_find_sensors(f"sensor.{location}_humidity", hass_states)[0]['state']
                states.update({ location: {"temp": temp, "hum": hum }})
            
            outString = ""
            for pos, location in enumerate(locations):
                temp = states.get(location)
                if temp and not temp['temp'] == 'unavailable' or not temp['hum'] == 'unavailable':
                    temp_color = '' if temp['temp'] == 'unavailable' else self.colorizeTemp(float(temp['temp']))
                    hum_color = '' if temp['hum'] == 'unavailable' else self.colorizeHum(float(temp['hum']))
                    outString += f"\x0309{naming[pos]}\x0f:{temp_color} {str(round(float(temp['temp']),2))}°C\x0f /{hum_color} {str(round(float(temp['hum']),2))}%\x0f, "
                
            zaal3_dak_temp = self.hass_find_sensors("sensor.daksensor_temperatuur_in_het_dak", hass_states)[0]['state']
            if zaal3_dak_temp != 'unavailable':
                outString += f"\x0309Zaal 3 Dak\x0f:{self.colorizeTemp(float(zaal3_dak_temp))} {round(float(zaal3_dak_temp), 3)}°C\x0f"

            self.reply(response_topic, outString)

        except Exception as e:
            err_str = f"[{os.path.basename(__file__)}] An exception occurred during cmd_sth ({e}). Line: {e.__traceback__.tb_lineno}"
            self.log.error(err_str)
            self.reply(response_topic, err_str)

    def spacergb(self, text, topic, response_topic):
        # get all the rgb lights from hass and set them to the given color
        entities = self.hass_find_entities("light")

    def extract_title_from_url(self, url):
        try:
            scraper = cloudscraper.create_scraper()
            r = scraper.get(url)
            soup = BeautifulSoup(r.text, 'html.parser')
            return soup.title.string
        except Exception as e:
            self.log.error(f"Error getting title: {e}")
            return f"Error getting title: {e}"

    def _srgb_to_linear(self, c: float) -> float:
        # sRGB companding inverse
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    def _hex_to_rgb01(self, hex_str: str) -> Tuple[float, float, float]:
        """
        Parse hex like '#RRGGBB', 'RRGGBB', '#RGB', '0xRRGGBB' and return floats in [0,1].
        """
        s = hex_str.strip().lower()
        if s.startswith("0x"):
            s = s[2:]
        if s.startswith("#"):
            s = s[1:]
        if len(s) == 3:  # #rgb -> #rrggbb
            s = "".join(ch * 2 for ch in s)
        if len(s) != 6 or any(ch not in "0123456789abcdef" for ch in s):
            raise ValueError(f"Invalid hex colour: {hex_str!r}")
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
        return r, g, b


    def _srgb01_to_oklab(self, r: float, g: float, b: float) -> Tuple[float, float, float]:
        """
        Convert sRGB (0..1) to OKLab (L, a, b).
        Uses Björn Ottosson's reference transforms (no external deps).
        """
        # Linearize
        rl, gl, bl = self._srgb_to_linear(r), self._srgb_to_linear(g), self._srgb_to_linear(b)

        # RGB -> LMS (via linear sRGB to LMS matrix)
        l = 0.4122214708 * rl + 0.5363325363 * gl + 0.0514459929 * bl
        m = 0.2119034982 * rl + 0.6806995451 * gl + 0.1073969566 * bl
        s = 0.0883024619 * rl + 0.2817188376 * gl + 0.6299787005 * bl

        # Nonlinearity
        l_ = l ** (1.0 / 3.0)
        m_ = m ** (1.0 / 3.0)
        s_ = s ** (1.0 / 3.0)

        # LMS -> OKLab
        L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
        a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
        b = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
        return (L, a, b)

    def _hex_to_oklab(self, hex_str: str) -> Tuple[float, float, float]:
        r, g, b = self._hex_to_rgb01(hex_str)
        return self._srgb01_to_oklab(r, g, b)


    def _oklab_distance(self, o1: Tuple[float, float, float], o2: Tuple[float, float, float]) -> float:
        # Euclidean distance in OKLab (good perceptual proxy)
        dL = o1[0] - o2[0]
        da = o1[1] - o2[1]
        db = o1[2] - o2[2]
        return math.sqrt(dL * dL + da * da + db * db)

    def _file_mtime(self, path: str) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return -1.0


    @lru_cache(maxsize=8)
    def _load_color_db(self, path: str, mtime: float) -> List[Dict[str, Any]]:
        """
        Load and preprocess color DB from JSON path.
        Result: list of dicts: {"name": str, "hex": "#rrggbb", "oklab": (L,a,b)}
        LRU cache key includes mtime so edits to the file bust cache.
        """
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        db: List[Dict[str, Any]] = []
        for item in raw:
            name = item.get("name")
            hx = item.get("hex")
            if not isinstance(name, str) or not isinstance(hx, str):
                continue
            # normalize hex to #rrggbb
            r, g, b = self._hex_to_rgb01(hx)
            hex_norm = "#{:02x}{:02x}{:02x}".format(int(round(r * 255)),
                                                    int(round(g * 255)),
                                                    int(round(b * 255)))
            db.append({"name": name, "hex": hex_norm, "oklab": self._srgb01_to_oklab(r, g, b)})
        if not db:
            raise ValueError(f"No valid color entries found in {path!r}.")
        return db

    def _get_db(self, path: str) -> List[Dict[str, Any]]:
        return self._load_color_db(path, self._file_mtime(path))

    def closest_colour_name(self,
        hex_color: str,
        json_path: str = "colornames.json",
        *,
        k: int = 1,
        include_distance: bool = False,
    ) -> Any:
        """
        Given a hex color, return the closest colour name(s) from a JSON database.

        Parameters
        ----------
        hex_color : str
            Input color, e.g. '#c93f38', 'c93f38', '#f00', '0xff0000'.
        json_path : str
            Path to colornames JSON with objects like {"name": "...", "hex": "#rrggbb"}.
        k : int
            Number of closest matches to return. k=1 returns a single value by default.
        include_distance : bool
            If True, return dict(s) with name, hex, distance (OKLab Δ).

        Returns
        -------
        If k == 1 and include_distance == False:
            str  -> the single closest color name.
        Else:
            List[dict] -> [{"name": str, "hex": "#rrggbb", "distance": float}, ...] sorted by closeness.

        Notes
        -----
        - Exact hex matches (case-insensitive, including #rgb form) are returned immediately.
        - Distances use Euclidean Δ in OKLab for better perceptual matching than RGB/HSV.
        """
        db = self._get_db(json_path)

        # Normalize input and check exact match first
        try:
            r, g, b = self._hex_to_rgb01(hex_color)
        except ValueError as e:
            raise

        input_hex_norm = "#{:02x}{:02x}{:02x}".format(int(round(r * 255)),
                                                    int(round(g * 255)),
                                                    int(round(b * 255)))
        for entry in db:
            if entry["hex"].lower() == input_hex_norm:
                if k == 1 and not include_distance:
                    return entry["name"]
                out = {"name": entry["name"], "hex": entry["hex"], "distance": 0.0}
                return [out] if k != 1 or include_distance else entry["name"]

        # Fuzzy match via OKLab
        target_oklab = self._srgb01_to_oklab(r, g, b)
        scored: List[Tuple[float, Dict[str, Any]]] = []
        for entry in db:
            d = self._oklab_distance(target_oklab, entry["oklab"])
            scored.append((d, entry))

        scored.sort(key=lambda t: t[0])
        top = scored[: max(1, k)]
        if k == 1 and not include_distance:
            return top[0][1]["name"]
        return [{"name": e["name"], "hex": e["hex"], "distance": float(d)} for d, e in top]


    def cmd_spacehex(self, text, topic, response_topic):
        states = self.call_hass("states")
        rgb = [self.hass_find_sensors("sensor.tcs34725_red_channel", states)[0],
               self.hass_find_sensors("sensor.tcs34725_green_channel", states)[0],
               self.hass_find_sensors("sensor.tcs34725_blue_channel", states)[0]]

        if rgb[0]['state'] == "unavailable" or rgb[1]['state'] == "unavailable" or rgb[2]['state'] == "unavailable":
            return self.reply(response_topic, f"\x0309[SpaceHex]\x0f \x0304Unavailable\x0f")

        hexcolor = "{:02x}{:02x}{:02x}".format(*[int(round((float(x['state']) / 100) * 255)) for x in rgb])
        
        name = self.closest_colour_name(f"#{hexcolor}", "colornames.json")
        return self.reply(response_topic, f"\x0309[SpaceHex]\x0f Zaal 1 is currently: \x0303#{hexcolor}\x0f - ({name})")
        
    def cmd_power(self, text, topic, response_topic):
        if "-v" in text:
            
            sensorArray = [
                    {"sensor": "states/sensor.hall_rack_power", "name": "Rack", "colors": [0.0, 400.0, 1000.0]},
                    {"sensor": "states/sensor.kitchen_network_power", "name": "Kitchen network", "colors": [0.0, 400.0, 1000.0]},
                    {"sensor": "states/sensor.amp_zaal1_power", "name": "Zaal 1 Amp", "colors": [0.0, 30.0, 100.0]},
                    {"sensor": "states/sensor.zaal1_desks_power", "name": "Zaal 1 stekkerblokken", "colors": [0.0, 500.0, 800.0]},
                    {"sensor": "states/sensor.zaal1_mediacorner_power", "name": "Zaal 1 mediacorner", "colors": [0.0, 500.0, 800.0]}, 
                    {"sensor": "states/sensor.kitchen_counter_power", "name": "Kitchen Counter","colors": [0.0, 500.0, 800.0]}, 
                    {"sensor": "states/sensor.kitchen_dishwasher_power", "name": "Vaatwasser", "colors": [0.0, 500.0, 800.0]}, 
                    {"sensor": "states/sensor.3d_corner_metering_power", "name": "3D Corner", "colors": [0.0, 500.0, 800.0]}, 
                    # {"sensor": "states/sensor.groepenkast_a_power", "name": "Groep A", "colors": [0.0, 500.0, 800.0]}, 
                    # {"sensor": "states/sensor.groepenkast_b_power", "name": "Groep B","colors": [0.0, 500.0, 800.0]}, 
                    # {"sensor": "states/sensor.zaal_2_power", "name": "Zaal 2","colors": [0.0, 500.0, 800.0]}, 
                    {"sensor": "states/sensor.p1_meter_power", "name": "Total", "colors": [0.0, 500.0, 800.0]}, 
                    ]

        else:
            sensorArray = [
                    # {"sensor": "states/sensor.groepenkast_a_power", "name": "Groep A", "colors": [0.0, 500.0, 800.0]},
                    # {"sensor": "states/sensor.groepenkast_b_power", "name": "Group B", "colors": [0.0, 500.0, 800.0]},
                    {"sensor": "states/sensor.p1_meter_power", "name": "Total", "colors": [0.0, 500.0, 800.0]}
                    ]
        
        power_str = "\x0309[Power Usage]\x0f "
        states = self.call_hass("states")
        #for sensor, name, colors in zip(sensors, nameing, colorSeverities):
        for sensorDict in sensorArray:
            sensor = sensorDict['sensor']
            name = sensorDict['name']
            colors = sensorDict['colors']
            try:
                power = self.hass_find_sensors(sensor, states)[0]
                if power['state'] == "unavailable":
                    power_str += f"{name}: \x0304Unavailable\x0f \x0309|\x0f "
                else:
                    power_str += f"{name}:{self.colorizeNumber(float(power['state']), *colors)}W \x0f\x0309|\x0f "
            except Exception as e:
                self.log.error(f"Error getting power usage: {e}")
                power_str += f"{name}: \x030Error ({e}) \x0309|\x0f"
                
        self.reply(response_topic, power_str[:-3])
    
    def cmd_regen(self, text, topic, response_topic):
        try:
            regen_data = self.request("https://gpsgadget.buienradar.nl/data/raintext/?lat=51.97&lon=5.67")
            regen_data = regen_data.decode('utf-8')
        except Exception as e:
            self.log.error(f"Error getting regen data: {e}")
            return self.reply(response_topic, f"\x0309[Regen]\x0f \x0304Error {e}\x0f")

        milimeters_values = []
        results = ["in mm/u: "]
        
        for regen_line in regen_data.split("\n"):
            regen_line = regen_line.strip().rstrip("\r")
            if len(regen_line) == 0:
                continue
            if regen_line == '':
                continue
            
            milimeters, time = regen_line.split("|")
            milimeters = math.pow(10.0, ((float(milimeters) - 109)/32.0))
            milimeters_values.append(milimeters)
            
            if milimeters >= 0.001:
                #results.append('%s: %.3fmm/u, ' % (milimeters, float(time)))
                results.append(f"\x02{time}:\x02 {milimeters:.3f}, ")
        
        if len(results) == 0:
            return self.reply(response_topic, f"\x0309[Regen]\x0f \x0312Geen regen voorspeld door buienradar.nl\x0f")
        
        outString = "\x0309[Regen]\x0f "
        outString += ''.join(results) 
        outString += "\x0f"
        
        if self.textAfterCommand(text) and "-v" in self.textAfterCommand(text):
            try:
                mn, mx, sparkline = self.sparkline(milimeters_values)
                outString += f"\x0309|\x0f {sparkline}"
            except Exception as e:
                self.log.error(f"[{os.path.basename(__file__)}] An exception occurred during on_regen ({e}). Line: {e.__traceback__.tb_lineno}")
        
        self.reply(response_topic, outString[:-2])

    def textAfterCommand(self, text):
        try:
            return text.split(" ", 1)[1]
        except:
            return None
    
    def colorizeNumber(self, number, low=30, mid=50, high=100):
        number = number
        
        if number < low:
            return f"\x0303 {number}"
        elif number < mid:
            return f"\x0307 {number}"
        elif number < high:
            return f"\x0308 {number}"
        else:
            return f"\x0304 {number}"
    
    def colorizeTemp(self,  celsius_temp):
        """
        Assigns an IRC color to a Celsius temperature based on its heat level.
        
        Arguments:
        celsius_temp -- The Celsius temperature value.
        
        Returns:
        The IRC color code as a string.
        """

        if celsius_temp >= 30.0:
            return '\x034'  # Red color code
        elif celsius_temp >= 20.0:
            return '\x037'  # Orange color code
        elif celsius_temp >= 10.0:
            return '\x038'  # Yellow color code
        elif celsius_temp >= 0.0:
            return '\x0309'  # Light Green color code
        elif celsius_temp >= -10.0:
            return '\x0311'  # Dark Green color code
        else:
            return '\x0312'  # Light Blue color code
    
    def colorizeHum(self, humidity):
        """
        Assigns an IRC color to a humidity level based on its value.
        
        Arguments:
        humidity -- The humidity value.
        
        Returns:
        The IRC color code as a string.
        """
        
        if humidity > 60:
            return '\x034'
        if humidity >= 40:
            return '\x0309'
        return '\x037'
   
    def sparkline(self, numbers):
        # bar = u'\u9601\u9602\u9603\u9604\u9605\u9606\u9607\u9608'
        bar = chr(9601) + chr(9602) + chr(9603) + chr(9604) + chr(9605) + chr(9606) + chr(9607) + chr(9608)
        barcount = len(bar)

        mn, mx = min(numbers), max(numbers)
        extent = mx - mn
        sparkline = ''.join(bar[min([barcount - 1, int((n - mn) / extent * barcount)])] for n in numbers)

        return mn, mx, sparkline

    # def _normalize_rgb16_to_8(self, r, g, b):
    #     """
    #     TCS34725 channels are typically 0..65535 (16-bit-ish). 
    #     We scale them so the brightest channel maps to 255 (preserving ratios).
    #     If all zero, return black.
    #     """
    #     r = int(r) if r is not None else 0
    #     g = int(g) if g is not None else 0
    #     b = int(b) if b is not None else 0
    #     m = max(r, g, b)
    #     if m <= 0:
    #         return (0, 0, 0)
    #     # scale so max -> 255
    #     k = 255.0 / m
    #     return (int(r * k), int(g * k), int(b * k))

    # def _gamma_correct(self, r, g, b, gamma=2.2):
    #     """
    #     Simple gamma correction for nicer perceived color on LEDs.
    #     """
    #     def corr(x):
    #         xn = max(0, min(255, x)) / 255.0
    #         return int(round((xn ** (1.0 / gamma)) * 255))
    #     return (corr(r), corr(g), corr(b))

    # def _send_wled_color(self, wled_host, r, g, b, brightness=None, segment_id=None, timeout=2.5):
    #     """
    #     Send a solid color to WLED using its JSON API.
    #     wled_host: "192.168.1.123" or "wled.local"
    #     brightness: 1..255, optional. If None, keep current.
    #     segment_id: int or None. If None, applies to current/first segment.
    #     """
    #     url = f"http://{wled_host}/json/state"
    #     payload = {
    #         "on": True,
    #     }

    #     # Segment object: set color for target segment (or default)
    #     seg_obj = {"col": [[int(r), int(g), int(b)]]}
    #     if segment_id is not None:
    #         seg_obj["id"] = int(segment_id)

    #     payload["seg"] = [seg_obj]
    #     if brightness is not None:
    #         payload["bri"] = int(max(1, min(255, brightness)))

    #     resp = requests.post(url, json=payload, timeout=timeout)
    #     resp.raise_for_status()
    #     return resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"ok": True}

    def hex_to_rgb(self, hex_str):
        """Convert hex color string to RGB tuple."""
        hex_str = hex_str.lstrip('#')
        if len(hex_str) == 3:
            hex_str = ''.join([c*2 for c in hex_str])
        if len(hex_str) != 6:
            raise ValueError("Invalid hex color format")
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        return (r, g, b)

    def cmd_zaalrgb(self, text, topic, response_topic):
        wled_host = "10.208.2.23"  # default target
        brightness = None           # optional override
        gamma_val = 2.2             # tweak if needed
        segment_id = None

        parts = text.strip().split(" ")
        if len(parts) < 2:
            self.reply(response_topic, "Usage: !zaalrgb R,G,B (e.g. !zaalrgb 255,128,64)")
            return
        print(parts)
        
        rgb_str = " ".join(parts[1:]).strip()
        if rgb_str.startswith("#") or rgb_str.startswith("0x"):
            try:
                r, g, b = self.hex_to_rgb(rgb_str)
            except ValueError as e:
                self.log.error(f"Invalid hex color '{rgb_str}': {e}")
                return
        else:
            # Expecting "R,G,B"
            try:
                # EXTRACT 3 numbers, no matter the spacing or commas
                pattern = re.compile(r'\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*[, ]\s*(\d{1,3})\s*')
                m = pattern.fullmatch(rgb_str)
                if not m:
                    raise ValueError("Invalid RGB format")
                r, g, b = map(int, m.groups())
            except Exception as e:
                self.log.error(f"Invalid RGB format '{rgb_str}', expected R,G,B — {e}")
                return

        # Clamp values
        r, g, b = [max(0, min(255, x)) for x in (r, g, b)]

        # Send to WLED
        url = f"http://{wled_host}/json/state"
        payload = {
            "on": True,
            "seg": [{
                "col": [[r, g, b]]
            }]
        }
        if brightness is not None:
            payload["bri"] = int(max(1, min(255, brightness)))
        if segment_id is not None:
            payload["seg"][0]["id"] = int(segment_id)

        try:
            resp = requests.post(url, json=payload, timeout=2.5)
            resp.raise_for_status()
            self.reply(response_topic, f"Set WLED @ {wled_host} to RGB({r},{g},{b})")
        except Exception as e:
            self.reply(response_topic, f"Failed to send RGB to WLED @ {wled_host}: {e}")

    def cmd_zaal2wled(self, text, topic, response_topic):
            """
            Reads TCS34725 RGB channels from Home Assistant and sends color to WLED.
            'text' may optionally contain params like:
            "wled=192.168.1.50 bri=128 gamma=2.2 seg=0"
            """
            # --- defaults you can tweak ---
            wled_host = "10.208.2.23"     # set your default target
            brightness = None            # or e.g. 180
            gamma_val = 2.2
            segment_id = None

            # Parse simple key=value pairs from 'text' (kept deliberately light)
            if text:
                for part in text.split():
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if k == "wled":
                            wled_host = v
                        elif k in ("bri", "brightness"):
                            try: brightness = int(v)
                            except: pass
                        elif k == "gamma":
                            try: gamma_val = float(v)
                            except: pass
                        elif k in ("seg", "segment"):
                            try: segment_id = int(v)
                            except: pass

            states = self.call_hass("states")
            rgb_raw = [
                self.hass_find_sensors("sensor.tcs34725_red_channel", states)[0],
                self.hass_find_sensors("sensor.tcs34725_green_channel", states)[0],
                self.hass_find_sensors("sensor.tcs34725_blue_channel", states)[0]
            ]

            # Safeguard: resolve entity state value -> int
            def to_int(v):
                try:
                    # HA state often as string
                    return int(float(v.get("state") if isinstance(v, dict) else v))
                except Exception:
                    return 0

            r16, g16, b16 = map(to_int, rgb_raw)

            # Normalize and gamma-correct
            r8, g8, b8 = self._normalize_rgb16_to_8(r16, g16, b16)
            r8, g8, b8 = self._gamma_correct(r8, g8, b8, gamma=gamma_val)

            try:
                result = self._send_wled_color(
                    wled_host=wled_host,
                    r=r8, g=g8, b=b8,
                    brightness=brightness,
                    segment_id=segment_id
                )
                self.reply(response_topic, f"WLED @ {wled_host} set to RGB({r8},{g8},{b8}) bri={brightness} seg={segment_id} result={result}")
            except Exception as e:
                self.log.error(f"Failed to send color to WLED @ {wled_host}: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting up.")
    plugin = hassPlugin()
    plugin.run()
