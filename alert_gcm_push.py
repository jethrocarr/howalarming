#! /usr/bin/env python
#
# Listens to events from beanstalk event queue and issues alerts via Google
# Cloud Messaging. These alerts can be delivered to the open source native
# apps.
#
# You must create a Google project at https://console.developers.google.com and
# setup tokens for Google Compute Messaging. There will be a server ID & key
# to go into config.yaml and an associate config file to go into the native app
# source code.
#
# This is a PUSH-ONLY server which makes it damn simple, but also means it
# lacks registration of devices back to the server, which requires you to copy
# the registration ID output by the app and add to the server configuration
# file.
#
# Refer to the README for more information.
#

import socket
import sys
import time
import datetime
import string
import re
import signal
import select
import smtplib
import email.utils
import json
import yaml         # requires pyyaml third party package
import beanstalkc   # requires beanstalkc third party package
from gcm import GCM # requires python-gcm third party package

class HowAlarming:

    def __init__(self):
        # Load configuration from YAML file and assign configuration values.
        try:
            self.config         = yaml.load(open('config.yaml', 'r'))

            # Beanstalkd Message Queue settings
            self.beanstalk_host             = self.config['beanstalkd']['host']
            self.beanstalk_port             = int(self.config['beanstalkd']['port'])
            self.beanstalk_tubes_commands   = self.config['beanstalkd']['tubes']['commands']
            self.beanstalk_tubes_events     = self.config['beanstalkd']['tubes']['events']

            # GCM
            self.gcm_api_key                = self.config['alert_gcm']['api_key']
            self.gcm_registration_tokens    = self.config['alert_gcm']['registration_tokens']
            self.triggers                   = self.config['alert_gcm']['triggers']

            # Make sure the queue we listen to exists
            if 'alert_gcm' not in self.config['beanstalkd']['tubes']['events']:
                print "Fatal: Config must define the alert_gcm event queue for this application."
                raise BaseException

        except IOError:
            print 'Fatal: Could not open configuration file'
            raise

        except (KeyError, AttributeError) as err:
            print 'Fatal: Unable to find required configuration in config.yaml'
            raise


    def beanstalk_connect(self):
        try:
            self.beanstalk = beanstalkc.Connection(host=self.beanstalk_host, port=self.beanstalk_port)
            print 'system: Beanstalkd connected on ' + str(self.beanstalk_host) + ' on port ' + str(self.beanstalk_port)
        except socket.error, (value,message):
            print "Fatal: Unable to connect to beanstalkd"
            raise


    def beanstalk_poll(self):
        # Poll for any commands in the event tube for CLI (aptly named "cli")

        self.beanstalk.watch('alert_gcm')
        job = self.beanstalk.reserve() # blocking call

        if job:
            # Event recieved, is it on the list of types we care about?
            try:
                alarm_event = json.loads(job.body)

                if alarm_event['type'] in self.triggers:
                    print "Recieved alert suitable for pushing, will trigger GCM event immediately:"
                    print job.body

                    # We send the message in the exact same JSON format, keeps things simple if all the
                    # HowAlarming applications respect the same format.
                    gcm      = GCM(self.gcm_api_key)
                    response = gcm.json_request(registration_ids=self.gcm_registration_tokens, data=alarm_event)


                    # Evaluate response.
                    if response and 'success' in response:
                        for reg_id, success_id in response['success'].items():
                            print 'Successfull delivery to reg_id: ' + reg_id

                    if 'errors' in response:
                        for error, reg_ids in response['errors'].items():
                            # Check for errors and act accordingly
                            if error in ['NotRegistered', 'InvalidRegistration']:
                                for reg_id in reg_ids:
                                    print "Registration ID no long valid, remove from config.yaml promptly: " + reg_id

                    if 'canonical' in response:
                        for reg_id, canonical_id in response['canonical'].items():
                            # Google has changed the canonical reg_id for this device, the config must
                            # be updated to reflect.
                            print "Replace reg ID ("+ reg_id +") with canonical id ("+ canonical_id +") in config.yaml promptly."

                else:
                    print 'Non-alerting event, ignoring (type: '+ alarm_event['type'] +')'

            except KeyError:
                print "Warning: Unable to process message, invalid JSON: ", job.body

            job.delete()
        return



if __name__ == '__main__':
        try:
            c = HowAlarming()
            c.beanstalk_connect()

            print 'system: ready to send GCM push messages to your app(s)!'
            while(True):
                c.beanstalk_poll()

        except KeyboardInterrupt:
            print 'system: User Terminated'
        except socket.error, err:
            print 'system: socket error ' + str(err[0])
