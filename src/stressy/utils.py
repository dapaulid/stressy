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
import collections
import glob
import os
import re
import signal
import sys

from time import perf_counter as timer
from importlib.metadata import metadata

#-------------------------------------------------------------------------------
# classes
#-------------------------------------------------------------------------------
#

#-------------------------------------------------------------------------------
#
# the most important metadata of the program
ProgInfo = collections.namedtuple('ProgInfo', 
    ['name', 'version', 'description', 'website', 'bugtracker']
)

#-------------------------------------------------------------------------------
#
class Failed(Exception):
    def __init__(self, message):
        super().__init__(message)
# end class

#-------------------------------------------------------------------------------
#
class Colors:
    # standard
    RED          = '\x1b[1;31m'
    GREEN        = '\x1b[1;32m'
    YELLOW       = "\x1b[1;33m"
    BLUE         = "\x1b[1;34m"
    PURPLE       = "\x1b[1;35m"
    CYAN         = "\x1b[1;36m"
    WHITE        = "\x1b[1;37m"
    # modifiers
    BOLD         = "\x1b[1m"
    FAINT        = "\x1b[2m"
    ITALIC       = "\x1b[3m"
    UNDERLINE    = "\x1b[4m"
    BLINK        = "\x1b[5m"
    NEGATIVE     = "\x1b[7m"
    CROSSED      = "\x1b[9m"
    # combinations
    LINK         = BLUE + UNDERLINE
    # misc
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
def use_colors():
	return sys.stdout.isatty()

#-------------------------------------------------------------------------------
#
def colorize(s, color):
	return color + s + Colors.RESET if use_colors() else s
# end function

#-------------------------------------------------------------------------------
#
def format_comments(s):
    return s.replace("#", Colors.ITALIC+"#").replace("\n", Colors.RESET+"\n") if use_colors() else s
# end function

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
UNITS_DURATION = [
	(1,                       ["s", "sec", "", "second", "seconds"]),
    (60,                      ["min", "minute", "minutes"]),
    (60 * 60,                 ["h", "hour", "hours"]),
    (60 * 60 * 24,            ["d", "day", "days"]),
    (60 * 60 * 24 * 7,        ["w", "week", "weeks"]),
    (60 * 60 * 24 * 30,       ["mt", "month", "months"]),
    (60 * 60 * 24 * 365,      ["a", "y", "year", "years"]),
]
UNITS_METRIC = [
	(1,                       [""]),
    (1000,                    ["k", "kilo", "thousand"]),
    (1000000,                 ["m", "mega", "million"]),
    (1000000000,              ["g", "giga", "b", "billion"]),
    (1000000000000,           ["t", "tera", "trillions"]),
]
UNITS_PATTERN = r'(\d+(?:\.\d+)?)\s*([a-z]*)'

#-------------------------------------------------------------------------------
#
def format_units(value, units, num_parts=-1):
    parts = []
    for factor, aliases in units[::-1]:
        num_units, value = divmod(value, factor)
        if num_units > 0 or factor == 1:
            parts.append("%d%s" % (num_units, aliases[0]))
    return " ".join(parts[:num_parts])
# end function

#-------------------------------------------------------------------------------
#
def parse_units(s, units):
	if s is None:
		return None
	matches = re.findall(UNITS_PATTERN, s.lower())
	if not matches:
		raise ValueError("invalid expression: %s" % s)
	value = 0
	for number, unit in matches:
		matched_unit = None
		for factor, aliases in units:
			if unit in aliases:
				matched_unit = aliases[0]
				break
		if matched_unit is not None:
			value += float(number) * factor
		else:
			raise ValueError("invalid unit: %s" % unit)
        # end if
	# end for

	return value
# end function

#-------------------------------------------------------------------------------
#
def format_duration(seconds, num_parts=2):
    if seconds < 60:
        return "%0.3fs" % seconds
    return format_units(seconds, UNITS_DURATION, num_parts)
# end function

#-------------------------------------------------------------------------------
#
def parse_duration(s):
    return parse_units(s, UNITS_DURATION)
