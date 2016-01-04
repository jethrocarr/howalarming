#! /usr/bin/env python
#
# Listens to events from beanstalk event queue and issues alerts via email. A
# very simple alerter.
#
# Don't rely on email alone for your alarm notifications, if it connects
# properly, doesn't get greylisted, doesn't get spam filtered and makes it all
# the way to your inbox it's a miracle.
#
# Only accurate test is to trigger an event, recommend setting it to email on
# 'armed' and 'disarmed' events as a way of testing it out.
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
import yaml			# requires pyyaml third party package
import beanstalkc	# requires beanstalkc third party package

class Itsalarming:
	def __init__(self):
		# Load configuration from YAML file and assign configuration values.
		try:
			self.config			= yaml.load(open('config.yaml', 'r'))

			# Beanstalkd Message Queue settings
			self.beanstalk_host				= self.config['beanstalkd']['host']
			self.beanstalk_port				= int(self.config['beanstalkd']['port'])
			self.beanstalk_tubes_commands	= self.config['beanstalkd']['tubes']['commands']
			self.beanstalk_tubes_events		= self.config['beanstalkd']['tubes']['events']

			# SMTP settings
			self.smtp_host		= self.config['alert_email']['smtp_host']
			self.smtp_port		= self.config['alert_email']['smtp_port']
			self.addr_from		= self.config['alert_email']['addr_from']
			self.addr_to		= self.config['alert_email']['addr_to']
			self.triggers		= self.config['alert_email']['triggers']

			# Make sure the queue we listen to exists
			if 'alert_email' not in self.config['beanstalkd']['tubes']['events']:
				print "Fatal: Config must define the alert_email event queue for this application."
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

		self.beanstalk.watch('alert_email')
		job = self.beanstalk.reserve() # blocking call

		if job:
			# Event recieved, is it on the list of types we care about?
			try:
				alarm_event = json.loads(job.body)

				if alarm_event['type'] in self.triggers:
					print "Recieved alert suitable for emailing, will trigger email event immediately:"
					print job.body

					# Send an alert email.
					smtp_server = smtplib.SMTP(self.smtp_host, self.smtp_port)

					smtp_message = ''
					smtp_message += 'From: '+ self.addr_from +'\r\n'
					smtp_message += 'To: '+ self.addr_to +'\r\n'
					smtp_message += 'Subject: ['+ alarm_event['type'] +'] '+ alarm_event['message'] +'\r\n'
					smtp_message += 'Date: '+ email.utils.formatdate() +'\r\n'
					smtp_message += 'Message-Id: '+ email.utils.make_msgid('itsalarming_alerter') +'\r\n'
					smtp_message += '\r\n'
					smtp_message += job.body +'\r\n'

					smtp_server.sendmail(self.addr_from, self.addr_to, smtp_message)

				else:
					print 'Non-alerting event, ignoring (type: '+ alarm_event['type'] +')'

			except KeyError:
				print "Warning: Unable to process message, invalid JSON: ", job.body

			job.delete()
		return



if __name__ == '__main__':
		try:
			c = Itsalarming()
			c.beanstalk_connect()

			print 'system: ready to send emails!'
			while(True):
				c.beanstalk_poll()

		except KeyboardInterrupt:
			print 'system: User Terminated'
		except socket.error, err:
			print 'system: socket error ' + str(err[0])
