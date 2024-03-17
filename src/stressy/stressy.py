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
import os
import shutil
import subprocess
import sys
import time

from datetime import datetime

try:
	import utils
	from utils import Failed, Colors, prog
except ModuleNotFoundError:
	from stressy import utils
	from stressy.utils import Failed, Colors, prog
# end try

#-------------------------------------------------------------------------------
# types
#-------------------------------------------------------------------------------
#
class TestResult:
    status       = None       # the TestStatus code
    runs         = 0          # total number of completed runs so far
    passed_runs  = 0          # the number of successfully completed runs
    failed_runs  = 0          # the number of failed runs
    start_time   = None       # the timestamp of test start 
    duration     = None       # the total test duration in seconds so far
    duration_eta = None       # estimated test duration until completion
    completed_on = None       # datetime of test completion
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

# path to file for storing test results
RESULTS_FILE = os.path.join(utils.OsPaths.APPDATA, "stressy.tsv")

# usage examples shown at end of help description
USAGE_EXAMPLES = """
  %(prog)s echo hello              # repeat until failure or ctrl-c
  %(prog)s -n 1k -q echo hello     # repeat 1000 times, output failures only
  %(prog)s -d 12h -p 4 echo hello  # repeat for 12 hours with 4 processes in parallel
  %(prog)s -n 3 -c bad_command     # repeat after first failure  
  %(prog)s -r                      # output previous results and statistics
"""

