import wiringpi2 as wiringpi
from time import sleep
from threading import Lock
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import logging
import signal
from logging.handlers import RotatingFileHandler
from logging.handlers import SysLogHandler
from lockfile import LockFile
from lockfile import LockTimeout

utc = pytz.UTC
DEBUG = False

# updated to handle Darlington arrays reversing circuit
ON = 1
OFF = 0
state_updated = False

pin_base = 65  # lowest available starting number is 65
pin_max = pin_base + (1 * 16)  # max pin is min pin plus (16 pins per MCP23017 chip * 2 such chips)
INTER_PIN_DELAY=0.2

PIN_MODES = {0: "INPUT", 1: "OUTPUT", 2: "ALT5", 3: "ALT4", 4: "ALT0", 5: "ALT1", 6: "ALT2", 7: "ALT3"}


#### BOARD-SPECIFIC CONSTANTS
RELAY_01 = UNUSED_1 = 81  # unused
RELAY_02 = UNUSED_2 = 82  # unused
RELAY_03 = UNUSED_3 = 83  # unused
RELAY_04 = UNUSED_4 = 84  # unused
RELAY_05 = UNUSED_5 = 85  # unused
RELAY_06 = UNUSED_6 = 86  # unused
RELAY_07 = LO_VOLT_1 = 87
RELAY_08 = LO_VOLT_2 = 88
RELAY_09 = OUTLET_1 = MIST_PUMP = 66  # lower 1-gang, bottom outlet
RELAY_10 = OUTLET_2 = TIER_FANS = 65  # lower 1-gang, top outlet

RELAY_11 = OUTLET_3 = SUPP_LIGHT_1 = 72  # middle 1-gang, bottom outlet
RELAY_12 = OUTLET_4 = SUPP_LIGHT_2 = 71  # middle 1-gang, top outlet

RELAY_13 = OUTLET_7 = MAIN_EXHAUST = 70  # 2-gang, upper left
RELAY_14 = OUTLET_5 = DRIVER1 = 68  # 2-gang, bottom left, main light outlets
RELAY_15 = OUTLET_8 = 67  # 2-gang, upper right
RELAY_16 = OUTLET_6 = SUPP_EXHAUST = 69  # 2-gang, bottom right

MAIN_LIGHTS = [DRIVER1, LO_VOLT_1, LO_VOLT_2]
SUPP_LIGHTS = [SUPP_LIGHT_1, SUPP_LIGHT_2]  # I/O pins controlling relays for supplemental light outlets

scheduler = BackgroundScheduler()

PIN_MODE_SAFE = 0
PIN_MODE_ACTIVE = 1

pin_state = {}
# pin_state.setdefault("default", OFF)
state_names = ["OFF", "ON"]
pin_names = {}
pin_names.setdefault("default", 'Unused')

# now, configure friendly names for the pins we actually use to drive the board
pin_names[UNUSED_1] = "UNUSED_1"
pin_names[UNUSED_2] = "UNUSED_2"
pin_names[UNUSED_3] = "UNUSED_3"
pin_names[UNUSED_4] = "UNUSED_4"
pin_names[UNUSED_5] = "UNUSED_5"
pin_names[UNUSED_6] = "UNUSED_6"
pin_names[LO_VOLT_1] = "LO_VOLT_1"
pin_names[LO_VOLT_2] = "LO_VOLT_2"

pin_names[MAIN_EXHAUST] = "MAIN_EXHAUST"
pin_names[SUPP_EXHAUST] = "SUPP_EXHAUST"

pin_names[OUTLET_6] = "OUTLET_6"
pin_names[DRIVER1] = "DRIVER1"

pin_names[SUPP_LIGHT_2] = "SUPP_LIGHT_2"
pin_names[SUPP_LIGHT_1] = "SUPP_LIGHT_1"

pin_names[TIER_FANS] = "TIER_FANS"
pin_names[MIST_PUMP] = "MIST_PUMP"

