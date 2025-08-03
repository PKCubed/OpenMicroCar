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
