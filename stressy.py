#!/usr/bin/env python3.11
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
import subprocess
import argparse
import os
import sys
import signal
import glob
import shutil
import enum
import datetime
import time
from timeit import default_timer as timer


#-------------------------------------------------------------------------------
# types
#-------------------------------------------------------------------------------
#
# enum used to specify test result. also used as exit code
class TestStatus(enum.IntEnum):
    PASSED       = 0
    FAILED       = 1
    CANCELLED    = 2
    ERROR        = 3
# end class

class TestResult:
    status       = None
    passed_runs  = 0
    failed_runs  = 0
    duration     = None
# end class

class OutputMode(enum.StrEnum):
    ALL          = 'all'
    FAIL         = 'fail'

    FILE         = 'file'
    NONE         = 'none'
# end enum

# log file name formats
class LogName(enum.StrEnum):
    TEMP         = ".stress_p%d.log"
    PASSED       = "stress_p%d_good.log"
    FAILED       = "stress_p%d_bad.log"
    CLEAN        = "stress_*.log"
    CLEAN_TEMP   = ".stress_*.log"  
# end enum

#-------------------------------------------------------------------------------
# main
#-------------------------------------------------------------------------------
#
def main():

    # parse command line
    parser = argparse.ArgumentParser(description='repeatedly run a command until failure')
    parser.add_argument('command', type=str, nargs='+', 
        help="the shell command to be executed")
    parser.add_argument('-r', '--runs', type=int, default=None, 
        help="number of repetitions. Repeat until failure if not specified")
    parser.add_argument('-p', '--processes', type=int, default=1, 
        help="number of processes to run the command in parallel")
    parser.add_argument('-t', '--timeout', type=float, default=None, 
        help="timeout in seconds for command to complete")
    parser.add_argument('-s', '--sleep', type=float, default=None,
        help="duration in seconds to wait before next run")
    parser.add_argument('-o', '--output', choices=list(OutputMode), default=OutputMode.ALL,
        help="destination for command output (stdout/stderr)")
    parser.add_argument('-c', '--continue', action='store_true', dest='cont',
        help="continue after first failure")
    args = parser.parse_args()

    # convert command from list to string
    args.command = subprocess.list2cmdline(args.command)

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
    
    # use colors
    if result.status == TestStatus.PASSED:
        summary = colorize(summary, Colors.GREEN)
    elif result.status == TestStatus.FAILED:
        summary = colorize(summary, Colors.RED)
    elif result.status == TestStatus.CANCELLED:
        summary = colorize(summary, Colors.YELLOW)
    # end if

    # print it
    print(summary)

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
        elif not verbose:
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
                proc_msg = "exited with code %d" % returncode

            except subprocess.TimeoutExpired:
                # process exceeded time limit
                kill(proc)              
                proc_success = False
                proc_msg = "killed due to timeout of %0.3f seconds" % args.timeout              
            # end try

            # output process output on failure
            if args.output == OutputMode.FAIL and not proc_success:
                print_complete()
                print(proc.stdout.read())
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
           
            # handle sleep if specified
            if args.sleep:
                time.sleep(args.sleep)
            # end if


        except KeyboardInterrupt:
            result.status = TestStatus.CANCELLED
            break
        # end try

    # end while

    # finish possible print_over
    #print_complete()

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

    # done
    return result
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
# Ansi colors
class Colors(enum.StrEnum):
    RED          = '\x1b[1;31m'
    GREEN        = '\x1b[1;32m'
    YELLOW       = "\x1b[1;33m"
    WHITE        = "\x1b[1;37m"
    RESET        = '\x1b[0m'
# end enum

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
		return "%.3f seconds" % seconds
	else:
		return str(datetime.timedelta(seconds=seconds)) # x days, H:MM:SS
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
