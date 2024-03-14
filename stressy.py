#!/usr/bin/env python3
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
import argparse
import collections
import enum
import glob
import os
import shutil
import signal
import subprocess
import sys
import time

from datetime import datetime
from time import perf_counter as timer


#-------------------------------------------------------------------------------
# types
#-------------------------------------------------------------------------------
#
class TestResult:
    status       = None       # the TestStatus code
    passed_runs  = 0          # the number of successfully completed runs
    failed_runs  = 0          # the number of failed runs
    started_on   = None       # the datetime of test start 
    duration     = None       # the total test duration
# end class

#-------------------------------------------------------------------------------
# constants
#-------------------------------------------------------------------------------
#
# enum used to specify test result. also used as exit code
class TestStatus(enum.IntEnum):
    PASSED       = 0          # the command executed successfully
    FAILED       = 1          # the command failed (non-zero exit code)
    CANCELLED    = 2          # the command was cancelled by user
    ERROR        = 3          # an error occurred during script execution
# end class

# Ansi colors
class Colors:
    RED          = '\x1b[1;31m'
    GREEN        = '\x1b[1;32m'
    YELLOW       = "\x1b[1;33m"
    BLUE         = "\x1b[1;34m"
    PURPLE       = "\x1b[1;35m"
    CYAN         = "\x1b[1;36m"
    WHITE        = "\x1b[1;37m"
    RESET        = '\x1b[0m'
# end enum

# colors associated with the TestStatus
StatusColors = [
    Colors.GREEN,
    Colors.RED,
    Colors.YELLOW,
    Colors.RED
]

# supported output modes
class OutputMode:
    ALL          = 'all'      # print all subprocess output
    FAIL         = 'fail'     # print subprocess output on failure only
    FILE         = 'file'     # redirect subprocess output to log files
    NONE         = 'none'     # do not print any subprocess output
# end enum

# log file name formats
class LogName:
    TEMP         = ".stress_p%d.log"
    PASSED       = "stress_p%d_good.log"
    FAILED       = "stress_p%d_bad.log"
    CLEAN        = "stress_*.log"
    CLEAN_TEMP   = ".stress_*.log"  
# end enum

# OS specific paths
if os.name == 'nt':
    # Windows
    DIR_APPDATA = os.getenv('APPDATA')
else:
    # Linux
    DIR_APPDATA = os.path.expanduser('~/.local/share')
# end if

# path to file for storing test results
RESULTS_FILE = os.path.join(DIR_APPDATA, "stressy.tsv")


#-------------------------------------------------------------------------------
# main
#-------------------------------------------------------------------------------
#
def main():

    # parse command line
    parser = argparse.ArgumentParser(description='repeatedly run a command until failure')
    parser.add_argument('command', type=str, nargs='*', 
        help="the shell command to be executed")
    parser.add_argument('-n', '--runs', type=int, default=None, 
        help="number of repetitions. Repeat until failure if not specified")
    parser.add_argument('-p', '--processes', type=int, default=1, 
        help="number of processes to run the command in parallel")
    parser.add_argument('-t', '--timeout', type=float, default=None, 
        help="timeout in seconds for command to complete")
    parser.add_argument('-s', '--sleep', type=float, default=None,
        help="duration in seconds to wait before next run")
    parser.add_argument('-o', '--output', choices=attrs(OutputMode), default=OutputMode.ALL,
        help="destination for command output (stdout/stderr)")
    parser.add_argument('-c', '--continue', action='store_true', dest='cont',
        help="continue after first failure")
    parser.add_argument('-r', '--results', action='store_true',
        help="print previous results for the given command")
    parser.add_argument('--clear-results', action='store_true',
        help="clear previous results for the given command")        
    args = parser.parse_args()

    # convert command from list to string
    args.command = subprocess.list2cmdline(args.command)

    # handle result related options
    if args.results:
        print_results(args)
        return TestStatus.PASSED
    elif args.clear_results:
        clear_results(args)
        return TestStatus.PASSED
    # end if

    # exit with help if no command specified
    if not args.command:
        parser.print_help()
        return TestStatus.ERROR
    # end if

    # do it
    result = stress_test(args)

    # format test summary
    if result.status == TestStatus.PASSED:
        if result.failed_runs == 0:
            summary = "successfully completed all %d runs" % result.passed_runs
        else:
            summary = "completed with %d failed and %d successful runs" % (result.failed_runs, result.passed_runs)
        # end if
    elif result.status == TestStatus.FAILED:
        if result.failed_runs == 1:
            summary = "FAILED after %d successful runs" % result.passed_runs
        else:
            summary = "FAILED with %d failed and %d successful runs" % (result.failed_runs, result.passed_runs)
        # end if
    elif result.status == TestStatus.CANCELLED:
        summary = "cancelled by user after %d failed and %d successful runs" % (result.failed_runs, result.passed_runs)
    else:
        raise Failed("unknown test result: %s" % result.status)
    # end if

    # append process count
    if args.processes > 1:
        summary += " on %d processes" % args.processes
    # append execution time
    summary += ", took %s" % format_duration(result.duration)
    
    # print it
    print(colorize(summary, StatusColors[result.status]))

    append_result(args, result)

    return result.status
