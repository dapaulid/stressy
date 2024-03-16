#-------------------------------------------------------------------------------
#
#	Measures execution time of Python functions using decorators.
#
#	@license
#	Copyright (c) Daniel Pauli <dapaulid@gmail.com>
#
#	This source code is licensed under the MIT license found in the
#	LICENSE file in the root directory of this source tree.
#
#-------------------------------------------------------------------------------

#-------------------------------------------------------------------------------
# imports 
#-------------------------------------------------------------------------------
#
import glob
import os
import re
import signal
import sys

from time import perf_counter as timer

#-------------------------------------------------------------------------------
# classes
#-------------------------------------------------------------------------------
#
class Failed(Exception):
    def __init__(self, message):
        super().__init__(message)
# end class

#-------------------------------------------------------------------------------
#
class Colors:
    RED          = '\x1b[1;31m'
    GREEN        = '\x1b[1;32m'
    YELLOW       = "\x1b[1;33m"
    BLUE         = "\x1b[1;34m"
    PURPLE       = "\x1b[1;35m"
    CYAN         = "\x1b[1;36m"
    WHITE        = "\x1b[1;37m"
    RESET        = '\x1b[0m'
# end class

#-------------------------------------------------------------------------------
#
class OsPaths:
	if os.name == 'nt':
		APPDATA = os.getenv('APPDATA')
	else:
		APPDATA = os.path.expanduser('~/.local/share')
	# end if
# end class


#-------------------------------------------------------------------------------
# constants
#-------------------------------------------------------------------------------
#   
HLINE = '-' * 80


#-------------------------------------------------------------------------------
# functions
#-------------------------------------------------------------------------------
#

#-------------------------------------------------------------------------------
#
def colorize(str, color):
    return color + str + Colors.RESET

#-------------------------------------------------------------------------------
#       
def kill(proc):
    # does not seem to work on windows when using shell=True
    #proc.terminate()
    #proc.kill()
    try:
        # TODO this works on windows, but seem to kill all child processes
        os.kill(proc.pid, signal.CTRL_C_EVENT)
        proc.wait()
    except KeyboardInterrupt:
        pass
    # end try
# end function  

#-------------------------------------------------------------------------------
#       
def remove_files(pattern):
    for file in glob.glob(pattern):
        os.remove(file)
# end function

#-------------------------------------------------------------------------------
#
DURATION_UNITS = [
	(1,                       ["s", "sec", "", "second", "seconds"]),
    (60,                      ["min", "minute", "minutes"]),
    (60 * 60,                 ["h", "hour", "hours"]),
    (60 * 60 * 24,            ["d", "day", "days"]),
    (60 * 60 * 24 * 7,        ["w", "week", "weeks"]),
    (60 * 60 * 24 * 30,       ["mt", "month", "months"]),
    (60 * 60 * 24 * 365,      ["a", "y", "year", "years"]),
]
DURATION_PATTERN = r'(\d+(?:\.\d+)?)\s*([a-z]*)'

#-------------------------------------------------------------------------------
#
def format_duration(seconds, num_parts=2):
    if seconds < 60:
        return "%0.3fs" % seconds
    parts = []
    for duration, aliases in DURATION_UNITS[::-1]:
        num_units, seconds = divmod(seconds, duration)
        if num_units > 0:
            parts.append("%d%s" % (num_units, aliases[0]))
    return " ".join(parts[:num_parts])
# end function

#-------------------------------------------------------------------------------
#
def parse_duration(s):
	if s is None:
		return None

	matches = re.findall(DURATION_PATTERN, s.lower())
	if not matches:
		raise ValueError("invalid duration: %s" % s)

	seconds = 0
	for number, unit in matches:
		matched_unit = None
		for duration, aliases in DURATION_UNITS:
			if unit in aliases:
				matched_unit = aliases[0]
				break
		if matched_unit is not None:
			seconds += float(number) * duration
		else:
			raise ValueError("invalid unit: %s" % unit)

	return seconds
# end function

#-------------------------------------------------------------------------------
#
def format_datetime(dt):
    return dt.strftime("%a %d %b %Y, %H:%M:%S")
# end function    

#-------------------------------------------------------------------------------
#
def format_count(count):
    units = [
        ("T", 1000000000000), # trillions
        ("B", 1000000000),    # billions
        ("M", 1000000),       # million
        ("K", 1000)           # thousands
    ]
    for unit, q in units:
        if count >= q:
            return "%d%s" % (count // q, unit)
    return "%d " % count
# end function    

#-------------------------------------------------------------------------------
#
def error(msg):
    print("error: %s" % msg, file=sys.stderr)
# end function

#-------------------------------------------------------------------------------
#
print_over_length = 0
def print_over(msg):
    global print_over_length
    msg = '  ' + msg # leave room for cursor
    if print_over_length > len(msg):
        padding = ' ' * (print_over_length - len(msg)) 
    else:
        padding = ''
    print(msg + padding, end='\r', flush=True)
    print_over_length = len(msg)

def print_complete(clear=False):
    global print_over_length
    if print_over_length > 0:
        if clear:
            print(' ' * print_over_length)
        else:
            print()
    print_over_length = 0

#-------------------------------------------------------------------------------
#
def attrs(obj):
	return [getattr(obj, x) for x in dir(obj) if not x.startswith('__')]