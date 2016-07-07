#! /usr/bin/env python
#
# Wrapper launcher for the Java GCM server application used for bi-directional
# comms between GCM and HowAlarming mobile apps.
#
# For more information and source code of the Java server, please see:
# https://github.com/jethrocarr/howalarming-gcm
#
# Refer to the README for more information.
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
import os
import yaml         # requires pyyaml third party package

# Unbuffered Logging
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)


# Load configuration from YAML file and assign configuration values.
try:
    config         = yaml.load(open('config.yaml', 'r'))

    # Beanstalkd Message Queue settings
    beanstalk_host             = config['beanstalkd']['host']
    beanstalk_port             = int(config['beanstalkd']['port'])
    beanstalk_tubes_commands   = config['beanstalkd']['tubes']['commands']
    beanstalk_tubes_events     = config['beanstalkd']['tubes']['events']

    # GCM
    gcm_api_key                = config['alert_gcm']['api_key']
    gcm_sender_id              = config['alert_gcm']['sender_id']
    gcm_registration_tokens    = config['alert_gcm']['registration_tokens']
    triggers                   = config['alert_gcm']['triggers']

    # Make sure the queue we listen to exists
    if 'alert_gcm' not in config['beanstalkd']['tubes']['events']:
	print "Fatal: Config must define the alert_gcm event queue for this application."
	raise BaseException

except IOError:
    print 'Fatal: Could not open configuration file'
    raise

except (KeyError, AttributeError) as err:
    print 'Fatal: Unable to find required configuration in config.yaml'
    raise


# The Java application runs using environmentals for it's configuration, so we
# take the config we've loaded in via YAML and set appropiate environmentals.

os.environ["GCM_SENDER_ID"]		= str(gcm_sender_id)
os.environ["GCM_API_KEY"]		= str(gcm_api_key)
os.environ["BEANSTALK_HOST"]		= str(beanstalk_host)
os.environ["BEANSTALK_PORT"]		= str(beanstalk_port)
os.environ["BEANSTALK_TUBES_EVENTS"]	= "alert_gcm"
os.environ["BEANSTALK_TUBES_COMMANDS"]	= "commands" # TODO: Nasty hard coding for prototype phase

print "!!!!!!!"
print "WARNING: EXPERIMENTAL JAVA SERVER, BUGGY AND HARDCODING AWAITS"
print "!!!!!!!"


# Run the application in foreground until it terminates.
os.system("java -jar resources/gcmserver/HowAlarmingServer-all-latest.jar")

