# ANTISTEAL

Antisteal is a collection of lightweight applications for bidirectional control
of house alarm systems (this includes receiving alerts, but also sending
instructions) making it easy to integrate alarm IP modules with other systems
and writing various support applications.

WARNING: DO NOT USE THIS SYSTEM FOR ANY LIFE THREATENING EVENT INCLUDING FIRE OR
MEDICAL ALERTING. THERE WILL BE BUGS.


# How it works

There are two types of applications - the "alarm integrators", which exchange
messages with the alarm system and the "alarm consumers" which handle alerts or
send commands to the "alarm integrators".

To facilitate communications, beanstalkd (http://kr.github.io/beanstalkd/) is
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


# Running

All the applications run in foreground mode. The following commands allow you
to launch them manually, but you'll probably want to launch them with something
like systemd which will deal with logging and restarts much more nicely.

Launch the beanstalkd server on localhost only:

    beanstalkd -l 127.0.0.1 -p 11300

Launch the alarm daemon:

    # For Envisalink series:
    ./envisalinkd.py

Launch the consumer applications (you can run as many or as few of these
applications to meet your requirements):

    # For SMS alerting
    ./smsd.py



# Supported Hardware

* Envisalink EVL-4 with DSC PowerSeries (envisalinkd)



# Message Format

All messages are exchanged between applications via the Beanstalkd queuing
service. The following is the defined data format for message exchange.


## Event messages

The event tubes (queues in beanstalkd speak) contain messages from the alarm
integrator application for all events reported by the alarm system. These take
the form of the following JSON message:

    {"type": "alarm", "raw": "123ABC", "code": "123", "message": "event details string"}

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
| response      | Responses to commands (eg acks)                    |
| alarm         | An alarm has been triggered.                       |
| recovery      | An alarm condition has recovered.                  |
| fault         | A fault has occurred (eg phone down, power outage) |



## Command messages

The command tubes contain instructions for the alarm integrator to perform, such
as arm/disarm, status etc.

These commands can be one of two formats, either a JSON command like the
following:

    {"code": "321", "message": "Human readable reference", "data": "Optional data/values to be sent"}

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


# About

Written by Jethro Carr primarily to support an Envisalink EVL-4 with a DSC
PowerSeries alarm, however the design should make it adaptable for other
system in future.

Credit to dumbo25 for the original Envisalink code at
(https://github.com/dumbo25/ev3_cmd) which has formed the base of the
Envisalink integration.


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
