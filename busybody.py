import os
import time
import subprocess as sp
import sys

cwd = os.getcwd() 
readevents = os.getcwd() + "/qcrypto/timestamp3/readevents3"
chopper2 = os.getcwd() + "/qcrypto/remotecrypto/chopper2"
temp = os.getcwd() + '/temp'

if not os.path.exists(temp):
    os.makedirs(temp)

try:
    proc = sp.Popen([readevents + ' -e -a 1 -u -F | ' + chopper2 + ' -F -D' + temp], shell=True)
except:
    print "Unable execute shell command"

time.sleep(5)

# Terminator
try:
    pid = sp.check_output("pgrep -f readevents3", stderr=sp.STDOUT, shell=True).decode('utf-8').split()
    while (pid!=None):
        for i in range(len(pid)):
            sp.Popen(['kill -13 '+str(pid[i])],shell=True)    
        time.sleep(1)
        try:
            pid = sp.check_output("pgrep -f readevents3", stderr=sp.STDOUT, shell=True).decode('utf-8').split()
        except sp.CalledProcessError:
            pid = None
except:
    print "Unable to execute command to kill process"

time.sleep(5)

# Double terminator
try:
    sp.Popen(['rm -r ' + temp], shell=True)   # This is very dangerous, but then well...
except:
    print "Unable to delete temp directory"

time.sleep(5)


# ----------------------

if not os.path.exists(temp):
    os.makedirs(temp)

try:
    proc = sp.Popen([readevents + ' -e -a 1 -u -F | ' + chopper2 + ' -F -D' + temp], shell=True)
except:
    print "Unable execute shell command"

time.sleep(5)

# Terminator
try:
    pid = sp.check_output("pgrep -f readevents3", stderr=sp.STDOUT, shell=True).decode('utf-8').split()
    while (pid!=None):
        for i in range(len(pid)):
            sp.Popen(['kill -13 '+str(pid[i])],shell=True)    
        time.sleep(1)
        try:
            pid = sp.check_output("pgrep -f readevents3", stderr=sp.STDOUT, shell=True).decode('utf-8').split()
        except sp.CalledProcessError:
            pid = None
except:
    print "Unable to execute command to kill process"

time.sleep(5)

# Double terminator
try:
    sp.Popen(['rm -r ' + temp], shell=True)   # This is very dangerous, but then well...
except:
    print "Unable to delete temp directory"