"""
Physical Schematic:
TOP OF BOARD

---------
| 7 | 8 |       7 = OUTLET_7, MAIN_EXHAUST      8 = OUTLET_8, SUPP_EXHAUST
| 5 | 6 |       5 = OUTLET_5, DRIVER_1          6 = OUTLET_6,
---------

-----
| 4 |           4 = OUTLET_4, SUPP_LIGHT_2
| 3 |           3 = OUTLET_3, SUPP_LIGHT_1
-----

-----
| 2 |           2 = OUTLET_2, TIER_FANS
| 1 |           1 = OUTLET_1, MIST_PUMP
-----

--------------

RELAY BLOCK AND
DISTRIBUTION

------------------

LOGIC BOARD & CPU

------------------
MAIN POWER

------------------


"""


def print_pin(pin):
    state_val = pin_state.get(pin)
    if state_val == 0 or state_val == 1:
        state_string = state_names[pin_state.get(pin)]
    else:
        state_string = "Unknown"

    return "{0} (pin {1}): {2}".format(pin_names.get(pin), pin, state_string)


def shutdown_board():
    if scheduler.running:
        scheduler.shutdown()
    # turn off all pins.
    for pin in range(pin_base, pin_max):
        set_pin(pin, OFF)

    state_updated = True

    apply_model(True)

    # set to input mode
    # this is a safety feature - if left in output mode, pins could be high, low,
    # etc - relays could be active or not.  input mode prevents them from driving the relays.
    for pin in range(pin_base, pin_max):
        wiringpi.pinMode(pin, PIN_MODE_SAFE)


def set_pin(pin, state):
    global state_updated
    s = None
    try:
        s = pin_state[pin]
    except KeyError:
        logger.debug("pin {0} had no state.  Initializing?".format(pin))

    if wiringpi.getAlt(pin) != PIN_MODE_ACTIVE:
        logger.warn(
            'Attempting to set output value on NON-ACTIVE pin {0} (mode: {1}).  Forcing to OUTPUT and setting...'.format(
                pin,
                PIN_MODES.get(wiringpi.getAlt(pin))))
        wiringpi.pinMode(pin, PIN_MODE_ACTIVE)

    pin_state[pin] = state
    if s == state:
        state_updated = False
    else:
        state_updated = True

    name = pin_names.get(pin)
    if name is not None:
        n = name
    else:
        n = "Pin_{0}".format(pin)
    logger.info("{0} -> {1}".format(n, state_names[pin_state.get(pin)]))


def apply_model(verbose):
    global state_updated
    logstring = 'applied state '
    for pin in sorted(pin_state.keys()):
        current_state = pin_state.get(pin)
        pin_name = pin_names.get(pin)
        state_name = state_names[current_state]
        if pin != "default":
            if state_name == state_names[ON]:
                logstring = logstring + "{0}:{1} ".format(pin_name, state_name)
            wiringpi.digitalWrite(pin, current_state)
            sleep(INTER_PIN_DELAY)
    if verbose or state_updated:
        logger.info(logstring)
    state_updated = False


def set_pins(pin_array, state):
    for pin in pin_array:
        set_pin(pin, state)


def init_control_plane():
    logger.info("Initializing control plane")
    chip1_i2c_addr = 0x20  # Controlled by A0, A1, A2 pins GND or +5V
#    chip2_i2c_addr = 0x22  # Controlled by A0, A1, A2 pins GND or +5V
#    chip3_i2c_addr = 0x23  # Controlled by A0, A1, A2 pins GND or +5V
#    chip4_i2c_addr = 0x24  # Controlled by A0, A1, A2 pins GND or +5V

    wiringpi.wiringPiSetup()  # initialise wiringpi

    wiringpi.mcp23017Setup(pin_base, chip1_i2c_addr)  # pins 65-80
