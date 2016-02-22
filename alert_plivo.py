#! /usr/bin/env python
#
# Listens to events from beanstalk event queue and issues alerts via the Plivo
# service for text-to-speech voice calls.
#
# Only accurate test is to trigger an event, recommend setting it to call on
# 'armed' and 'disarmed' events for testing, but once setup, probably only want
# alerts for 'alarm', 'recovery' and 'fault'
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

import plivo        # required third party package
#import plivoxml     # required third party package

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

            # Plivo Settings
            self.auth_id      = self.config['alert_plivo']['auth_id']
            self.auth_token   = self.config['alert_plivo']['auth_token']
            self.call_from    = self.config['alert_plivo']['call_from']
            self.call_to      = self.config['alert_plivo']['call_to']
            self.triggers     = self.config['alert_plivo']['triggers']

            # Make sure the queue we listen to exists
            if 'alert_plivo' not in self.config['beanstalkd']['tubes']['events']:
                print "Fatal: Config must define the alert_plivo event queue for this application."
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
        # Poll for any commands in the event tube for Plivo

        self.beanstalk.watch('alert_plivo')
        job = self.beanstalk.reserve() # blocking call

        if job:
            # Event recieved, is it on the list of types we care about?
            try:
                alarm_event = json.loads(job.body)

                if alarm_event['type'] in self.triggers:
                    print "Recieved alert suitable for sending to plivo, triggering call for each destination number configured..."
                    print job.body

                    # Dial each number configured via Plivo service
                    for phone in self.call_to:

                        # Generic messages to play back to Plivo when conditions occur. Github
                        # probably isn't the greatest place to host this, but it's also probably
                        # not the worst either given the high awareness of API changes and any
                        # breakages. There's no way to have Plivo play a message without doing
                        # a callback either. :-(
                        message = 'https://raw.githubusercontent.com/jethrocarr/howalarming/master/resources/plivo/event.xml'

                        if alarm_event['type'] == 'alarm':
                            message_url = 'https://raw.githubusercontent.com/jethrocarr/howalarming/master/resources/plivo/alarm.xml'

                        if alarm_event['type'] == 'recovery':
                            message_url = 'https://raw.githubusercontent.com/jethrocarr/howalarming/master/resources/plivo/recovery.xml'

                        if alarm_event['type'] == 'fault':
                            message_url = 'https://raw.githubusercontent.com/jethrocarr/howalarming/master/resources/plivo/fault.xml'


                        # Place call via the Plivo service.
                        try:
                            p = plivo.RestAPI(self.auth_id, self.auth_token)

                            params = {
                                'to':            phone,
                                'from':          self.call_from,
                                'caller_name':   'HowAlarming',
                                'answer_url':    message_url,
                                'answer_method': 'GET',
                                }

                            response = p.make_call(params)

                            if response[0] != 201:
                                print "Warning: A caller infrastructure error occured when attempting to call " + str(phone) +"."
                        except:
                            print "Warning: An unexpected fault occured when attempting to call " + str(phone) +"."


                    # We don't know the call ID (not returned via the API
                    # for some annoying reason) so we need to check what
                    # calls are active. This assumes your Plivo account isn't
                    # used a whole heap... PRs for better solution welcome.

                    active = True

                    while active:

                        try:
                            response = p.get_live_calls()

                            if len(response[1]["calls"]) >= 1:
                                print "Info: Waiting for calls to complete..."
                                time.sleep(1)
                            else:
                                print "Info: No calls remaining, proceeding to next message(s)."
                                active = False

                        except:
                            print "Warning: An unexpected fault occured whilst querying call status..."
                            active = True

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

            print 'system: ready to robodial with a vengance!'
            while(True):
                c.beanstalk_poll()

        except KeyboardInterrupt:
            print 'system: User Terminated'
        except socket.error, err:
            print 'system: socket error ' + str(err[0])