#-------------------------------------------------------------------------------
# main
#-------------------------------------------------------------------------------
#
def main():

    # parse command line
    parser = argparse.ArgumentParser(
        description="%s v%s - %s\n  %s" % (prog.name, prog.version, prog.description, utils.colorize(prog.website, Colors.LINK)),
        epilog="examples:" + utils.format_comments(USAGE_EXAMPLES),
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('command', type=str, nargs='*', 
        help="the shell command to execute")
    # execution options
    exec_group = parser.add_argument_group("execution")
    exec_group.add_argument('-n', '--runs', type=utils.parse_count,
        help="number of repetitions, like 1000 or 10k")
    exec_group.add_argument('-d', '--duration', type=utils.parse_duration,
        help="repetition duration, like 30min or 12h")
    exec_group.add_argument('-p', '--processes', type=utils.parse_count, default=1, 
        help="number of processes to run the command in parallel")
    exec_group.add_argument('-t', '--timeout', type=utils.parse_duration,
        help="maximum duration for command to complete")
    exec_group.add_argument('-s', '--sleep', type=utils.parse_duration,
        help="duration in seconds to wait before next run")
    exec_group.add_argument('-c', '--continue', action='store_true', dest='cont',
        help="continue after first failure")
    # output options
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument('-q', '--quiet', action='store_true',
        help="print subprocess output only if command fails")
    output_group.add_argument('-l', '--logfile', action='store_true',
        help="write subprocess output to log files")
    # result history 
    hist_group = parser.add_argument_group("result history")
    hist_group.add_argument('-r', '--results', action='store_true',
        help="print result history for the given command")
    hist_group.add_argument('--clear-results', action='store_true',
        help="clear result history for the given command")        
    # that's all   
    args = parser.parse_args()

    # convert command from list to string
    args.command = subprocess.list2cmdline(args.command)

    # determine output mode from given flags
    if args.logfile:
        args.output = OutputMode.FILE
    elif args.quiet:
        args.output = OutputMode.FAIL
    else:
        args.output = OutputMode.ALL
    # end if

    # handle result history options
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
    summary += ", took %s" % utils.format_duration(result.duration)
    
    # print it
    print(utils.colorize(summary, StatusColors[result.status]))

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
            utils.print_complete()            
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
            
            start_time = utils.timer()        
            try:
                returncode = proc.wait(remaining_timeout)
                # process completed
                proc_success = returncode == 0              
                proc_msg = "exited with code %d on %s" % (returncode, datetime.now())

            except subprocess.TimeoutExpired:
                # process exceeded time limit
                utils.kill(proc)              
                proc_success = False
                proc_msg = "killed due to timeout of %0.3f seconds" % args.timeout              
            # end try

            # output process output on failure
            if args.output == OutputMode.FAIL and not proc_success:
                utils.print_complete()
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
                elapsed = utils.timer() - start_time          
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
            utils.remove_files(LogName.CLEAN_TEMP)                
        # end if
    # end try
                
# end function

#-------------------------------------------------------------------------------
#
def check_completed(args, result):

    # update total number of runs
    result.runs = result.passed_runs + result.failed_runs    

    # determine total elapsed time
    result.duration = utils.timer() - result.start_time

    # update estimate time until completion if possible
    if args.runs is not None and result.runs > 0:
        duration_eta_n = result.duration / result.runs * (args.runs - result.runs)
    else:
        duration_eta_n = None
    # end if
    if args.duration is not None:
        duration_eta_d = args.duration - result.duration
    else:
        duration_eta_d = None
    # end if
    if duration_eta_n is None:
        result.duration_eta = duration_eta_d
    elif duration_eta_d is None:
        result.duration_eta = duration_eta_n
    else:
        result.duration_eta = max(duration_eta_d, duration_eta_n)
    # end if

    # check if specified number of runs reached. None means 'forever', unless duration specified
    runs_reached = args.runs is not None and result.runs >= args.runs

    # check if specified duration reached. None means 'forever', unless number of runs specified
    duration_reached = args.duration is not None and result.duration >= args.duration

    # we're done if a failure occurred and the 'continue' flag is not set
    if result.failed_runs > 0 and not args.cont:
        return True

    # we're done when all specified conditions are met
    if args.runs is None:
        return duration_reached
    elif args.duration is None:
        return runs_reached
    else:
        return runs_reached and duration_reached
# end function

#-------------------------------------------------------------------------------
#
def stress_test(args):

    if args.output == OutputMode.FILE:
        # remove old log files first
        utils.remove_files(LogName.CLEAN)
    # end if

    # start measuring execution time
    result = TestResult()
    result.start_time =  utils.timer()
    try:
        while not check_completed(args, result):

            # output info
            info = "run #%d" % result.runs
            if args.runs is not None:
                info += " of %d" % args.runs
            info += ", %d failures since %s" % (result.failed_runs, utils.format_duration(result.duration))
            if result.duration_eta is not None:
                info += ", ETA %s" % utils.format_duration(result.duration_eta)
            if args.output == OutputMode.ALL:
                print(utils.HLINE)
                print("| " + utils.colorize(info.ljust(len(utils.HLINE)-4), Colors.WHITE) + " |")
                print(utils.HLINE)
            else:
                utils.print_over("[ %s ]" % utils.colorize(info, Colors.WHITE))
            # end if    
                
            # do it
            if run(args):
                # success
                result.passed_runs += 1             
            else: 
                # failed
                result.failed_runs += 1
            # end if
           
            handle_sleep(args.sleep)
        # end while
            
    except KeyboardInterrupt:
        result.status = TestStatus.CANCELLED
    # end try

    # determine total elapsed time
    result.duration = utils.timer() - result.start_time
    result.completed_on = datetime.now()

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
        utils.print_complete(clear=True)
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
        info = "sleeping for %s" % utils.format_duration(seconds)
        utils.print_over("[ %s ]" % utils.colorize(info, Colors.WHITE))
        time.sleep(1)
        seconds = max(seconds - 1, 0)
    # end if
    utils.print_over("")
# end function

#-------------------------------------------------------------------------------
#
def append_result(args, result):
    # format result
    entry = [
        args.command,
        result.completed_on.isoformat(), 
        str(result.duration),
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
    ROW = "{0:<25} {1:>10} {2:>10} {3:>6} {4:>6} {5:>6}   {6:<8}"
    print(utils.HLINE)
    print(utils.colorize(ROW.format("completed on", "duration", "per run", "proc", "pass", "fail", "result"), Colors.WHITE))
    print(utils.HLINE)
    for cmd, entries in groups.items():
        print(utils.colorize(cmd, Colors.CYAN))
        for entry in entries:
            avg = float(entry[1]) / (int(entry[3]) + int(entry[4]))
            fmt_entry = (
                utils.format_datetime(datetime.fromisoformat(entry[0])),        # completed on
                utils.format_duration(float(entry[1])),                         # duration
                utils.format_duration(avg),                                     # per run
                utils.format_count(int(entry[2])),                              # proc
                utils.format_count(int(entry[3])),                              # pass
                utils.format_count(int(entry[4])),                              # fail 
                utils.colorize(entry[5], StatusColors[TestStatus[entry[5]]]),   # result
            )
            # print it
            print(ROW.format(*fmt_entry))
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
# entry point
#-------------------------------------------------------------------------------
#
if __name__ == "__main__":
    try:
        sys.exit(main())
    except Failed as e:
        utils.error(e)
        sys.exit(TestStatus.ERROR)
    # end try
# end if
        
#-------------------------------------------------------------------------------
# end of file