# end function


#-------------------------------------------------------------------------------
# functions
#-------------------------------------------------------------------------------
#
def run(args):

    # init output redirection for subprocesses
    if args.output == OutputMode.FAIL:
        stdout = [ subprocess.PIPE for i in range(args.processes) ]
    elif args.output == OutputMode.ALL:
        stdout = [ None for i in range(args.processes) ]
    elif args.output == OutputMode.FILE:
        stdout = [ open(LogName.TEMP % i, 'w') for i in range(args.processes) ]
    elif args.output == OutputMode.NONE:
        stdout = [ subprocess.DEVNULL for i in range(args.processes) ]
    else:
        raise Failed("unknown output mode: %s" % args.output)
    # end if

    # helper to output process specific traces
    def print_proc(i, msg, verbose=False):
        msg = "[process %d] %s" % (i, msg)
        if args.output == OutputMode.FILE:
            print(msg, flush=True, file=stdout[i])
        elif args.output != OutputMode.NONE and not verbose:
            print_complete()            
            print(msg)
        # end if
    # end function

    try:
        # output command info
        for i in range(args.processes):
            print_proc(i, args.command, verbose=True)


        # start new processes for command
        procs = [ 
            subprocess.Popen(args.command, shell=True, text=True,
                stdout=stdout[i], stderr=subprocess.STDOUT if stdout[i] is not None else None) 
            for i in range(args.processes)
        ]

        # wait for processes to complete
        success = True  
        remaining_timeout = args.timeout
        for i, proc in enumerate(procs):
            
            start_time = timer()        
            try:
                returncode = proc.wait(remaining_timeout)
                # process completed
                proc_success = returncode == 0              
                proc_msg = "exited with code %d on %s" % (returncode, datetime.now())

            except subprocess.TimeoutExpired:
                # process exceeded time limit
                kill(proc)              
                proc_success = False
                proc_msg = "killed due to timeout of %0.3f seconds" % args.timeout              
            # end try

            # output process output on failure
            if args.output == OutputMode.FAIL and not proc_success:
                print_complete()
                print(proc.stdout.read().rstrip())
            # output process termination info
            print_proc(i, proc_msg, verbose=proc_success)

            if args.output == OutputMode.FILE:
                # handle log file
                stdout[i].close()
                # only keep most recent logfile of good and bad runs
                shutil.move(LogName.TEMP % i, (LogName.PASSED if proc_success else LogName.FAILED) % i)
            # end if
                
            # determine remaining time
            if remaining_timeout is not None:
                elapsed = timer() - start_time          
                remaining_timeout = max(remaining_timeout - elapsed, 0)
            # end if

            # run failed if at least one process failed
            success = success and proc_success
        # end for
            
        return success
    
    finally:
        # cleanup
        if args.output == OutputMode.FILE:
            # make sure to close and remove any temporary log files
            for i in range(args.processes):
                stdout[i].close()
            remove_files(LogName.CLEAN_TEMP)                
        # end if
    # end try
                
# end function

#-------------------------------------------------------------------------------
#
def stress_test(args):

    if args.output == OutputMode.FILE:
        # remove old log files first
        remove_files(LogName.CLEAN)
    # end if

    # start measuring execution time
    start_time = timer()

    runs = 0
    result = TestResult()
    result.started_on =  datetime.now()
    while args.runs is None or runs < args.runs:

        runs += 1
        result.duration = timer() - start_time          

        # output info
        info = "run #%d" % runs
        if args.runs is not None:
            info += " of %d" % args.runs
        info += ", %d failures since %s" % (result.failed_runs, format_duration(result.duration))
        if args.output == OutputMode.ALL:
            print(HLINE)
            print("| " + colorize(info.ljust(len(HLINE)-4), Colors.WHITE) + " |")
            print(HLINE)
        else:
            print_over("[ %s ]" % colorize(info, Colors.WHITE))
        # end if    
            
        # run command
        try:
            if run(args):
                # success
                result.passed_runs += 1             
            else: 
                # failed
                result.failed_runs += 1
                # stop unless the 'continue' flag is specified
                if not args.cont:
                    break
            # end if
           
            handle_sleep(args.sleep)

        except KeyboardInterrupt:
            result.status = TestStatus.CANCELLED
            break
        # end try

    # end while

    # determine total elapsed time
    result.duration = timer() - start_time  

    # determine result
    if result.status != TestStatus.CANCELLED:
        if result.failed_runs == 0:
            result.status = TestStatus.PASSED 
        else:
            result.status = TestStatus.FAILED
        # end if
    # end if

    # finish possible print_over
    if args.output == OutputMode.ALL or (args.output == OutputMode.FAIL and result.status == TestStatus.FAILED):
        print()
    else:
        print_complete(clear=True)
    # end if

    # done
    return result
