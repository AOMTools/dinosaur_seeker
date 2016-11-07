"""
FAITHFUL BINNER v 1.00
These procedural lines (probably with some other stuffs) will align the timestamp data with respect to the trigger signal. 
The output of (the first) part of the program is the binning array which contain the information about how many count for each time bin for every successful trigger cases. 
Any doubt just ask the author

Author = Adrian Utama
Oct 2016
"""

from __future__ import division # without this, python 2.x will understand 1/2 as 0.0
import numpy as np
import time
import os

# Timing: this is just to monitor how much time it takes for this procedure (which supposed to be medium fast) will take
startime=time.time()

# Get files
cwd = os.getcwd() + '/data'
files = sorted(os.listdir(cwd))

# For the first data in the array
filename = 'data/' + files[0]

loaddata = np.array([0], dtype = 'uint64') # Create a zero entry array

for i in range (0, 5):
	# Looping over the rest of the files
	filename = 'data/' + files[i]
	# Open and load the timestamp file
	f = open(filename, 'rb')
	f.seek(20)		# This is for the header in chopper (should be 20 bytes = 160 bits of header)
	data = np.fromfile(file=f, dtype='uint64')[:-1]		# This -1 thing is for the footer (8 bytes of nothingness)
	loaddata = np.hstack((loaddata, data))

loaddata = loaddata[1:]		# Clear the initialised zero entry

# --------------------------------------  BEGIN PROCEDURAL LINES OF FAITHFUL BINNER ------------------------------------------------ #

# Timing parameters: in terms of ms
timebin = 0.5		# The timing window for each bin
setback = 0			# How long before the trigger to start recording
setforward = 40		# How long after the trigger to stop recording

# Some parameters of the triggering
trigcounts = 95
lookuptime = 1

# Window of the data to look for (default: startcut = 0, endcut = 1)
startcut = 0
endcut = 1

# Conversion ratio (from timestamp to ms)
convratio = 8 * 1000 * 1000 

# # For debugging
# for values in loaddata:
# 	print np.binary_repr(values,64)

# Some magic code to obtain the timing of the detection events. Each time bin in 125 ps
time_array = np.uint64((loaddata << 32) >> 15) + np.uint64(loaddata >> 47) 

# Some magic code to obtain the channel of the detection events
channel_array = np.uint8((loaddata >> 32) & 0xf)

# ----- Procedures to find the appropriate triggering time -----

trigsig_index = np.nonzero(channel_array & 0x2)		# Only looking at channel 2 for trigger signal
lookuptimets = lookuptime * convratio				# Amount of time to look up for trigger (converted to timestamp time)
timetrig_array = time_array[trigsig_index]			# Obtain the array of times of a detected trigger signal

# trigcheck_array contains the time difference (normalised to the lookup time) between the first and last trigger signal (determined by trigcounts)
trigcheck_array = (timetrig_array[trigcounts-1:] - timetrig_array[:-trigcounts+1]) / lookuptimets  	# The plus/minus 1 is because you need to compare the events which are spaced trigcounts-1

# If trigcheck_array is less than 1, that particular index is a successful start of the trigger signal
trigcheck_array = np.floor(trigcheck_array)			# The values smaller than 1 will be round down to 0.

# Extract out the index (row number) in the timestamp file that signifies the start of the trigger signal
trigger_time_index = np.extract(trigcheck_array == 0, trigsig_index)
trigger_time_array = time_array[trigger_time_index]

# Cutting of trigger time index and trigger time array to select the time window we want to look at 
starttime = startcut * time_array[-1]
endtime = endcut * time_array[-1] 
starttime = starttime + convratio * (setback + 1)			# Such that it does not trigger on an unfinished business (+ 1ms for safety)
endtime = endtime - convratio * (setforward + 1)			# Such that it does not trigger on an unfinished business (+ 1ms for safety)
trigger_time_index = trigger_time_index[(trigger_time_array > starttime) & (trigger_time_array < endtime)]
trigger_time_array = trigger_time_array[(trigger_time_array > starttime) & (trigger_time_array < endtime)]

# ------------------------------------------------------------- END ---------------------------------------------------------------- #

# Timing: stop the stopwatch
t = time.time() - startime;
print("Run time:"+ str(t) +"s")
