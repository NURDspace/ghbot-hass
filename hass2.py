#! /usr/bin/env python3

import time
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
from bs4 import BeautifulSoup

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
           PluginCommand(self.cmd_spacestation, "spacestation", "Display the current weatherstation on top of the space")
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
       #TODO colorize people! 
       people = [p for p in self.hass_find_entities('person') if p['state'] == 'home']
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
                outString += f"\x0309Zaal 3 Dak\x0f:{self.colorizeTemp(float(zaal3_dak_temp))} {zaal3_dak_temp}°C\x0f"

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

    def cmd_spacehex(self, text, topic, response_topic):
        states = self.call_hass("states")
        rgb = [self.hass_find_sensors("sensor.tcs34725_red_channel", states)[0],
               self.hass_find_sensors("sensor.tcs34725_green_channel", states)[0],
               self.hass_find_sensors("sensor.tcs34725_blue_channel", states)[0]]

        if rgb[0]['state'] == "unavailable" or rgb[1]['state'] == "unavailable" or rgb[2]['state'] == "unavailable":
            return self.reply(response_topic, f"\x0309[SpaceHex]\x0f \x0304Unavailable\x0f")

        hexcolor = "{:02x}{:02x}{:02x}".format(*[int(round((float(x['state']) / 100) * 255)) for x in rgb])
        title = self.extract_title_from_url(f"https://icolorpalette.com/color/{hexcolor}")
        if not title.startswith("Error") and "information" in title.lower():
            # strip first character 
            title = title[1:]
            title = title.split("  ")[0]


        return self.reply(response_topic, f"\x0309[SpaceHex]\x0f Zaal 1 is currently: \x0303#{hexcolor}\x0f - {title} (https://icolorpalette.com/color/{hexcolor})")
        
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

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.info("Starting up.")
    plugin = hassPlugin()
    plugin.run()
