#! /usr/bin/env python
#
# Minimal CLI for interacting with applications via issues commands to/from
# the beanstalk queues. Generally intended for debugging purposes.
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

            # Make sure the queue we listen to exists
            if 'cli' not in self.config['beanstalkd']['tubes']['events']:
                print "Fatal: Config must define the cli event queue for this application."
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

        self.beanstalk.watch('cli')
        job = self.beanstalk.reserve(timeout=1) # Mostly non-blocking Beanstalk poll

        if job:
            # Event recieved, output as-is:
            print job.body

            job.delete()
        return

    def beanstalk_push(self, message):
        # Send outputs to all defined command tubes (queues in beanstalk speak).
        for tube in self.beanstalk_tubes_commands:
            #print 'system: Pushing message \"'+ str(message) +'\" to ' + str(tube) + '.'
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

                if k == '':
                    print "Type a command and hit enter. For example: status"
                else:
                    self.beanstalk_push(k)
        return


if __name__ == '__main__':
        try:
            c = HowAlarmingCLI()
            c.beanstalk_connect()

            print "system: type commands and enter with newline to send them"
            while(True):
                c.beanstalk_poll()
                c.keyboard_poll()

        except KeyboardInterrupt:
            print 'system: User Terminated'
        except socket.error, err:
            print 'system: socket error ' + str(err[0])
