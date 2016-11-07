import os
import time

# Timing: this is just to monitor how much time it takes for this procedure (which supposed to be medium fast) will take
startime=time.time()

cwd = os.getcwd() + '/data'

# List method
files = sorted(os.listdir(cwd))
print files

# Timing: stop the stopwatch
t = time.time() - startime;
print("Run time:"+ str(t) +"s")