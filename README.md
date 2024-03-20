[![pypi](https://img.shields.io/pypi/v/stressy)](https://pypi.org/project/stressy)

# stressy

A tool to repeatedly run a shell command until failure.

  - Easy to use: Just put `stressy` in front of a command to repeat it until it returns a non-zero exit code.
  - Allows specifying a minimum number of runs or duration required to pass a stress test.
  - Supports running a command concurrently using multiple processes.
  - Keeps track of test results and statistics in a logfile.

## Installation

For end users:
```bash
pip install stressy
```

For developers/contributors:
```bash
git clone https://github.com/dapaulid/stressy.git
pip install -e stressy/
```

This will checkout the source and install it from the local directory (a.k.a. [Editable Install](https://setuptools.pypa.io/en/latest/userguide/development_mode.html)).

If you run into any trouble during installation, make sure that `pip` is available and up-to-date:
```bash
pip install --upgrade pip
```

## Usage

```bash
usage: stressy [-h] [-n RUNS] [-d DURATION] [-p PROCESSES] [-t TIMEOUT] [-s SLEEP] [-c] [-q | -l] [-r] [--clear-results] ...

stressy v1.0.4 - a tool to repeatedly run a command until failure
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
  stressy echo hello              # repeat until failure or ctrl-c
  stressy -n 1k -q echo hello     # repeat 1000 times, output failures only
  stressy -d 12h -p 4 echo hello  # repeat for 12 hours with 4 processes in parallel
  stressy -n 3 -c bad_command     # repeat after first failure  
  stressy -r                      # output previous results and statistics

```
