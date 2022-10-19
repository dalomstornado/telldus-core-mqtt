#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import logging.config
import random
import threading
import time

import yaml
from paho.mqtt import client as mqtt_client

import src.telldus as telldus
from src.telldus import const, td

THREADING_RLOCK = threading.RLock()

TYPES = {const.TELLSTICK_TEMPERATURE: 'temperature',
         const.TELLSTICK_HUMIDITY: 'humidity',
         const.TELLSTICK_RAINRATE: 'rainrate',
         const.TELLSTICK_RAINTOTAL: 'raintotal',
         const.TELLSTICK_WINDDIRECTION: 'winddirection',
         const.TELLSTICK_WINDAVERAGE: 'windaverage',
         const.TELLSTICK_WINDGUST: 'windgust'}

METHODS = {const.TELLSTICK_TURNON: 'turn on',
           const.TELLSTICK_TURNOFF: 'turn off',
           const.TELLSTICK_BELL: 'bell',
           const.TELLSTICK_TOGGLE: 'toggle',
           const.TELLSTICK_DIM: 'dim',
           const.TELLSTICK_LEARN: 'learn',
           const.TELLSTICK_EXECUTE: 'execute',
           const.TELLSTICK_UP: 'up',
           const.TELLSTICK_DOWN: 'down',
           const.TELLSTICK_STOP: 'stop'}


def connect_mqtt(config, client_id) -> mqtt_client:
    def on_connect(client, userdata, flags, return_code):
        # pylint: disable=unused-argument
        if return_code == 0:
            client.connected_flag = True
            logging.info('Connected to MQTT Broker as %s.', client_id)
        else:
            logging.critical('Failed to connect, return code %d', return_code)

    client = mqtt_client.Client(client_id)
    client.username_pw_set(config['mqtt']['user'], config['mqtt']['pass'])
    client.on_connect = on_connect
    client.connect(config['mqtt']['broker'], int(config['mqtt']['port']))

    return client


def publish_mqtt(client, topic, msg):
    with THREADING_RLOCK:
        result = client.publish(topic, msg, retain=True)

        if result[0] == 0:
            logging.info('Send "%s" to topic "%s"', msg, topic)
        else:
            logging.error('Failed to send message to topic "%s"', topic)


def subscribe_device(client: mqtt_client):
    logging.debug('Subscribing to MQTT device events')

    def on_message(client, userdata, msg):
        # pylint: disable=unused-argument
        logging.info('Received "%s" from "%s" topic',
                     msg.payload.decode(), msg.topic)
        device_id = msg.topic.split('/')[1]
        module = msg.topic.split('/')[2]
        action = msg.topic.split('/')[3]
        cmd_status = False

        payload = int(msg.payload.decode())
        if module == 'light':
            if action == 'dim':
                logging.info('[DEVICE] Sending command DIM "%s" to device id "%s"', payload, device_id)
                cmd_status = d.dim(device_id, payload)
            elif action == 'set':
                if payload == 0:
                    logging.info('[DEVICE] Sending light OFF "%s" to device id "%s"', payload, device_id)
                    cmd_status = d.turn_off(device_id)
                else:
                    logging.info('[DEVICE] Sending light ON ONCE "%s" to device id "%s"', payload, device_id)
                    cmd_status = d.turn_on_once(device_id)
            else:
                logging.info('[DEVICE] Unknown light action "%s"', action)
        
        elif module == 'brightness':
                logging.info('[DEVICE] Sending command DIM (brightness) "%s" to device id "%s"', payload, device_id)
                cmd_status = d.dim(device_id, payload)
        
        elif module == 'switch':
            if payload == int(const.TELLSTICK_TURNON):
                logging.info('[DEVICE] Sending command ON to device id "%s"', device_id)
                cmd_status = d.turn_on(device_id)
            elif payload == int(const.TELLSTICK_TURNOFF):
                logging.info('[DEVICE] Sending command OFF to device id "%s', device_id)
                cmd_status = d.turn_off(device_id)
        
        elif not cmd_status:
            logging.error('[DEVICE] Command "%s" not supported, please open a github issue with this message.', msg)

    client.subscribe('{}/+/+/set'.format(config['home_assistant']['state_topic']))
    client.on_message = on_message


def raw_event(data, controller_id, cid):
    # pylint: disable=unused-argument
    if 'command' not in data:
        return

    # Sensors can be added or discovered in telldus-core without
    # a restart, ensure config topic for HASS
    command_topics = raw.create_topics(raw.get(data))
    initial_publish(mqtt_command, command_topics)

    topic = raw.create_topic(raw.serialized['id'], 'binary_sensor')
    topic_data = raw.create_topic_data('binary_sensor',
                                       raw.serialized['method'])

    publish_mqtt(mqtt_command, topic, topic_data)


