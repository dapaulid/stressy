# stressy

A simple tool to repeatedly run a shell command until failure.

## Usage

```
usage: stressy.py [-h] [-r RUNS] [-p PROCESSES] [-t TIMEOUT] [-o {fail,stdio,file,none}] [-c] command [command ...]

repeatedly run a command until failure

positional arguments:
  command               the shell command to be executed

options:
  -h, --help            show this help message and exit
  -r RUNS, --runs RUNS  number of repetitions. Repeat until failure if not specified
  -p PROCESSES, --processes PROCESSES
                        number of processes to run the command in parallel
  -t TIMEOUT, --timeout TIMEOUT
                        timeout in seconds for command to complete
  -o {fail,stdio,file,none}, --output {fail,stdio,file,none}
                        destination for command output (stdout/stderr)
  -c, --continue        continue after first failure
```