#    wiringpi.mcp23017Setup(pin_base + 16, chip2_i2c_addr)  # pins 81-96
#    wiringpi.mcp23017Setup(pin_base + 32, chip3_i2c_addr)  # pins 97-112
#    wiringpi.mcp23017Setup(pin_base + 48, chip4_i2c_addr)  # pins 113-128

    for pin in range(pin_base, pin_max):
        set_pin(pin, OFF)
        wiringpi.pinMode(pin, PIN_MODE_ACTIVE)  # set to output mode

    sleep(1)

    for pin in range(pin_base, pin_max):
        mode = wiringpi.getAlt(pin)
        if mode != PIN_MODE_ACTIVE:
            logger.error("Initialized pin {0} to mode {1} but found it in mode {2}".format(pin, PIN_MODE_ACTIVE, mode))

    # and then apply our CHANGES
    apply_model(False)
    logger.info("Control plane initialized successfully")


def set_main_lights(state): set_pins(MAIN_LIGHTS, state)

def set_supp_lights(state): set_pins(SUPP_LIGHTS, state)

def set_main_fan(state): set_pin(MAIN_EXHAUST, state)

def set_supp_fan(state): set_pin(SUPP_EXHAUST, state)

def set_mist(state): set_pin(MIST_PUMP, state)

def set_tier_fans(state): set_pin(TIER_FANS, state)

def mist(on):
    set_tier_fans(not on)  # turn fans off/on
    set_mist(on)  # then turn mist circuit on/off


def init_scheduler():
    logger.info("Initializing schedule jobs")
    # morning routine
    scheduler.add_job(set_main_fan, args=[ON], trigger='cron', name='ensure_main_fan', misfire_grace_time=86399,
                      day_of_week='*', hour=0, minute=00, timezone=utc)
    scheduler.add_job(set_tier_fans, args=[ON], trigger='cron', name='ensure_tier_fan', misfire_grace_time=86399,
                      day_of_week='*', hour=0, minute=00, timezone=utc)
    # not really necessary but makes startup easy

    scheduler.add_job(set_main_lights, args=[ON], trigger='cron', name='main_lights_on_am', misfire_grace_time=86399,
                      day_of_week='*', hour=12, minute=0, timezone=utc)
    scheduler.add_job(set_supp_lights, args=[ON], trigger='cron', name='supp_lights_on_am', misfire_grace_time=86399,
                      day_of_week='*', hour=13, minute=20, timezone=utc)

    # midday routine
    scheduler.add_job(set_supp_lights, args=[OFF], trigger='cron', name='supp_lights_off_cooldown',
                      misfire_grace_time=86399, day_of_week='*', hour=18, minute=0, timezone=utc)
    scheduler.add_job(set_supp_lights, args=[ON], trigger='cron', name='supp_lights_on_cooldown',
                      misfire_grace_time=86399, day_of_week='*', hour=18, minute=15, timezone=utc)

    # evening routine
    scheduler.add_job(set_supp_lights, args=[OFF], trigger='cron', name='supp_lights_off_pm', misfire_grace_time=86399,
                      day_of_week='*', hour=00, minute=30, timezone=utc)
    scheduler.add_job(set_main_lights, args=[OFF], trigger='cron', name='main_lights_off_pm', misfire_grace_time=86399,
                      day_of_week='*', hour=1, minute=0, timezone=utc)

    # misting routine
    scheduler.add_job(mist, args=[ON], trigger='cron', name='mist_on_first', day_of_week='*', misfire_grace_time=86399,
                      hour=13, minute=00, timezone=utc)
    scheduler.add_job(mist, args=[OFF], trigger='cron', name='mist_off_first', day_of_week='*',
                      misfire_grace_time=86399, hour=13, minute=3, timezone=utc)

    scheduler.add_job(mist, args=[ON], trigger='cron', name='mist_on_second', day_of_week='*', misfire_grace_time=86399,
                      hour=14, minute=30, timezone=utc)
    scheduler.add_job(mist, args=[OFF], trigger='cron', name='mist_off_second', day_of_week='*',
                      misfire_grace_time=86399, hour=14, minute=33, timezone=utc)

    scheduler.add_job(mist, args=[ON], trigger='cron', name='mist_on_third', day_of_week='*', misfire_grace_time=86399,
                      hour=16, minute=00, timezone=utc)
    scheduler.add_job(mist, args=[OFF], trigger='cron', name='mist_off_third', day_of_week='*',
                      misfire_grace_time=86399, hour=16, minute=3, timezone=utc)

    scheduler.start()
    logger.info("Daily Schedule loaded")