def device_event(id_, method, data, cid):
    # pylint: disable=unused-argument
    method_string = METHODS.get(method, 'UNKNOWN METHOD {0}'.format(method))
    string = '[DEVICE] {0} -> {1} ({2})'.format(id_, method_string, method)
    if method == const.TELLSTICK_DIM:
        string += ' [{0}]'.format(data)

    # TODO: remove hardcoded dimmer ids
    if id_ == 8 or id_ == 9 or id_ == 10 or id_ == 11 or id_ == 12:
        logging.debug('[DEVICE EVENT DIMMER LIGHT] %s', string)
        if method == const.TELLSTICK_TURNOFF:
            topic = d.create_topic(id_, 'light')
            topic_data = d.create_topic_data('light', 0)
        elif method == const.TELLSTICK_TURNON:
            topic = d.create_topic(id_, 'light')
            topic_data = d.create_topic_data('light', 255)
        elif method == const.TELLSTICK_DIM:
            topic = d.create_topic(id_, 'brightness')
            topic_data = d.create_topic_data('brightness', data)
    elif method == const.TELLSTICK_DIM:
        logging.debug('[DEVICE EVENT LIGHT] %s', string)
        topic = d.create_topic(id_, 'brightness')
        topic_data = d.create_topic_data('brightness', data)
    else:
        logging.debug('[DEVICE EVENT SWITCH] %s', string)
        topic = d.create_topic(id_, 'switch')
        topic_data = d.create_topic_data('switch', method)
    publish_mqtt(mqtt_device, topic, topic_data)

def sensor_event(protocol, model, id_, data_type, value, timestamp, cid):
    # pylint: disable=unused-argument
    type_string = TYPES.get(data_type, 'UNKNOWN METHOD {0}'.format(data_type))
    string = '[SENSOR] {0} {1} ({2}) = {3}'.format(
        id_, model, type_string, value)
    logging.debug(string)

    # Sensors can be added or discovered in telldus-core without
    # a restart, ensure config topic for HASS
    sensor_topics = s.create_topics(s.get(id_))
    initial_publish(mqtt_sensor, sensor_topics)

    topic = s.create_topic(id_, type_string)
    data = s.create_topic_data(type_string, value)
    publish_mqtt(mqtt_sensor, topic, data)


def initial_publish(client_mqtt, topics):
    for topic in topics:
        if 'config' in topic:
            publish_mqtt(client_mqtt, topic['config']['topic'],
                         topic['config']['data'])
        if 'state' in topic:
            publish_mqtt(client_mqtt, topic['state']['topic'],
                         topic['state']['data'])


with open('./logging.yaml', 'r', encoding='utf-8') as stream:
    logging_config = yaml.load(stream, Loader=yaml.SafeLoader)

logging.config.dictConfig(logging_config)
logger = logging.getLogger('telldus-core-mqtt-main')

# Wait 5s for telldus-core to start and start collecting data
logging.info('Waiting for telldus-core to start...')
time.sleep(5)
logging.info('telldus-core have started.')

# Setup connection MQTT server
c = telldus.Telldus()
config = c.get_config

# Setting up MQTT connections
mqtt_sensor_id = 'telldus-core-mqtt-sensor-{}'.format(
    random.randint(0, 1000))  # nosec
mqtt_sensor = connect_mqtt(config, mqtt_sensor_id)

mqtt_device_id = 'telldus-core-mqtt-device-{}'.format(
    random.randint(0, 1000))  # nosec
mqtt_device = connect_mqtt(config, mqtt_device_id)

mqtt_command_id = 'telldus-core-mqtt-command-{}'.format(
    random.randint(0, 1000))  # nosec
mqtt_command = connect_mqtt(config, mqtt_command_id)

mqtt_subscription_id = 'telldus-core-mqtt-subscription-{}'.format(
    random.randint(0, 1000))  # nosec
mqtt_subscription = connect_mqtt(config, mqtt_subscription_id)

# # On program start, collect sensors to publish to MQTT server
s = telldus.Sensor(c.td_core)
sensors_topics = s.create_topics(s.get())
initial_publish(mqtt_sensor, sensors_topics)

# # On program start, collect devices to publish to MQTT server
d = telldus.Device(c.td_core)
devices_topics = d.create_topics(d.get())
initial_publish(mqtt_device, devices_topics)

# Collect raw commands
raw = telldus.Command(c.td_core)

# Initialize event listener for telldus-core
telldus_core = asyncio.new_event_loop()
asyncio.set_event_loop(telldus_core)

dispatcher = td.AsyncioCallbackDispatcher(telldus_core)
core = td.TelldusCore(callback_dispatcher=dispatcher)
callbacks = []

# # Events to listen for from telldus-core
callbacks.append(core.register_raw_device_event(raw_event))
callbacks.append(core.register_device_event(device_event))
callbacks.append(core.register_sensor_event(sensor_event))

# Main loop
try:
    subscribe_device(mqtt_subscription)

    mqtt_sensor.loop_start()
    mqtt_device.loop_start()
    mqtt_command.loop_start()
    mqtt_subscription.loop_start()

    telldus_core.run_forever()
except KeyboardInterrupt:
    mqtt_device.unsubscribe('{}/+/+/set'.format(
        config['home_assistant']['state_topic']))

    mqtt_sensor.disconnect()
    mqtt_device.disconnect()
    mqtt_command.disconnect()
    mqtt_subscription.disconnect()

    mqtt_sensor.loop_stop()
    mqtt_device.loop_stop()
    mqtt_command.loop_stop()
    mqtt_subscription.loop_stop()
