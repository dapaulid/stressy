[![pypi](https://img.shields.io/pypi/v/stressy)](https://pypi.org/project/stressy)

# stressy

A simple tool to repeatedly run a shell command until failure.

## Installation

```bash
pip install stressy
```

## Usage

```
usage: stressy.py [-h] [-n RUNS] [-d DURATION] [-p PROCESSES] [-t TIMEOUT] [-s SLEEP] [-c] [-q | -l] [-r] [--clear-results] [command ...]

stressy v1.0.3 - a tool to repeatedly run a command until failure
  https://github.com/dapaulid/stressy

positional arguments:
  command               the shell command to execute

options:
  -h, --help            show this help message and exit
  -q, --quiet           print subprocess output only if command fails
  -l, --logfile         write subprocess output to log files

execution:
  -n RUNS, --runs RUNS  number of repetitions, like 1000 or 10k
  -d DURATION, --duration DURATION
                        repetition duration, like 30min or 12h
  -p PROCESSES, --processes PROCESSES
                        number of processes to run the command in parallel
  -t TIMEOUT, --timeout TIMEOUT
                        maximum duration for command to complete
  -s SLEEP, --sleep SLEEP
                        duration in seconds to wait before next run
  -c, --continue        continue after first failure

result history:
  -r, --results         print result history for the given command
  --clear-results       clear result history for the given command

examples:
  stressy.py echo hello              # repeat until failure or ctrl-c
  stressy.py -n 1k -q echo hello     # repeat 1000 times, output failures only
  stressy.py -d 12h -p 4 echo hello  # repeat for 12 hours with 4 processes in parallel
  stressy.py -n 3 -c bad_command     # repeat after first failure  
  stressy.py -r                      # output previous results and statistics
```