# end function

#-------------------------------------------------------------------------------
#
def handle_sleep(seconds):
    if not seconds:
        return
    while seconds > 0:
        info = "sleeping for %s" % format_duration(seconds)
        print_over("[ %s ]" % colorize(info, Colors.WHITE))
        time.sleep(1)
        seconds = max(seconds - 1, 0)
    # end if
    print_over("")
# end function

#-------------------------------------------------------------------------------
#
def append_result(args, result):
    # format result
    entry = [
        args.command,
        result.started_on.isoformat(), 
        format_duration(result.duration),
        str(args.processes),
        str(result.passed_runs), 
        str(result.failed_runs), 
        result.status.name
    ]
    # write to file
    with open(RESULTS_FILE, 'a') as out:
        out.write('\t'.join(entry) + '\n')

# end function

#-------------------------------------------------------------------------------
#
def print_results(args):
    # read results from file
    try:
        groups = collections.defaultdict(list)
        with open(RESULTS_FILE, 'r') as inp:
            for line in inp:
                if line.startswith(args.command):
                    row = line.strip().split('\t')
                    groups[row[0]].append(row[1:])
                # end if
            # end for
        # end with
    except FileNotFoundError:
        pass
    # end try
    if len(groups) == 0:
        print("no results available for this command")
        return
    # end if

    # format results as table
    ROW = "{0:<25} {1:>12} {2:>6} {3:>6} {4:>6}   {5:<8}"
    print(HLINE)
    print(colorize(ROW.format("started on", "duration", "proc", "pass", "fail", "result"), Colors.WHITE))
    print(HLINE)
    for cmd, entries in groups.items():
        print(colorize(cmd, Colors.BLUE))
        for entry in entries:
            # format datetime
            entry[0] = format_datetime(datetime.fromisoformat(entry[0]))
            # format pass/fail
            entry[3] = format_count(int(entry[3]))
            entry[4] = format_count(int(entry[4]))
            # format test result
            entry[5] = colorize(entry[5], StatusColors[TestStatus[entry[5]]])
            # print it
            print(ROW.format(*entry))
        print()
    # end for

# end function

#-------------------------------------------------------------------------------
#
def clear_results(args):
    # determine results to keep
    total_count = 0
    remaining = []
    try:    
        with open(RESULTS_FILE, 'r') as inp:
            for line in inp:
                total_count += 1
                if not line.startswith(args.command):
                    remaining.append(line)
                # end if
            # end for
        # end with
    except FileNotFoundError:
        pass
    # end try
    remove_count = total_count - len(remaining)        
    if remove_count == 0:
        print("no results to remove for this command")
        return
    # end if

    # write remaining results to file
    with open(RESULTS_FILE, 'w') as out:
        for line in remaining:
            out.write(line)
        # end for
    # end with

    # done
    print("removed %d of %d results" % (remove_count, total_count))

# end function

#-------------------------------------------------------------------------------
# helpers
#-------------------------------------------------------------------------------
#
#-------------------------------------------------------------------------------
#
# custom exception class to terminate script execution
class Failed(Exception):
    def __init__(self, message):
        super().__init__(message)
# end class

#-------------------------------------------------------------------------------
#   
# horizontal line
HLINE = '-' * 80

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
def format_duration(seconds):
    if seconds < 60:
        return "%0.3fs" % seconds
    units = [
        ("a",   365 * 86400), # years
        ("mt",  30 * 86400),  # months
        ("w",   7 * 86400),   # weeks
        ("d",   86400),       # day
        ("h",   3600),        # hours
        ("min", 60),          # minutes
        ("s",   1)            # seconds
    ]
    parts = []
    for unit, duration in units:
        num_units, seconds = divmod(seconds, duration)
        if num_units > 0:
            parts.append("%d%s" % (num_units, unit))
    return " ".join(parts[:2])
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

#-------------------------------------------------------------------------------
# entry point
#-------------------------------------------------------------------------------
#
if __name__ == "__main__":
    # workaround to enable ansi colors in windows
    # https://stackoverflow.com/questions/12492810/python-how-can-i-make-the-ansi-escape-codes-to-work-also-in-windows
    if os.name == 'nt':
        os.system("")
    # end if    
    try:
        sys.exit(main())
    except Failed as e:
        error(e)
        sys.exit(TestStatus.ERROR)
    # end try
# end if
        
#-------------------------------------------------------------------------------
# end of file
