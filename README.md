# OpenMicroCar
An ESP32 based 4-motor vehicle designed as a single circuit board.

The idea here is to build 4 or more of these, and play a game of capture the flag with an analog FPV system on each little car. The IR leds and receivers will be used to "shoot" other cars laser-tag style. The ESP32s will use WiFi, or something else to communicate with a raspberry pi server. There will be two zones, one for each team, that are considered safe zones for that team, and will be another esp32 or esp8266 that has an IR receiver. When that receiver detects a car's infrared transmission, it knows it is in the safe zone. An opponent can drive into the safe zone of it's opposing team to capture its flag. It then has to get back to it's safe zone. If it is shot in the middle by the opponent, the flag is transferred to the car that shot it. They then have to bring it to their safe side. If a car gets shot, it must drive back to its safe zone before it can shoot or capture flags.

A car will be colored with its team color, orange or purple. When a car has a flag, the LEDs will blink in a fast pattern. When a car has been shot, its leds get dim and some leds fade red until it gets back to safety. When a car is shot, but is still in a safe zone, some leds will flash white and quickly fade back to the team color.

This tiny car has a PCB footprint of just 55 by 85.5 millimeters. The components all together cost under $30. It's designed to have 4 N20 motors soldered to the bottom, and held on by wrapping 2 lengths of wire around them and soldering to the PCB. Each motor has its own PWM control, as well as direction and braking control.

There are 12 infrared leds positioned around the car, all broadcasting the same signal from the ESP32 through a transistor. There are 2 IR receivers. One in the front designed to be the "shooting" receiver, and one in the back to alert the driver if they are being followed (may or may not get implemented).

There are also 12 WS2812b addressable RGB leds on each car. 8 facing down, and 4 facing up.

There is provision for a speaker and amplifier IC on board. This can be used to make beeps and boops, or maybe I'll try to output actual sampled sounds.


![alt text](Images/Screenshot%202025-08-03%20080516.png)
![alt text](Images/Screenshot%202025-08-03%20080527.png)

# Communication Details
Everything here is just my plans. Nothing has been actually tested and done yet.

Each car will be controlled through a web interface on people's phones. This web interface will come from a python program on a raspberry pi. When someone want's their car to go forward, they press the button on the web interface, which the python program sees, and then sends via wifi socket to the esp32 on that person's car, that they want to go forward. If the car doesn't hear from the python program for 1 second, it shuts off and goes to the disconnected failsafe state, that way it won't just drive away. We want the button latency to be as low as possible, approaching imperceptible.

Each car will send out a couple bytes through the IR leds that will let other cars know which car it is. This will be the car ID code.

People can also press the shoot button on their phone. This will tell the python program to request a shoot from the car. This will then read data through the IR receiver, and save any car ID codes it sees. It will report these back to python. At the same time, if the safe zone receivers see any IR car ID codes, Python will have seen that. If any of the shot cars match the safe cars, they will not be affected, but will be sent the safe shot signal to flash their LEDs and make a noise similar to that you get when you shoot a metal baloon in BTD Battles. If a car is not detected to be in a safe zone, it will be sent the shot signal, and it will be marked as shot until python sees it has been received by it's safe zone receiver.