def setup_for_time(t):
    logger.info("setup for time: {0}".format(t))
    scheduler.print_jobs()
    for job in scheduler.get_jobs():
        if job.next_run_time.time() <= t.time():
            logger.info("triggering {0}".format(job))
            job.func(job.args[0])


def setup_for_current_time(): setup_for_time(datetime.now(tz=utc))


def receive_signal(signum, stack):
    print('Signal Received: {0} shutting down'.format(signum))
    logger.info('Signal Received: {0} shutting down'.format(signum))
    shutdown()


def shutdown():
    logger.info("Shutting down...")
    l = Lock()
    try:
        l.acquire()
        logger.info("Shutdown isolation lock acquired.  Shutting down...")
        shutdown_board()
        lock.release()
        logger.info("released ", lock.path)

        logger.info("Chloris daemon terminating.")
        logging.shutdown()
        exit()
    except:
        logger.info("Unable to acquire shutdown isolation lock; shutdown alreadu in progress.")


def log_state(boo):
    logstring = ""
    for pin in sorted(pin_state.keys()):
        current_state = pin_state.get(pin)
        pin_name = pin_names.get(pin)
        state_name = state_names[current_state]
        if pin != "default":
            logstring = logstring + "{0}:{1} ".format(pin_name, state_name)
    logger.info(logstring)

interval = 5

lock = LockFile("/var/run/chloris.pid")
if not lock.i_am_locking():
    try:
        lock.acquire(timeout=5)    # wait up to 5 seconds
    except LockTimeout:
        print("unable to acquire ", lock.path, " within 5 seconds.  Aborting...")
        exit(-1)

LOG_FILENAME = '/var/log/chloris/daemon'
logger = logging.getLogger('chloris')
logger.setLevel(logging.INFO)

logger.info(lock.path, ' lock acquired.')

rfh = RotatingFileHandler(LOG_FILENAME, maxBytes=1000000, backupCount=20)
rfh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger.addHandler(rfh)

slh = SysLogHandler('/dev/log')
slh.setFormatter(logging.Formatter('chloris: %(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logger.addHandler(slh)

signal.signal(signal.SIGQUIT, receive_signal)
signal.signal(signal.SIGINT, receive_signal)
signal.signal(signal.SIGTERM, receive_signal)


try:
    logger.info("Chloris daemon initializing")
    init_control_plane()
    init_scheduler()
    setup_for_current_time()
    scheduler.add_job(apply_model, args=[True], name='startup_instant_grat')  # do it do it now
    logger.info("Setup complete")

    # enforce relays are in modeled state every minute
    scheduler.add_job(apply_model, args=[False], trigger='cron', name='apply_model',
                      minute='*', timezone=utc, misfire_grace_time=5)

    scheduler.add_job(log_state, args=[True], trigger='cron', name='log_state_hourly',
                      hour='*', timezone=utc, misfire_grace_time=5)

    while True:
        sleep(600)
except KeyboardInterrupt:
    logger.info("Caught KeyboardInterrupt.  Shutting down...")
    shutdown()
finally:
    shutdown()







"""



# To kick off the script, run the following from the python directory:
#   PYTHONPATH=`pwd` python testdaemon.py start

#third party libs
from daemon import runner

class App():

    def __init__(self):
        self.stdin_path = '/dev/null'
        self.stdout_path = '/dev/tty'
        self.stderr_path = '/dev/tty'
        self.pidfile_path =  '/var/run/chloris/daemon.pid'
        self.pidfile_timeout = 5

    def run(self):



app = App()
#logger = logging.getLogger("DaemonLog")
#logger.setLevel(logging.INFO)
#formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
#handler = logging.FileHandler("/var/log/testdaemon/testdaemon.log")
#handler.setFormatter(formatter)
#logger.addHandler(handler)

daemon_runner = runner.DaemonRunner(app)
#This ensures that the logger file handle does not get closed during daemonization
daemon_runner.daemon_context.files_preserve=[handler.stream]
daemon_runner.do_action()
"""