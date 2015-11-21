import wiringpi2 as wiringpi
from time import sleep
import signal
import sys


ON = 0
OFF = 1

pin_base = 65       # lowest available starting number is 65
chip1_i2c_addr = 0x21     # A0, A1, A2 pins all wired to GND 
chip2_i2c_addr = 0x22     # A0, A1, A2 pins all wired to GND
chip3_i2c_addr = 0x23     # A0, A1, A2 pins all wired to GND 
chip4_i2c_addr = 0x24     # A0, A1, A2 pins all wired to GND

wiringpi.wiringPiSetup()                    # initialise wiringpi

wiringpi.mcp23017Setup(pin_base,   chip1_i2c_addr)   # pins 65-80
wiringpi.mcp23017Setup(pin_base+16,chip2_i2c_addr)   # pins 81-96
wiringpi.mcp23017Setup(pin_base+32,chip3_i2c_addr)   # pins 97-112
wiringpi.mcp23017Setup(pin_base+48,chip4_i2c_addr)   # pins 113-128

pin_max = 128

def shutdown():
	for pin in range(pin_base,pin_max):
		off(pin)

def on(pin):
        wiringpi.digitalWrite(pin, ON) # sets port GPA1 to 0V, which turns the relay ON.
        print "pin {} on".format(pin)
  
def off(pin):
        wiringpi.digitalWrite(pin, OFF) # sets port GPA1 to 5V, which turns the relay OFF.
        print  "pin {} off".format(pin)
 
def init(): 
	for pin in range(pin_base,pin_max):
		wiringpi.pinMode(pin,1) # set to output mode
		off(pin)

interval=5
try:
    init()
    while True:
        for pin in range(80,97):
		on(pin)
		trash = raw_input("hit enter when done with pin")
		off(pin)
except KeyboardInterrupt:
	shutdown()
finally:
	shutdown()
