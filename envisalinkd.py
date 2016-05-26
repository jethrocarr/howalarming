#! /usr/bin/env python
#
# Alarm integration with the TPI interface for the Envisalink alarm IP module.
#
# Essentially we connect to the module's TCP socket, authenticate and then
# exchange commands and alerts to/from the configured beanstalk tubes to be
# used by other applications.
#
# Based on source code by dumbo25 at https://github.com/dumbo25/ev3_cmd
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
import threading
import json
import yaml         # requires pyyaml third party package
import beanstalkc   # requires beanstalkc third party package

# Unbuffered Logging
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

class Envisalink:
    def __init__(self):
        # Load configuration from YAML file and assign configuration values.
        try:
            self.config         = yaml.load(open('config.yaml', 'r'))

            # General Envislink/Alarm Settings
            self.host           = self.config['envisalinkd']['host']
            self.port           = int(self.config['envisalinkd']['port'])
            self.password       = self.config['envisalinkd']['password']
            self.code_master    = self.config['envisalinkd']['code_master']
            self.code_installer = self.config['envisalinkd']['code_installer']
            self.zones          = self.config['envisalinkd']['zones']

            # Because the zone ids are 3 digit long ints, if the user hasn't
            # quoted them in the YAML, they get convered to ints and then
            # break. Hence we convert them to strings and pad with zeros to
            # support either int or string input.
            self.zones = {str(k).zfill(3):str(v) for k,v in self.zones.items()}

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

        # Fixed defaults
        self.loggedin = False
        self.poll_ack = True
        self.max_poll_retries = 3
        self.poll_retries = 0
        self.max_partitions = 1
        self.max_zones = len(self.zones.keys())
        self.sleep = 0
        self.file_log = sys.stdout # Use STDOUT for all logging
        self.printMutex = threading.Lock()
        self.socketMutex = threading.Lock()

        # Are modes always the same across alarms, or are they configurable? For now, treating as a fixed value.
        self.modes = {'0' : 'Away', '1' : 'Stay in house', '2' : 'Zero entry away', '3' : 'Zero entry stay in house'}

        # Commands needed to decode 500 ack
        self.commands = {'000' : 'poll',
            '001' : 'status report',
            '005' : 'login',
            '008' : 'dump zone timers',
            '010' : 'set time and date',
            '020' : 'command output',
            '030' : 'partition arm',
            '031' : 'stay arm',
            '032' : 'zero entry delay',
            '033' : 'arm',
            '040' : 'disarm',
            '055' : 'timestamp',
            '056' : 'time',
            '057' : 'temperature',
            '060' : 'trigger panic alarm',
            '070' : 'use 071 command',
            '071' : 'keypad command',
            '072' : 'user code programming',
            '073' : 'user programming',
            '074' : 'keep alive',
            '200' : 'send code'
            }
        self.responses = {'500' : 'command acknowledge',
            '501' : 'command error',
            '502' : 'system error',
            '505' : 'login',
            '510' : 'keypad LED state',
            '511' : 'keypad LED flash state',
            '550' : 'time/date Broadcast',
            '560' : 'ring detected',
            '561' : 'indoor temperature',
            '562' : 'outdoor temperature',
            '601' : 'alarm',
            '602' : 'alarm clear',
            '603' : 'tamper',
            '604' : 'tamper clear',
            '605' : 'zone fault',
            '606' : 'zone fault clear',
            '609' : 'zone open',
            '610' : 'zone closed',
            '615' : 'zone timer dump',
            '620' : 'duress alarm',
            '621' : 'fire key alarm',
            '622' : 'fire key alarm clear',
            '623' : 'auxillary key alarm',
            '624' : 'auxillary alarm clear',
            '625' : 'panic alarm',
            '626' : 'panic alarm clear',
            '631' : 'smoke/aux alarm',
            '632' : 'smoke/aux alarm clear',
            '650' : 'partition ready',
            '651' : 'partition not ready',
            '652' : 'partition armed',
            '653' : 'partition force arming enabled',
            '654' : 'partition alarm',
            '655' : 'partition disarmed',
            '656' : 'partition exit delay',
            '657' : 'partition entry delay',
            '658' : 'partition keypad lockout',
            '659' : 'partition failed to arm',
            '660' : 'partition PGM output',
            '663' : 'chime enabled',
            '664' : 'chime disabled',
            '670' : 'partition invalid access',
            '671' : 'partition function not available',
            '672' : 'partition failure to arm',
            '673' : 'partition is busy',
            '674' : 'partition arming',
            '680' : 'installer\'s mode',
            '700' : 'partition user closing',
            '701' : 'partition armed by method',
            '702' : 'partition armed, but zone(s) bypassed',
            '750' : 'partition disarmed by user',
            '751' : 'partition disarmed by method',
            '800' : 'closet panel battery trouble',
            '801' : 'closet panel battery okay',
            '802' : 'closet panel AC trouble',
            '803' : 'closet panel AC okay',
            '806' : 'system bell trouble',
            '807' : 'system bell okay',
            '814' : 'closet panel cannot communicate with monitoring.',
            '816' : 'buffer nearly full',
            '829' : 'general system tamper',
            '830' : 'general System Tamper Restore',
            '840' : 'partition trouble LED on',
            '841' : 'partition trouble LED off',
            '842' : 'fire trouble alarm',
            '843' : 'fire trouble alarm cleared',
            '849' : 'verbose trouble status',
            '900' : 'code required',
            '912' : 'command output pressed',
            '921' : 'master code required',
            '922' : 'installer\'s code required'
            }
        self.errorCodes = {'000' : 'no error',
            '001' : 'last command not finished',
            '002' : 'receive buffer overflow',
            '003' : 'transmit buffer overflow',
            '010' : 'keybus transmit buffer overrun',
            '011' : 'keybus transmit time timeout',
            '012' : 'keybus transmit mode timeout',
            '013' : 'keybus transmit keystring timeout',
            '014' : 'keybus interface failure',
            '015' : 'keybus disarming or arming with user code',
            '016' : 'keybus keypad lockout, too many disarm attempts',
            '017' : 'keybus closet panel in installer\'s mode',
            '018' : 'keybus requested partition is busy',
            '020' : 'API command syntax error',
            '021' : 'API partition out of bounds',
            '022' : 'API command not supported',
            '023' : 'API disarm attempted, but not armed',
            '024' : 'API not ready to arm',
            '025' : 'API command invalid length',
            '026' : 'API user code not required',
            '027' : 'API invalid characters'
            }


    def beanstalk_connect(self):
        try:
            self.beanstalk = beanstalkc.Connection(host=self.beanstalk_host, port=self.beanstalk_port)
            self.printNormal('system: Beanstalkd connected on ' + str(self.beanstalk_host) + ' on port ' + str(self.beanstalk_port))
        except socket.error, (value,message):
            self.printFatal(message)


    def beanstalk_poll(self):
        # Poll for any commands in the command tubes. (Note we generally only
        # expect a single tube, but we can support multiples just like with
        # the event tubes).

        for tube in self.beanstalk_tubes_commands:
            self.beanstalk.watch(tube)

            job = self.beanstalk.reserve(timeout=0) # Non-blocking Beanstalk poll

            if job:
                # We have a job returned, we now need to process the command and
                # determine what action to take (if any)

                if job.body == 'arm':
                    self.sendCommand('030', 'Partition Arm', '1')
                elif job.body == 'disarm':
                    self.sendCommand('040', 'Partition Disarm', '1' + str(self.code_master))
                elif job.body == 'fire':
                    self.sendCommand('060', 'Fire Panic Button', '1')
                elif job.body == 'medical':
                    self.sendCommand('060', 'Medical Panic Button', '2')
                elif job.body == 'police':
                    self.sendCommand('060', 'Police Panic Button', '3')
                elif job.body == 'status':
                    self.sendCommand('001', 'keyboard: status')
                elif self.is_json(job.body):
                    self.printNormal('JSON command issued: ' + job.body)
                    command_obj = json.loads(job.body)

                    if 'code' in command_obj:
                        # Only the code to be issued is required, data values and message are optional
                        # but we need to define them to avoid spewing KeyErrors everywhere.
                        if 'message' not in command_obj:
                            command_obj['message'] = 'Unknown Command'
                        if 'data' not in command_obj:
                            command_obj['data'] = ''

                        self.sendCommand(command_obj['code'], command_obj['message'], command_obj['data'])
                    else:
                        self.printNormal('system: unrecognized command via JSON')
                else:
                    self.printNormal('system: unrecognized command = ' + job.body)

                # Cleanup
                job.delete()
        return

    def beanstalk_push(self, message):
        # Encode in JSON format
        message_json = json.dumps(message)

        # Send outputs to all defined event tubes (queues in beanstalk speak).
        for tube in self.beanstalk_tubes_events:
            #self.printNormal('system: Pushing message \"'+ str(message_json) +'\"to ' + str(tube) + '.')
            self.beanstalk.use(tube)
            self.beanstalk.put(message_json)
        return

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.socket.settimeout(None)
            self.socket.setblocking(0)
            self.printNormal('system: connect ' + str(self.host) + ' on port ' + str(self.port))
            self.status['system'] = 'connected'
        except socket.error, (value,message):
            self.printFatal(message)

    def login(self):
        time.sleep(1)
        self.sendCommand(005, 'login', self.password)

    def sendCommand(self, command, msg, data_bytes = []):
        # send one message at a time
        self.socketMutex.acquire()
        try:
            cmd_bytes = str(command).zfill(3)
            cmd = []
            checksum = 0
            for byte in cmd_bytes:
                cmd.append(byte)
                checksum += ord(byte)
            for byte in data_bytes:
                cmd.append(byte)
                checksum += ord(byte)

            checksum = checksum % 256
            cmd.extend([hex(nibble)[-1].upper() for nibble in [ checksum / 16, checksum % 16]])
            cmd.extend((chr(0x0D), chr(0x0A)))

            self.printNormal("send [" + ''.join(cmd[:len(cmd)-4]) + "]: " + msg)

            try:
                # We send the commands to the alarm, but we also advise the
                # listening applications on what commands we are running.
                self.socket.send(''.join(cmd))
		self.beanstalk_push({'type': 'command', 'raw': cmd, 'code': cmd, 'message': msg, 'timestamp': int(time.time())})
            except socket.error, err:
                e.printFatal('socket error '+ str(err[0]) + ' in sendCommand ' )

        finally:
            self.socketMutex.release()

    def receiveResponse(self):
        try:
            msg = ''
            while True:
                rsp = self.socket.recv(4096)
                if len(rsp) == 0:
                    # try to re-establish connection
                    self.printNormal('Envisalink closed the connection. Try to reconnect')
                    return 'c'
                    # self.printFatal('Envisalink closed the connection')
                # remove return and line feed
                words = string.split(rsp, '\r\n')
                if words == ['']:
                    break

                msg = 'm'
                # remove checksum and decode word
                # might want to use checksum before processing response
                for i in range(0,len(words)):
                    word = ''.join(words[i][:len(words[i])-2])
                    if word != '':
                        words[i] = word
                        self.decodeResponse(word)
            return msg

        except socket.error, (value,message):
            # non-blocking socket correctly returns an error of temporarily unavailable
            # self.printNormal('system: ' + message)
            return ''
        return ''

    def decodeResponse(self, word):
        cmd = word[:3]
        msg = ''
        event_type = 'unknown'

        if cmd == '':
            return
        elif cmd == '500':
            data = word[3:6]
            if data != '':
                if data == '000':
                    self.loggedin = True
                    self.poll_ack = True
                    self.sleep = 0
                    self.status['system'] = 'logged in'

                event_type = 'response'
                msg += "ack " + self.commands[data]
            else:
                event_type = 'response'
                msg += "no ack command"
        elif cmd == '501':
            event_type = 'fault'
            msg += 'command error, bad checksum'
        elif cmd == '502':
            event_type = 'fault'
            data = word[3:6]
            msg += 'system error = ' + self.errorCodes[data]
        elif cmd == '505':
            if word[3:4] == '0':
                self.printFatal(msg + "password is incorrect")
            elif word[3:4] == '1':
                msg += "login successful"
                event_type = 'info'
                self.status['system'] = 'logged in'
                self.loggedin = True
            elif word[3:4] == '2':
                self.printFatal(msg + "login timed out. password not sent within 10 seconds of connection.")
            elif word[3:4] == '3':
                event_type = 'response'
                msg += "socket setup. request password"
                # this is where login should go, but it is much less reliable
                # and causes problems
                # self.login()
        elif cmd == '510':
            event_type = 'info'
            self.status['system'] = 'disarmed'
            msg += 'lit keypad LEDs = '
            b = int(word[3:5],16)

            # Bit 0 - Ready LED lit
            if b & 0x01 != 0:
                msg += 'ready '
            # Bit 1 - Armed LED lit
            if b & 0x02 != 0:
                msg += 'armed '
                self.status['system'] = 'armed'
            # Bit 2 - Memory LED lit
            if b & 0x04 != 0:
                msg += 'memory '
            # Bit 3 - Bypass LED lit
            if b & 0x08 != 0:
                msg += 'bypass '
            # Bit 4 - Trouble LED lit
            if b & 0x10 != 0:
                msg += 'trouble '
            # Bit 5 - Program LED lit
            if b & 0x20 != 0:
                msg += 'program '
            # Bit 6 - Fire LED lit
            if b & 0x40 != 0:
                msg += 'fire '
            # Bit 7 - Backlight LED lit
            if b & 0x80 != 0:
                msg += 'backlight '

        elif cmd == '511':
            event_type = 'info'
            msg += 'flashing keypad LEDs = '
            b = int(word[3:5],16)

            # Bit 0 - Ready LED lit
            if b & 0x01 != 0:
                msg += 'ready '
            # Bit 1 - Armed LED lit
            if b & 0x02 != 0:
                msg += 'armed '
            # Bit 2 - Memory LED lit
            if b & 0x04 != 0:
                msg += 'memory '
            # Bit 3 - Bypass LED lit
            if b & 0x08 != 0:
                msg += 'bypass '
            # Bit 4 - Trouble LED lit
            if b & 0x10 != 0:
                msg += 'trouble '
            # Bit 5 - Program LED lit
            if b & 0x20 != 0:
                msg += 'program '
            # Bit 6 - Fire LED lit
            if b & 0x40 != 0:
                msg += 'fire '
            # Bit 7 - Backlight LED lit
            if b & 0x80 != 0:
                msg += 'backlight '

        elif cmd == '550':
            event_type = 'info'
            msg += 'time and date ' + word[3:5] + ":" + word[5:7] + " " + word[7:9] + "/" + word[9:11] + "/20" + word[11:13]
        elif cmd == '560':
            event_type = 'info'
            msg += 'ring detected'
        elif cmd == '561':
            event_type = 'info'
            msg += 'indoor temperature = ' + word[3:7]
        elif cmd == '562':
            event_type = 'info'
            msg += 'outdoor temperature = ' + word[3:7]
        elif cmd == '601':
            zone = word[4:7]
            partition = word[3:4]
            if int(zone) <= self.max_zones:
                if int(partition) <= self.max_partitions:
                    msg += 'alarm. partition = ' + partition + ' zone = ' + self.zones[zone]
                    event_type = 'alarm'
        elif cmd == '602':
            zone = word[4:7]
            partition = word[3:4]
            if int(zone) <= self.max_zones:
                if int(partition) <= self.max_partitions:
                    msg += 'alarm cleared. partition = ' + partition + ' zone = ' + self.zones[zone]
                    event_type = 'recovery'
        elif cmd == '603':
            zone = word[4:7]
            partition = word[3:4]
            if int(zone) <= self.max_zones:
                if int(partition) <= self.max_partitions:
                    msg += 'tamper. partition = ' + partition + ' zone = ' + self.zones[zone]
                    event_type = 'alarm'
        elif cmd == '604':
            zone = word[4:7]
            partition = word[3:4]
            if int(zone) <= self.max_zones:
                if int(partition) <= self.max_partitions:
                    msg += 'tamper cleared. partition = ' + partition + ' zone = ' + self.zones[zone]
                    event_type = 'recovery'
        elif cmd == '605':
            zone = word[3:6]
            if int(zone) <= self.max_zones:
                msg += 'zone ' + self.zones[zone] + ' fault'
                event_type = 'alarm'
        elif cmd == '606':
            zone = word[3:6]
            if int(zone) <= self.max_zones:
                msg += 'zone ' + self.zones[zone] + ' fault cleared'
                event_type = 'recovery'
        elif cmd == '609':
            zone = word[3:6]
            if int(zone) <= self.max_zones:
                msg += 'zone ' + self.zones[zone] + ' open'
                event_type = 'info'
        elif cmd == '610':
            zone = word[3:6]
            if int(zone) <= self.max_zones:
                msg += 'zone ' + self.zones[zone] + ' closed'
                event_type = 'info'
        elif cmd == '615':
            # don't care about all the zone timers
            msg += 'received [615]: zone timer dump'
            event_type = 'info'
        elif cmd == '620':
            msg += 'duress alarm'
            event_type = 'alarm'
        elif cmd == '621':
            msg += 'fire key alarm detected'
            event_type = 'alarm'
        elif cmd == '622':
            msg += 'fire key alarm restored'
            event_type = 'recovery'
        elif cmd == '623':
            msg += 'auxillary key alarm detected'
            event_type = 'alarm'
        elif cmd == '624':
            msg += 'auxillary key alarm restored'
            event_type = 'recovery'
        elif cmd == '625':
            msg += 'panic key detected'
            event_type = 'alarm'
        elif cmd == '626':
            msg += 'panic key restored'
            event_type = 'recovery'
        elif cmd == '631':
            msg += 'smoke/aux alarm detected'
            event_type = 'alarm'
        elif cmd == '632':
            msg += 'smoke/aux alarm restored'
            event_type = 'recovery'
        elif cmd == '650':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' ready'
                event_type = 'info'
        elif cmd == '651':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' not ready'
                event_type = 'info'
        elif cmd == '652':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' armed, mode = ' + self.modes[word[4:5]]
                event_type = 'armed'
        elif cmd == '653':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' forcing alarm enabled'
                event_type = 'info'
        elif cmd == '654':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' in alarm'
                event_type = 'alarm'
        elif cmd == '655':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' disarmed'
                event_type = 'disarmed'
        elif cmd == '656':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' exit delay'
                event_type = 'armed'
        elif cmd == '657':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' entry delay'
                event_type = 'info'
        elif cmd == '658':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' keypad lockout'
                event_type = 'alarm'
        elif cmd == '659':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' failed to arm'
                event_type = 'fault'
        elif cmd == '660':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' PGM output'
                event_type = 'info'
        elif cmd == '663':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' chime enabled'
                event_type = 'info'
        elif cmd == '664':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' chime disabled'
                event_type = 'info'
        elif cmd == '670':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' invalid access code'
                event_type = 'alarm'
        elif cmd == '671':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' function not available'
                event_type = 'fault'
        elif cmd == '672':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' failure to arm'
                event_type = 'fault'
        elif cmd == '673':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' is busy'
                event_type = 'fault'
        elif cmd == '674':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' is arming'
                event_type = 'info'
        elif cmd == '680':
            msg += 'system in installer\'s mode'
            event_type = 'alarm'
        elif cmd == '700':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition = ' + partition + 'armed by user'
                event_type = 'info'
        elif cmd == '701':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' armed by method'
                event_type = 'info'
        elif cmd == '702':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' armed but zone(s) bypassed'
                event_type = 'info'
        elif cmd == '750':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' disarmed by user'
                event_type = 'info'
        elif cmd == '751':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' partition disarmed by method'
                event_type = 'info'
        elif cmd == '800':
            msg += 'closet panel battery trouble'
            event_type = 'fault'
        elif cmd == '801':
            msg += 'closet panel battery restore'
            event_type = 'fault'
        elif cmd == '802':
            msg += 'closet panel AC trouble'
            event_type = 'fault'
        elif cmd == '803':
            msg += 'closet panel AC retored'
            event_type = 'fault'
        elif cmd == '806':
            msg += 'bell trouble'
            event_type = 'fault'
        elif cmd == '807':
            msg += 'bell restored'
            event_type = 'fault'
        elif cmd == '814':
            msg += 'closet panel failed to communicate with monitoring'
            event_type = 'fault'
        elif cmd == '816':
            msg += 'buffer near full'
            event_type = 'fault'
        elif cmd == '829':
            msg += 'general system tamper'
            event_type = 'alarm'
        elif cmd == '830':
            msg += 'general system tamper cleared'
            event_type = 'recovery'
        elif cmd == '840':
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' trouble LED on'
                event_type = 'fault'
        elif cmd == '841':
            event_type = 'info'
            partition = word[3:4]
            if int(partition) <= self.max_partitions:
                msg += 'partition ' + partition + ' trouble LED off'
                event_type = 'info'
        elif cmd == '842':
            event_type = 'alarm'
            msg += 'fire trouble alarm'
        elif cmd == '843':
            event_type = 'recovery'
            msg += 'fire trouble alarm cleared'
        elif cmd == '849':
            event_type = 'fault'
            msg += 'verbose trouble status = '
            b = int(word[3:5],16)

            # Bit 0 - Service required
            if b & 0x01 != 0:
                msg += 'service required | '
            # Bit 1 - AC power lost
            if b & 0x02 != 0:
                msg += 'AC power lost | '
            # Bit 2 - telephone line fault
            if b & 0x04 != 0:
                msg += 'telephone line fault (ignore) | '
            # Bit 3 - failure to communicate
            if b & 0x08 != 0:
                msg += 'failure to communicate | '
            # Bit 4 - sensor/zone fault
            if b & 0x10 != 0:
                msg += 'sensor/zone fault | '
            # Bit 5 - sensor/zone tamper
            if b & 0x20 != 0:
                msg += 'sensor zone tamper | '
            # Bit 6 - low battery
            if b & 0x40 != 0:
                msg += 'low battery '

            self.printNormal(msg)
        elif cmd == '900':
            msg += 'code required'
            event_type = 'response'
            # the master code should be a variable and in a config file
            self.sendCommand('200', 'code send', self.code_master)
        elif cmd == '912':
            # don't care about data
            event_type = 'response'
            msg += 'command output pressed'
        elif cmd == '921':
            event_type = 'response'
            msg += 'master code required'
        elif cmd == '922':
            event_type = 'response'
            msg += 'installer\'s code required'
        else:
            if len(msg) > 20:
                msg += "received[too long]: unhandled response"
                event_type = 'fault'
            else:
                msg += "unhandled response"
                event_type = 'fault'

        # Not all events should be broadcast, for example we don't bother
        # reporting unconfigured zones, even though we get told about them
        # by status queries.
        if msg:
            # Assembled completed response
            self.printNormal('received ['+ event_type +'][' + word + ']: ' + msg)

            response = {'type': event_type, 'raw': word, 'code': cmd, 'message': msg}
            self.beanstalk_push(response)

        return

    def timeStamp(self):
        t = time.time()
        s = datetime.datetime.fromtimestamp(t).strftime('%Y/%m/%d %H:%M:%S - ')
        return s

    def printNormal(self, msg):
        self.printMutex.acquire()
        try:
            print >> self.file_log, self.timeStamp() + msg
        finally:
            self.printMutex.release()


    def printFatal(self, msg):
        self.printMutex.acquire()
        try:
            try:
                print >> self.file_log, self.timeStamp() + "fatal: " + msg
                self.socket.shutdown(SHUT_RDWR)
                time.sleep(1)
                self.socket.close()
            except socket.error, (value,message):
                print >> self.file_log, self.timeStamp() + "system: " + message
        finally:
            self.printMutex.release()
            self.exitData()
            sys.exit()

    def resetData(self):
        self.status = {'system' : 'unknown', 'alarm' : 'unknown', 'script' : 'unknown'}
        self.status_zones = {'001' : 'unknown', '002' : 'unknown', '003' : 'unknown', '004' : 'unknown', '005' : 'unknown', '006' : 'unknown'}

    def exitData(self):
        self.resetData()

    def getStatus(self):
        self.sendCommand(001, 'get status')
        return True

    def poll(self):
        if self.poll_ack == True:
            self.poll_ack = False
            self.poll_retries = 0
            self.sendCommand(0, 'poll')
        else:
            if self.poll_retries == self.max_poll_retries:
                # try to reconnect ?
                self.printFatal('connection closed, no response to poll')
            else:
                self.sendCommand(0, 'poll')
                self.poll_retries += 1
                self.printNormal('system: poll retry = ' + str(self.poll_retries))

        # every 60s * N minutes send a poll
        self.p = threading.Timer(60*10, e.poll)
        self.p.daemon = True
        self.p.start()
        return

    def is_json(self, myjson):
        try:
            json_object = json.loads(myjson)
        except ValueError, e:
            return False

        return True


