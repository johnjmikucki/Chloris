import wiringpi2 as wiringpi
from time import sleep
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import warnings
import pytz

utc = pytz.UTC

ON = 0
OFF = 1

pin_base = 65  # lowest available starting number is 65
pin_max = pin_base + (4 * 16)  # max pin is min pin plus (16 pins per MCP23017 chip * 4 such chips)

#### BOARD-SPECIFIC CONSTANTS
RELAY_01 = UNUSED_1 = 81  # unused
RELAY_02 = UNUSED_2 = 82  # unused
RELAY_03 = UNUSED_3 = 83  # unused
RELAY_04 = UNUSED_4 = 84  # unused
RELAY_05 = UNUSED_5 = 85  # unused
RELAY_06 = UNUSED_6 = 86  # unused
RELAY_07 = LO_VOLT_1 = 87
RELAY_08 = LO_VOLT_2 = 88
RELAY_09 = OUTLET_2 = 90  # lower 1-gang, bottom outlet
RELAY_10 = OUTLET_1 = 89  # lower 1-gang, top outlet
RELAY_11 = OUTLET_8 = 96  # middle 1-gang, bottom outlet
RELAY_12 = OUTLET_7 = 95  # middle 1-gang, top outlet
RELAY_13 = OUTLET_6 = 94  # 2-gang, upper left
RELAY_14 = OUTLET_4 = 92  # 2-gang, bottom left
RELAY_15 = OUTLET_3 = 91  # 2-gang, upper right
RELAY_16 = OUTLET_5 = 93  # 2-gang, bottom right

DRIVER1 = OUTLET_4  # I/O pins controlling relays for main light outlets
SUPP_1 = OUTLET_3
SUPP_2 = OUTLET_7
MAIN_LIGHTS = [DRIVER1, LO_VOLT_1, LO_VOLT_2]
SUPP_LIGHTS = [SUPP_1, SUPP_2]  # I/O pins controlling relays for supplemental light outlets
MAIN_FAN = OUTLET_6  # I/O pin controlling relay for primary fan outlet
SUPP_FAN = OUTLET_5  # I/O pin controlling relay for supplemental fan outlet
MIST_PUMP = OUTLET_2  # I/O pin controlling relay for misting pump outlet

scheduler = BackgroundScheduler();

pin_state = {}
state_names = ["ON", "OFF"]
pin_names = {DRIVER1: "DRIVER1", SUPP_1: "SUPP_1", SUPP_2: "SUPP_2", LO_VOLT_1: "LO_VOLT_1",
             LO_VOLT_2: "LO_VOLT_2", MAIN_FAN: "MAIN_FAN", SUPP_FAN: "SUPP_FAN", MIST_PUMP: "MIST_PUMP"}
print(pin_names)


def print_pin(pin):
    state_val = pin_state.get(pin)
    if state_val == 0 or state_val == 1:
        state_string = state_names[pin_state.get(pin)]
    else:
        state_string = "Unknown"

    return "{0} (pin {1}): {2}".format(pin_names.get(pin), pin, state_string)


def shutdown():
    # turn off all pins.
    for pin in range(pin_base, pin_max):
        set_pin(pin, OFF)


def set_pin(pin, state):
    print(print_pin(pin) + " -> " + state_names[state])
    wiringpi.digitalWrite(pin, state)  # sets port GPA1 to 0V, which turns the relay ON.
    pin_state[pin] = state
    #   print("new " + print_pin(pin))


def set_pins(pin_array, state):
    for pin in pin_array:
        set_pin(pin, state)
        sleep(0.2)


def init_control_plane():
    chip1_i2c_addr = 0x21  # A0, A1, A2 pins all wired to GND
    chip2_i2c_addr = 0x22  # A0, A1, A2 pins all wired to GND
    chip3_i2c_addr = 0x23  # A0, A1, A2 pins all wired to GND
    chip4_i2c_addr = 0x24  # A0, A1, A2 pins all wired to GND

    wiringpi.wiringPiSetup()  # initialise wiringpi

    wiringpi.mcp23017Setup(pin_base, chip1_i2c_addr)  # pins 65-80
    wiringpi.mcp23017Setup(pin_base + 16, chip2_i2c_addr)  # pins 81-96
    wiringpi.mcp23017Setup(pin_base + 32, chip3_i2c_addr)  # pins 97-112
    wiringpi.mcp23017Setup(pin_base + 48, chip4_i2c_addr)  # pins 113-128

    for pin in range(pin_base, pin_max):
        wiringpi.pinMode(pin, 1)  # set to output mode
        set_pin(pin, OFF)