# end function

#-------------------------------------------------------------------------------
#
def format_count(count):
    return format_units(count, UNITS_METRIC, 1)
# end function

#-------------------------------------------------------------------------------
#
def parse_count(s):
    return int(parse_units(s, UNITS_METRIC))
# end function

#-------------------------------------------------------------------------------
#
def format_datetime(dt):
    return dt.strftime("%a %d %b %Y, %H:%M:%S")
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
def load_toml(filename):

    # TODO: the following code is GPT 3.5 generated, and doesn't
    # parse multi-line stuff correctly. it still seems to be good enough
    # for our current purposes

    with open(filename, 'r') as file:
        # Initialize an empty dictionary to store the parsed data
        data = {}
        current_section = None

        # Loop through each line in the file
        for line in file:
            # Remove leading/trailing whitespace and newline characters
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # Skip empty lines and comments

            # Check if the line denotes a section header
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1]
                data[current_section] = {}
            elif current_section:
                # Split the line on the first '=' character
                parts = line.split('=', 1)
                if len(parts) == 2:  # Ensure there's a key-value pair
                    key, value = parts
                    # Remove leading/trailing whitespace from key and value
                    key = key.strip().strip('"')
                    value = value.strip()
                    # Handle lists
                    if value.startswith('[') and value.endswith(']'):
                        # Parse the list items
                        value = [item.strip().strip('"') for item in value[1:-1].split(',')]
                    # Handle dictionaries
                    elif value.startswith('{') and value.endswith('}'):
                        # Parse the dictionary items
                        # Remove curly braces
                        value_text = value[1:-1]
                        # Split by comma and then by equals sign to get key-value pairs
                        items = value_text.split(',')
                        value = {}
                        for item in items:
                            key_value = item.split('=')
                            if len(key_value) == 2:
                                # Strip whitespace and quotes from key and value
                                key = key_value[0].strip().strip('"')
                                sub_value = key_value[1].strip().strip('"')
                                value[key] = sub_value
                    # Remove surrounding quotes from the value if present
                    elif value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    # Store the key-value pair in the appropriate section
                    data[current_section][key] = value

        return data
    # end with
# end function

#-------------------------------------------------------------------------------
#
def find_file_in_parents(filename, start_dir=None):
    # NOTE: GPT 3.5 generated

    # If start_dir is not provided, use the directory of the calling script
    if start_dir is None:
        start_dir = os.path.dirname(os.path.realpath(__file__))

    # Traverse upwards the directory tree until finding the file or reaching the root directory
    current_dir = start_dir
    while True:
        file_path = os.path.join(current_dir, filename)
        if os.path.isfile(file_path):
            return file_path
        
        # Move up one directory
        parent_dir = os.path.dirname(current_dir)
        # Break if current directory is the root directory
        if parent_dir == current_dir:
            break
        current_dir = parent_dir
    
    # Just return filename if the file is not found (best effort for error messages)
    return filename
# end function

#-------------------------------------------------------------------------------
# initialization
#-------------------------------------------------------------------------------
#
# load program info
prog = None
try:
    toml = load_toml(find_file_in_parents("pyproject.toml"))
    prog = ProgInfo(
        name         = toml['project']['name'],
        version      = toml['project']['version'],
        description  = toml['project']['description'],
        website      = toml['project.urls']['Homepage'],
        bugtracker   = toml['project.urls']['Bug Tracker'],
    )
except FileNotFoundError:
    # probably installed
    m = metadata("stressy")
    prog = ProgInfo(
        name         = m['Name'],
        version      = m['Version'],
        description  = m['Summary'],
        website      = m['Project-URL'].split(' ')[-1],
        bugtracker   = '(unknown)',
    )
# end try    

# workaround to enable ansi colors in windows
# https://stackoverflow.com/questions/12492810/python-how-can-i-make-the-ansi-escape-codes-to-work-also-in-windows
if os.name == 'nt' and use_colors():
	os.system("")
# end if

#-------------------------------------------------------------------------------
# end of file