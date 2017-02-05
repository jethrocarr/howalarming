#! /usr/bin/env python
#
# Listens to events from beanstalk event queue and hit HTTP endpoints as
# requested.
#
# Only accurate test is to trigger an event, recommend setting it to call on
# 'armed' and 'disarmed' events for testing, but once setup, probably only want
# alerts for 'alarm', 'recovery' and 'fault'
#

import os
import socket
import sys
import time
import datetime
import string
import re
import signal
import select
import json
import requests
import yaml         # requires pyyaml third party package
import beanstalkc   # requires beanstalkc third party package


# Unbuffered Logging
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

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

            # url Settings
            self.urls         = self.config['alert_url']['urls']
            self.triggers     = self.config['alert_url']['triggers']

            # Make sure the queue we listen to exists
            if 'alert_url' not in self.config['beanstalkd']['tubes']['events']:
                print "Fatal: Config must define the alert_url event queue for this application."
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
        # Poll for any commands in the event tube for url

        self.beanstalk.watch('alert_url')
        job = self.beanstalk.reserve() # blocking call

        if job:
            # Event recieved, is it on the list of types we care about?
            try:
                alarm_event = json.loads(job.body)

                if alarm_event['type'] in self.triggers:
                    print "Recieved alert suitable for sending to url, triggering call for each configured URL"
                    print job.body

                    # Dial each number configured via url service
                    for url in self.urls:

                        # Assemble the URL to HTTP GET
                        url = url + alarm_event['type']
                        print "Hitting URL "+ url

                        # Send a GET request to the URL.
                        try:
                            request = requests.get(url, timeout=5)

                            if request.status_code != 200:
                                print "Warning: An HTTP response code of "+ request.status_code +" was recieved"
                            else:
                                print "... successful"
                        except:
                            print "Warning: An unexpected fault occured when attempting to hit URL: "+ url

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

            print 'system: url curl\'n at the ready capt\'n'
            while(True):
                c.beanstalk_poll()

        except KeyboardInterrupt:
            print 'system: User Terminated'
        except socket.error, err:
            print 'system: socket error ' + str(err[0])