if __name__ == '__main__':
        try:
            e = Envisalink()
            e.printNormal('system: start envisalinkd')
            e.resetData()
            e.connect()
            e.beanstalk_connect()
            e.login()

            # get status of security system
            e.getStatus()

            e.poll()

            # monitor loop
            max_login_wait = 3
            login_wait = 0
            e.sleep = 0
            while(True):
                e.beanstalk_poll()
                rsp = e.receiveResponse()
                if rsp == 'c':
                    e.socket.close()
                    e.resetData()
                    time.sleep(10)
                    e.loggedin = False
                    login_wait = 0
                    e.sleep = 0
                    e.connect()
                    e.login()
                elif rsp == '':
                    e.sleep += 1
                    if e.sleep == 10:
                        if e.loggedin == False:
                            if login_wait == max_login_wait:
                                e.printFatal('failed to login or logged out')
                            else:
                                login_wait += 1
                                e.printNormal('system: login wait = ' + str(login_wait))
                        e.sleep = 0
                    else:
                        time.sleep(1)
                else:
                    # does it ever get here ?
                    e.printNormal('system: rsp = ' + rsp)

        except KeyboardInterrupt:
            e.printFatal('system: User terminated execution')
        except socket.error, err:
            e.printFatal('socket error ' + str(err[0]))
