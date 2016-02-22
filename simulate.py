#! /usr/bin/env python
#
# Simulate each of the different alarm conditions.
#

import socket
import sys
import time
import datetime
import string
import re
import signal
import select
import threading
import yaml         # requires pyyaml third party package
import beanstalkc   # requires beanstalkc third party package

class HowAlarmingCLI:
    def __init__(self):
        # Load configuration from YAML file and assign configuration values.
        try:
            self.config         = yaml.load(open('config.yaml', 'r'))

            # Beanstalkd Message Queue settings
            self.beanstalk_host             = self.config['beanstalkd']['host']
            self.beanstalk_port             = int(self.config['beanstalkd']['port'])
            self.beanstalk_tubes_commands   = self.config['beanstalkd']['tubes']['commands']
            self.beanstalk_tubes_events     = self.config['beanstalkd']['tubes']['events']

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

    def beanstalk_push(self, message):
        # Send outputs to all defined event tubes (queues in beanstalk speak).
        for tube in self.beanstalk_tubes_events:
            self.beanstalk.use(tube)
            self.beanstalk.put(message)
        return

    def keyboard_poll(self):
        # Poll STDIN for a newline, when we get one, push to the beanstalkd
        # command tube for processing.
        i,o,e = select.select([sys.stdin],[],[],1)
        for s in i:
            if s == sys.stdin:
                k = sys.stdin.readline()
                k = k[:len(k)-1]

                if k == 'command':
                    self.beanstalk_push('{"type": "command", "code": "123", "message": "Arm alarm command issued", "raw": "123 command issued"}')
                elif k == 'info':
                    self.beanstalk_push('{"type": "info", "code": "236", "message": "Some kind of general information event occured", "raw": "236 INFO GENERAL"}')
                elif k == 'armed':
                    self.beanstalk_push('{"type": "armed", "code": "535", "message": "Alarm now armed", "raw": "535 ARMED"}')
                elif k == 'disarmed':
                    self.beanstalk_push('{"type": "disarmed", "code": "525", "message": "Alarm is disarmed", "raw": "525 disarmed"}')
                elif k == 'response':
                    self.beanstalk_push('{"type": "response", "code": "123", "message": "ACK of command", "raw": "123 response"}')
                elif k == 'alarm':
                    self.beanstalk_push('{"type": "alarm", "code": "911", "message": "Alarm triggered in sector 5", "raw": "911 ALARM ALARM"}')
                elif k == 'recovery':
                    self.beanstalk_push('{"type": "recovery", "code": "1332", "message": "Alarm recovered", "raw": "1332 recovery"}')
                elif k == 'fault':
                    self.beanstalk_push('{"type": "fault", "code": "666", "message": "Flux Capaciter Failed", "raw": "666 FLUXERR"}')
                elif k == 'unknown':
                    self.beanstalk_push('{"type": "unknown", "code": "???", "message": "unknown", "raw": "Unknown error, there\s no helping you now son"}')
                else:
                    print "Request a specific alarm event to simulate from: [command|info|armed|disarmed|response|alarm|recovery|fault|unknown]"
        return


if __name__ == '__main__':
        try:
            c = HowAlarmingCLI()
            c.beanstalk_connect()

            print "system: what time of alarm event would you like to simulate?"
            while(True):
                c.keyboard_poll()

        except KeyboardInterrupt:
            print 'system: User Terminated'
        except socket.error, err:
            print 'system: socket error ' + str(err[0])
