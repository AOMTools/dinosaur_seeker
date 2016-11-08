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

FILENAME = 'test2'

# Timing: this is just to monitor how much time it takes for this procedure (which supposed to be medium fast) will take
startime=time.time()

# Timing parameters: in terms of ms
timebin = 1		# The timing window for each bin
setback = 5			# How long before the trigger to start recording
setforward = 55		# How long after the trigger to stop recording

# Some parameters of the triggering
trigcounts = 95
lookuptime = 1

# Window of the data to look for (default: startcut = 0, endcut = 1)
startcut = 0
endcut = 1

# Conversion ratio (from timestamp to ms)
convratio = 8 * 1000 * 1000 

# Open and load the timestamp file
f = open(FILENAME, 'rb')
loaddata = np.fromfile(file=f, dtype='uint64')

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

# ----- END ----- #


# Procedures to create a 2D binned array of the binned counts for each triggering events

# Get the total number of bins
nofbins = int((setforward + setback) / timebin)

# Obtain the timesdata array that contain masked data of signal from channel 1 and 2
data_sig1 = channel_array & 0x1			# Get a masked array with that particular channel
data_sig2 = (channel_array & 0x2) >> 1	# Get a masked array in channel 2, and shifting the masked array one bit right

# Get some basic information from the first triggering event, along with the construction of completed array
completed_array1, bin_edges = np.histogram(time_array, bins = nofbins, range = (trigger_time_array[0] - setback*convratio, trigger_time_array[0] + setforward*convratio), weights=data_sig1)
completed_array2, bin_edges = np.histogram(time_array, bins = nofbins, range = (trigger_time_array[0] - setback*convratio, trigger_time_array[0] + setforward*convratio), weights=data_sig2)
timebin_array = (bin_edges[:-1] - trigger_time_array[0]) / convratio

# Looping through the rest of the time array
for i in range(1, len(trigger_time_array)):
	eachtrigger_array1, bin_edges = np.histogram(time_array, bins = nofbins, range = (trigger_time_array[i] - setback*convratio, trigger_time_array[i] + setforward*convratio), weights=data_sig1)
	eachtrigger_array2, bin_edges = np.histogram(time_array, bins = nofbins, range = (trigger_time_array[i] - setback*convratio, trigger_time_array[i] + setforward*convratio), weights=data_sig2)
	completed_array1 = np.vstack((completed_array1, eachtrigger_array1))
	completed_array2 = np.vstack((completed_array2, eachtrigger_array2))

# ----- END ----- #
np.savetxt(FILENAME + "_ch1", completed_array1, fmt='%i')
np.savetxt(FILENAME + "_ch2", completed_array2, fmt='%i')
# np.savetxt(FILENAME + "_timebin", timebin_array, fmt='%10.5f')
# np.savetxt(FILENAME + "_trigtime", trigger_time_array/convratio, fmt='%10.5f')

# Timing: stop the stopwatch
t = time.time() - startime;
print("Run time:"+ str(t) +"s")