def set_main_lights(state):  set_pins(MAIN_LIGHTS, state)


def set_supp_lights(state):  set_pins(SUPP_LIGHTS, state)


def set_main_fan(state): set_pin(MAIN_FAN, state)


def set_supp_fan(state): set_pin(SUPP_FAN, state)


def set_mist(state): set_pin(MIST_PUMP, state)


def set_tier_fans():
    warnings.warn("No tier-fans relay defined.")


def mist(on):
    set_tier_fans(not on)  # turn fans off/on
    set_mist(on)  # then turn mist circuit on/off


def init_scheduler():
    # morning routine
    scheduler.add_job(set_main_fan, args=[ON], trigger='cron', name='ensure_main_fan', misfire_grace_time=60,
                      day_of_week='*', hour=0, minute=00, timezone=utc)
    # not really necessary but makes startup easy

    scheduler.add_job(set_main_lights, args=[ON], trigger='cron', name='main_lights_on_am', misfire_grace_time=60,
                      day_of_week='*', hour=12, minute=0, timezone=utc)
    scheduler.add_job(set_supp_lights, args=[ON], trigger='cron', name='supp_lights_on_am', misfire_grace_time=60,
                      day_of_week='*', hour=13, minute=20, timezone=utc)

    # midday routine
    scheduler.add_job(set_supp_lights, args=[OFF], trigger='cron', name='supp_lights_off_cooldown',
                      misfire_grace_time=60,
                      day_of_week='*', hour=18, minute=0, timezone=utc)
    scheduler.add_job(set_supp_lights, args=[ON], trigger='cron', name='supp_lights_on_cooldown', misfire_grace_time=60,
                      day_of_week='*', hour=18, minute=15, timezone=utc)

    # evening routine
    scheduler.add_job(set_supp_lights, args=[OFF], trigger='cron', name='supp_lights_off_pm', misfire_grace_time=60,
                      day_of_week='*', hour=00, minute=30, timezone=utc)
    scheduler.add_job(set_main_lights, args=[OFF], trigger='cron', name='main_lights_off_pm', misfire_grace_time=60,
                      day_of_week='*', hour=1, minute=0, timezone=utc)

    # misting routine
    scheduler.add_job(mist, args=[ON], trigger='cron', name='mist_on_first', day_of_week='*', misfire_grace_time=60,
                      hour=13, minute=00, timezone=utc)
    scheduler.add_job(mist, args=[OFF], trigger='cron', name='mist_off_first', day_of_week='*', misfire_grace_time=60,
                      hour=13, minute=3, timezone=utc)

    scheduler.add_job(mist, args=[ON], trigger='cron', name='mist_on_second', day_of_week='*', misfire_grace_time=60,
                      hour=14, minute=30, timezone=utc)
    scheduler.add_job(mist, args=[OFF], trigger='cron', name='mist_off_second', day_of_week='*', misfire_grace_time=60,
                      hour=14, minute=33, timezone=utc)

    scheduler.add_job(mist, args=[ON], trigger='cron', name='mist_on_third', day_of_week='*', misfire_grace_time=60,
                      hour=16, minute=00, timezone=utc)
    scheduler.add_job(mist, args=[OFF], trigger='cron', name='mist_off_third', day_of_week='*', misfire_grace_time=60,
                      hour=16, minute=3, timezone=utc)

    scheduler.start()


def setup_for_time(t):
    print("starting time: ", t)
    for j in scheduler.get_jobs():
        job_time = j.next_run_time.time()
        print("job " + j.name + " next run: " + job_time.isoformat())
        if (t.time() >= job_time):
            print("I should start job:", j.name)


def setup_for_current_time():
    setup_for_time(datetime.now(tz=utc))


interval = 5
try:
    init_control_plane()
    init_scheduler()
    setup_for_current_time()
    while True:
        print(datetime.now())
        sleep(600)
except KeyboardInterrupt:
    shutdown()
finally:
    shutdown()
