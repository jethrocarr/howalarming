# howalarming

howalarming is a collection of lightweight applications for bidirectional control
of house alarm systems (this includes receiving alerts, but also sending
instructions) making it easy to integrate alarm IP modules with other systems
and writing various support applications.

Currently it includes support for Envisalink enabled alarm modules and alerting
via email, phone calls or mobile apps via push messages.

WARNING: DO NOT USE THIS SYSTEM FOR ANY LIFE THREATENING EVENT INCLUDING FIRE OR
MEDICAL ALERTING. THERE WILL BE BUGS.


# How it works

There are two types of applications - the "alarm integrators", which exchange
messages with the alarm system and the "alarm consumers" which handle alerts or
send commands to the "alarm integrators".

To facilitate communications, [beanstalkd](http://kr.github.io/beanstalkd/) is
used as a lightweight work queue for exchanging messages between applications.

This design makes it easy(ish) to add support for different alarm systems/IP
modules and also feeding events to multiple different applications. For example,
you might have the alarm integrator for DSC/Envisalink and then one app that
triggers an SMS whilst another talks to AWS SNS/SQS to trigger more
sophisticated actions.


# Installation/Configuration

Copy `config.example.yaml` to `config.yaml`. This file should be used by all
the applications, see the relevant sections for each application as needed.

Dependencies:

    # via native OS package manager (eg apt-get, yum, brew):
    beanstalkd
    python-2.7 (probably already on as default, check with python --version)
    
    # for Python apps:
    pip install pyyaml
    pip install beanstalkc
    pip install python-gcm (for alert_gcm_push.py only)
    pip install plivo (for alert_plivo.py only)

Tested on UNIX platforms - in theory it might run OK on Windows, feel free to
submit pull requests fixing any OS compatibility issues if this floats your boat.


# Running

All the applications run in foreground mode. The following commands allow you
to launch them manually, but you'll probably want to launch them with something
like systemd which will deal with logging and restarts much more nicely,
especially since some error coditions like socket timeout with beanstalk or the
alarm will result in the app dying and expecting to be respawned by init.

Launch the beanstalkd server on localhost only:

    beanstalkd -l 127.0.0.1 -p 11300

Launch the alarm daemon:

    # For Envisalink series:
    ./envisalinkd.py

Launch the consumer applications (you can run as many or as few of these
applications to meet your requirements):

    # For debugging/testing only, don't run these daemons :-/
    ./cli.py
    ./simulate.py

    # For email-based alerting
    ./alert_email.py

    # For Google Compute Messaging alerting (to companion Android app)
    ./alert_gcm.py

    # For Plivo alerting (text to speech global voice calling)
    ./alert_plivo.py


# Config Management Support (Puppet)

Alternatively you can install and run HowAlarming via the author's Puppet
module available either on [Github](https://github.com/jethrocarr/puppet-howalarming)
or at the [PuppetForge](https://forge.puppetlabs.com/jethrocarr/howalarming).


# Mobile Applications (via GCM)

The Google Compute Messaging (GCM) application is intended for pushing alarm
events to native mobile applications such as the Android companion application.

The following is the list of compatible applications:

* https://github.com/jethrocarr/howalarming-android
* https://github.com/jethrocarr/howalarming-ios

The applications include instructions around the provisioning of GCM, but
generally you'll need a project setup in Google Developer Console with GCM
enabled in order to get an API key and to get a configuration file for the
mobile applications.



# Supported Hardware

* Envisalink EVL-4 with DSC PowerSeries (envisalinkd.py)



# Message Format

All messages are exchanged between applications via the Beanstalkd queuing
service. The following is the defined data format for message exchange.


## Event messages

The event tubes (queues in beanstalkd speak) contain messages from the alarm
integrator application for all events reported by the alarm system. These take
the form of the following JSON message:

    {"type": "alarm", "code": "123", "message": "event details string", "raw": "123ABC", timestamp: '1199145600'}

Because alarm systems are complex beasts with many hundreds of response types,
we also add a type field indicating the nature of the event. You can then choose
to write generic software that respects any alarm integrator by only actioning
based on the types, or you can write more sophisticated rules that understand
the native code, message or even the raw data itself.

If using the type codes, recommend also providing the message string through to
the end user to help them determine what is taking place.

The following are the acceptable types:

| Type Value    | Meaning                                            |
| ------------- |----------------------------------------------------|
| command       | Echo of any commands issued via the command tubes. |
| info          | Info/status messages from the alarm                |
| armed         | Alarm is now armed (includes in delay arming)      |
| disarmed      | Alarm is now disarmed                              |
| response      | Responses to commands (eg acks)                    |
| alarm         | An alarm has been triggered.                       |
| recovery      | An alarm condition has recovered.                  |
| fault         | A fault has occurred (eg phone down, power outage) |
| unknown       | Ummmm dunno... Flux capacitor on fire?             |



## Command messages

The command tubes contain instructions for the alarm integrator to perform, such
as arm/disarm, status etc.

These commands can be one of two formats, either a JSON command like the
following:

    {"code": "321", "message": "Human readable reference", "data": "Optional data/values to be sent", timestamp: '1199145600'}

Or a "simple" string command. These simple commands should be supported by all
alarm integrators making it easy to add generic support for all supported alarm
systems, whilst still being able to fire native commands as required.

| Command       | Action                                             |
| ------------- |----------------------------------------------------|
| status        | Report status information from alarm               |
| arm           | Arm the alarm system                               |
| disarm        | Disarm the alarm system                            |
| fire          | Trigger the panic alarm (for fire)                 |
| medical       | Trigger the panic alarm (for medical)              |
| police        | Trigger the panic alarm (for police)              |


# Application Security

There's no security/authentication between the components. The intention of this
design is that you run all the applications on a small embedded dedicated alarm
computer (like a Raspberry Pi) or on some VM/container where only trusted
applications will be present and able to talk to the beanstalkd service. The
beanstalkd instance should NEVER be listening on a network reachable port, make
sure you always run it on localhost only.

All security/validation/encryption should take place in your alarm consumers
which take actions with the various events triggered. Some are easy, if you're
doing purely push-only (eg trigger an SMS) the security is simple, but if you're
accepting commands from an HTTP endpoint or app, you need to think carefully
about user validation and potentially command/input validation as well.


# About

Written by Jethro Carr primarily to support an Envisalink EVL-4 with a DSC
PowerSeries alarm, however the design should make it adaptable for other
system in future.

Credit to @dumbo25 for the original Envisalink code at
https://github.com/dumbo25/ev3_cmd which has formed the base of the
Envisalink integration in `envisalinkd.py`

Pull requests including docs, bug fixes, new alarm support, new alarm consumers,
etc always welcome.


# License

Unless otherwise stated, all source code is:

    Copyright (c) 2016 Jethro Carr

    Permission is hereby granted, free of charge, to any person obtaining a copy of
    this software and associated documentation files (the "Software"), to deal in
    the Software without restriction, including without limitation the rights to
    use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
    of the Software, and to permit persons to whom the Software is furnished to do
    so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
