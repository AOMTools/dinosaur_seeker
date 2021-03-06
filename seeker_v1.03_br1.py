"""
Created on Thurs Oct 27 2016
@author: Adrian Utama

Dinosaur Seeker v1.03 branch 1
The GUI to monitor the averaged extinction of the atom based on a predefined trigger signal
1.01: Added functionality of fitting on the go and displaying some relevant values on the GUI. Also fixed some bugs, particularly concerning low trigger counts.
1.02: Added functionality to save the files, and to communicate with external program (using port 5558)
1.03: Added a temporary patch to switch off and on the power supply if the memory allocation for the driver fails
28 Nov - Added in the return value of decay time and yoffset when ask to reset

PS: The Queue function is not (yet) implemented as the subprocess consumes little time/memory. We also do not need to implement the workerthread as there is (not yet) asynchronous communication
"""

from __future__ import division # without this, python 2.x will understand 1/2 as 0.0
import Tkinter
import os
import time
import Queue
import threading
import json
import subprocess as sp
import zmq

# PLOTTING ADD ON --->
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2TkAgg
from matplotlib.figure import Figure
import matplotlib.animation as animation
import matplotlib.ticker as mtick
from lmfit import Model
# <---

# TEMPORARY PATCH ADD ON --->
from hameg_control import Hameg
HM_PORTS="/dev/serial/by-id/usb-HAMEG_HAMEG_HO720_013105245-if00-port0"
HM_PS=Hameg(HM_PORTS)
# <---

REFRESH_RATE = 100          # 100ms
DATA_REFRESH_RATE = 3000    # 3s (probably around 4-6s in the end, depending on the computer)
MONITORING_TIME = 40        # Looking at the traces of 40 ms in length
DATA_TIMEBIN = 0.5          # Timebin for each data. Higher number lower resolution

PROBESTART = 0.5    # Where does the probe start. Important for fitting values

# Define the fitting function
def exp_decay(x, yoff, amp, dec):
    y = yoff + amp * np.exp(- (x-PROBESTART) / dec)
    return y

class GuiPart:
    def __init__(self, master, queue, endCommand):
        self.master = master
        self.queue = queue

        # Variable to change the status of measurement: 0 - initial, 1 - start, 2 - stop, 3 - clear
        self.status = 0

        # Trigger to record
        self.rec_trigger = 0

        # Set up the GUI
        Tkinter.Label(master, text='Measurement Sequence', font=("Helvetica", 16)).grid(row=1, padx=5, pady=5, column=1, columnspan = 2)

        self.status_display = Tkinter.StringVar(master)
        self.status_display.set("Start")      # 0 and 3 - start, 1 - stop, 2 - clear 
        self.status_button = Tkinter.Button(master, font=("Helvetica", 16), textvariable=self.status_display, command=lambda:self.statusChange(), width = 10)
        self.status_button.grid(sticky="w", row=1, column=3, columnspan = 1, padx=5, pady=5)

        self.message_display = Tkinter.StringVar(master)
        self.message_display.set("Starting program")      # 0 and 3 - start, 1 - stop, 2 - clear 
        self.message = Tkinter.Label(master, font=("Helvetica", 16),  textvariable=self.message_display, width=30, bg="white", fg="black", padx=2, pady=2)
        self.message.grid(row=1, padx=5, pady=5, column=4, columnspan = 2)

        # Part of gui for relevant parameters
        self.frame1 = Tkinter.Frame(self.master)
        self.new_trigger_cases_display = Tkinter.StringVar(master)
        self.new_trigger_cases_display.set("New:")
        self.total_trigger_cases_display = Tkinter.StringVar(master)
        self.total_trigger_cases_display.set("Total:")
        self.trigger_rate_display = Tkinter.StringVar(master)
        self.trigger_rate_display.set("Rate:")
        self.process_time_display = Tkinter.StringVar(master)
        self.process_time_display.set("PROCESS TIME:")        
        Tkinter.Label(self.frame1, font=("Helvetica", 12), text="TRIGGER CASES", width=16, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame1, font=("Helvetica", 12), textvariable=self.new_trigger_cases_display, width=16, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame1, font=("Helvetica", 12), textvariable=self.total_trigger_cases_display, width=10, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame1, font=("Helvetica", 12), textvariable=self.trigger_rate_display, width=18, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame1, font=("Helvetica", 12), textvariable=self.process_time_display, width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        self.frame1.grid(row = 2, columnspan =10, sticky=Tkinter.W)

        # Part of gui for fitting values
        self.frame2 = Tkinter.Frame(self.master)
        self.redchi_display = Tkinter.StringVar(master)
        self.redchi_display.set(u"Reduced \u03c7 \u00b2 :")
        self.ext_display = Tkinter.StringVar(master)
        self.ext_display.set(u"EXTINCTION:")
        Tkinter.Label(self.frame2, font=("Helvetica", 12), text="FITTING RESULT", width=16, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame2, font=("Helvetica", 12), textvariable=self.redchi_display, width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame2, font=("Helvetica", 12), text="", width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame2, font=("Helvetica", 12), textvariable=self.ext_display, width=24, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        self.frame2.grid(row = 3, columnspan =10, sticky=Tkinter.W)

        self.frame3 = Tkinter.Frame(self.master)
        self.yoff_display = Tkinter.StringVar(master)
        self.yoff_display.set(u"Yoff:")
        self.amp_display = Tkinter.StringVar(master)
        self.amp_display.set(u"Amp:")
        self.dec_display = Tkinter.StringVar(master)
        self.dec_display.set(u"Dec:")
        Tkinter.Label(self.frame3, font=("Helvetica", 12), text="FIT PARAMETERS", width=16, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame3, font=("Helvetica", 12), textvariable=self.yoff_display, width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame3, font=("Helvetica", 12), textvariable=self.amp_display, width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame3, font=("Helvetica", 12), textvariable=self.dec_display, width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        self.frame3.grid(row = 4, columnspan =10, sticky=Tkinter.W)

        # PLOTTING ADD ON--->
        self.xdata = np.arange(0.5, MONITORING_TIME, DATA_TIMEBIN)
        self.ydata = np.array([1.] * len(self.xdata))
        self.xdata_bf = np.arange(0.5, MONITORING_TIME, DATA_TIMEBIN)
        self.ydata_bf = np.array([1.] * len(self.xdata))
        self.ystderr = np.array([0.] * len(self.xdata))

        self.figure = Figure(figsize=(10, 5))
        self.figure_subplot = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().grid(row =5, column = 1, columnspan = 8)
        
        self.line, (self.bottoms, self.tops), (self.verts,) = self.figure_subplot.errorbar(self.xdata, self.ydata, yerr = self.ystderr, fmt = 'o', ls = '', markersize = 4, color = 'red')
        self.line_bf, = self.figure_subplot.plot(self.xdata_bf, self.ydata_bf)
        self.figure_subplot.grid()

        self.figure_subplot.set_xlabel("Time (ms)")
        self.figure_subplot.set_ylabel("Count rate (ms-1)")
        # self.figure_subplot.yaxis.set_major_formatter(mtick.FormatStrFormatter('%.e'))
        # self.figure_subplot.set_xticklabels([])
        self.figure.tight_layout()

        self.anim = animation.FuncAnimation(self.figure, self.animated, interval = 500, blit=False)
        # <---

        Tkinter.Button(master, text='Shutdown', font=("Helvetica", 16), command=endCommand).grid(sticky="w", row=10, column=1, padx=5, pady=5)
        self.recdir_entry = Tkinter.Entry(master, width=50, font=("Helvetica", 14), justify=Tkinter.LEFT)
        self.recdir_entry.grid(row=10, column=2, columnspan = 3)
        self.rec_button = Tkinter.Button(master, text='Record', font=("Helvetica", 16), command=lambda:self.recordData(), state = 'disabled')
        self.rec_button.grid(row=10, column=5, padx=5, pady=5)


    def animated(self, i):
        self.line.set_xdata(self.xdata)
        self.line.set_ydata(self.ydata)
        yerr_top = self.ydata - self.ystderr
        yerr_bot = self.ydata + self.ystderr
        self.bottoms.set_ydata(yerr_bot)
        self.tops.set_ydata(yerr_top)        
        # Magic code to get back the missing vertical line in the errorbars
        new_segments_y = [np.array([[x, yt], [x,yb]]) for x, yt, yb in zip(self.xdata, yerr_top, yerr_bot)]
        self.verts.set_segments(new_segments_y)
        self.figure_subplot.set_xlim([0, MONITORING_TIME])
        self.figure_subplot.set_ylim([0, max(self.ydata)*1.1])
        # For the best line
        self.line_bf.set_xdata(self.xdata_bf)
        self.line_bf.set_ydata(self.ydata_bf)
        return self.line,

    def statusChange(self):
        if self.status == 0:
            self.status_button['state'] = 'disabled'
            self.status_display.set("Stop")
            self.message_display.set("Preparing to start")
            self.message['bg'] = 'red'
            self.master.update_idletasks()
            self.status = 1
        elif self.status == 1:
            self.status_button['state'] = 'disabled'
            self.status_display.set("Clear")
            self.message_display.set("Preparing to stop")
            self.message['bg'] = 'red'
            self.master.update_idletasks()
            self.status = 2
        elif self.status == 2:
            self.status_button['state'] = 'disabled'
            self.status_display.set("Start")
            self.message_display.set("Preparing to clean")
            self.rec_button['state'] = 'disabled' # Disable the record button 
            self.message['bg'] = 'red'
            self.master.update_idletasks()
            self.status = 3
        elif self.status == 3: 
            self.status_button['state'] = 'disabled'
            self.status_display.set("Stop")
            self.message_display.set("Preparing to start again")
            self.message['bg'] = 'red'
            self.master.update_idletasks()
            self.status = 1

    def recordData(self):
        self.status_button['state'] = 'disabled'
        self.message_display.set("Recording")
        self.message['bg'] = 'red'
        self.master.update_idletasks()
        self.rec_trigger = 1    # Create the trigger to be processed by the master 

    def processIncoming(self):
        """Handle all messages currently in the queue, if any."""
        while self.queue.qsize(  ):
            try:
                msg = self.queue.get(0)
                # Check contents of message and do whatever is needed. As a
                # simple test, print it (in real life, you would
                # suitably update the GUI's display in a richer fashion).
                print msg
            except Queue.Empty:
                # just on general principles, although we don't
                # expect this branch to be taken in this case
                pass

class ThreadedClient:
    """
    Launch the main part of the GUI and the worker thread. periodicCall and
    endApplication could reside in the GUI part, but putting them here
    means that you have all the thread controls in a single place.
    """
    def __init__(self, master):
        """
        Start the GUI and the asynchronous threads. We are in the main
        (original) thread of the application, which will later be used by
        the GUI as well. We spawn a new thread for the worker (I/O).
        """
        self.master = master
        self.running = 1

        # Create the queue
        self.queue = Queue.Queue(  )

        # Set up the GUI part
        self.gui = GuiPart(master, self.queue, self.endApplication)
        master.protocol("WM_DELETE_WINDOW", self.endApplication)   # About the silly exit button

        # Start the procedure regarding the initialisation of experimental parameters and objects
        self.status = 0
        self.initialiseParameters()

        # Initialising the zmq server
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind("tcp://127.0.0.1:5558")
        print "The server is up. Ready to receive messages"

        # Set up the thread to do asynchronous I/O
        # More threads can also be created and used, if necessary
        self.thread1 = threading.Thread(target=self.workerThread1_zmq)
        self.thread1.start(  )
    
        # Start the periodic call in the GUI to check if the queue contains
        # anything
        self.periodicCall(  )

    def initialiseParameters(self):

        # Initialisation of several variables
        self.refresh_counter = 0        # refresh the plotting and data handling
        self.unread_file_index = 0      # This will contain the index of the first sorted unread files
        self.trigger_firstdata = 0      # This will get used up for the first processing of useful data & reset when it is restarted

        # Initialise the plotting & fitting arrays (again)
        self.gui.xdata = np.arange(0.5, MONITORING_TIME, DATA_TIMEBIN)
        self.gui.ydata = np.array([1.] * len(self.gui.xdata))
        self.gui.ystderr = np.array([0.] * len(self.gui.xdata))
        self.gui.xdata_bf = np.arange(0.5, MONITORING_TIME, DATA_TIMEBIN)
        self.gui.ydata_bf = np.array([1.] * len(self.gui.xdata))
        
        # Initialise some relevant parameters
        self.new_trigger_cases = 0
        self.total_trigger_cases = 0
        self.trigger_rate = 0
        self.process_time = 0
        self.acquire_time = 0
        self.startime_acq = 0

        # Initialise Fitting Values
        self.yoff_est = 1
        self.yoff_std = 0
        self.amp_est = 0
        self.amp_std = 0
        self.dec_est = 0
        self.dec_std = 0
        self.ext_est = 0
        self.ext_std = 0
        self.redchi = 0

    def initialiseDirectory(self):

        # This function will initialise and make ready the directory
        self.current_directory = os.getcwd()
        if not os.path.exists(self.current_directory + '/temp'):
            os.makedirs(self.current_directory + '/temp')
        else:
            print "The temp directory was not cleared. You might want to clear it first."
            self.gui.message_display.set("CAUTION: temp not cleared!")
            self.gui.message['bg'] = 'white'
            self.master.update_idletasks()          
        self.temp_directory = self.current_directory + '/temp'
        self.readevents_directory = self.current_directory + "/qcrypto/timestamp3/readevents3"
        self.chopper2_directory = self.current_directory + "/qcrypto/remotecrypto/chopper2"

        # Create the recording directory
        self.recdir = self.current_directory + '/data'
        self.gui.recdir_entry.delete(0, Tkinter.END)
        self.gui.recdir_entry.insert(0, self.recdir)

    def startRecording(self):
        try:
            proc = sp.Popen([self.readevents_directory + ' -e -a 1 -u -F | ' + self.chopper2_directory + ' -F -V -1 -D' + self.temp_directory], shell=True)
        except:
            print "Unable to start recording"
        time.sleep(1)   # To wait some time to start the recording process properly
        

    def stopRecording(self):
        # Terminator
        try:
            pid = sp.check_output("pgrep -f readevents3", stderr=sp.STDOUT, shell=True).decode('utf-8').split()
            while (pid!=None):
                for i in range(len(pid)):
                    sp.Popen(['kill -9 '+str(pid[i])],shell=True)    # Either -9 or -13
                time.sleep(1)
                try:
                    pid = sp.check_output("pgrep -f readevents3", stderr=sp.STDOUT, shell=True).decode('utf-8').split()
                except sp.CalledProcessError:
                    pid = None
            #for i in range(len(pid)):
            #    sp.Popen(['kill -9 '+str(pid[i])],shell=True)    
            #    time.sleep(0.5)
            #while (pid!=None):
            #    try:
            #        pid = sp.check_output("pgrep -f readevents3", stderr=sp.STDOUT, shell=True).decode('utf-8').split()
            #        time.sleep(0.1)
            #    except sp.CalledProcessError:
            #        pid = None
        except:
            print "Unable to execute command to kill process"

    def clearData(self):
        # Double Terminator
        try:
            sp.Popen(['rm -r ' + self.temp_directory], shell=True)   # This is very dangerous, but then well...
        except:
            print "Unable to delete temp directory"
        while os.path.exists(self.temp_directory):
            time.sleep(1)    # To wait some time to delete all the files properly

    def periodicCall(self):
        """
        Check every REFRESH_RATE ms if there is something new in the queue.
        """
        self.gui.processIncoming(  )

        # Setting a refresh rate for periodic call
        self.master.after(REFRESH_RATE, self.periodicCall)

        # Check status of the GUI, and assign the status of the Threaded client:
        # 0 - initial, 1 - pressed start button, and then measuring and analysing, 2 - pressed stop button, and then stopped and freeze, 5 - pressed clear button, and then cleared and ready to restart, 9 - ERROR (something wrong, probably click too fast)
        self.checkStatus()

        # Refresh the data handling and replotting
        if self.status == 1:
            self.refresh_counter += 1
            if self.refresh_counter >= DATA_REFRESH_RATE / REFRESH_RATE:
                self.gui.message_display.set("Processing triggers")
                self.gui.message['bg'] = 'yellow'
                self.master.update_idletasks()
                # -----> This line is to obtain the approximate acquiration time (for each cycle)
                self.endtime_acq = time.time() # Restart the stopwatch
                self.acquire_time = self.endtime_acq - self.startime_acq
                self.startime_acq = self.endtime_acq
                # <-----
                self.newData()
                self.updateParamGui()
                self.refresh_counter = 0
                self.gui.message_display.set("Processing done")
                self.gui.message['bg'] = 'green'
                self.master.update_idletasks()

        # PLOTTING ADD ON --->
        if not True:
            self.gui.ydata.pop(0)
            self.gui.ydata.append(self.average_opm)
        # <---

        # Writing the recorded data to the files
        if self.gui.rec_trigger == 1:
            if self.total_trigger_cases >= 5:   # Only records if there is sufficient data
                self.writeToFile()
                self.gui.rec_trigger = 0
                self.gui.status_button['state'] = 'normal'
                self.gui.message_display.set("Recording Finished")
                self.gui.message['bg'] = 'blue'
                self.master.update_idletasks()
            else:
                self.gui.rec_trigger = 0
                self.gui.status_button['state'] = 'normal'
                self.gui.message_display.set("DATA INSUFFICIENT")
                print "Cannot write to file. Data insufficient."
                self.gui.message['bg'] = 'white'
                self.master.update_idletasks()
 

        # Shutting down the program
        if not self.running:
            print "Shutting Down"
            import sys
            sys.exit()

    def checkStatus(self):
        
        # This procedural lines will check whether there is a change of status in GUI part (and apply the change in this client)
        if self.gui.status == 0:
            self.status = 0 # Nothing interesting
        elif self.gui.status == 1:
            if self.status == 0 or self.status == 3:
                self.startime_acq = time.time()     # Get the stopwatch started
                self.initialiseDirectory()
                self.startRecording()
                self.status = 1 # Go into the limbo state of measuring and analysing
                self.gui.status_button['state'] = 'normal'
                self.gui.message_display.set("Measurement started")
                self.gui.message['bg'] = 'green'
                self.master.update_idletasks()
        elif self.gui.status == 2:
            if self.status == 1:
                self.stopRecording()
                self.status = 2
                self.gui.status_button['state'] = 'normal'
                self.gui.message_display.set("Measurement stopped")
                self.gui.message['bg'] = 'blue'
                self.gui.rec_button['state'] = 'normal' # Get the record button to work
                self.master.update_idletasks()
        elif self.gui.status == 3:
            if self.status == 2:
                self.clearData()
                self.refresh_counter = 0    # Reset the refresh counter count
                self.status = 3
                self.gui.status_button['state'] = 'normal'
                self.gui.message_display.set("Data cleared")
                self.initialiseParameters() # Reset the important parameters again
                self.updateParamGui()
                self.gui.message['bg'] = 'white'
                self.master.update_idletasks()

    def newData(self):

        # Timing: this is just to monitor how much time it takes for this procedure (which supposed to be medium fast) to run
        startime_proc=time.time()

        files = sorted(os.listdir(self.temp_directory))

        # TEMPORARY PATCH ADD ON --->
        while True:
	    if len(files) > 0:
		break
	    else:
		self.gui.status_button['state'] = 'disabled'
		self.master.update_idletasks()
		self.stopRecording()
		print "The timestamp file write failed. Trying switching on and off the power supply" 
		print('Off hameg channel 2')
		HM_PS.output_off(2)
		time.sleep(5)
		print('On hameg channel 2')
		HM_PS.output_on(2)
		time.sleep(5)
		self.startRecording()
		time.sleep(5)
		self.gui.status_button['state'] = 'normal'
		files = sorted(os.listdir(self.temp_directory))
        # <---

        last_file_index = len(files) - 2   # -1 because of how array works in python. -1 again because we want to buffer the last file

        # ----- Magical procedures to get the data from the new incoming files -----

        # First, we create a array containing all the traces from the newest collated data 

        loaddata = np.array([0], dtype = 'uint64') # Create a zero entry array
        for i in range (self.unread_file_index, last_file_index + 1):   # Here, we +1 again because of how range works in python
            # Looping over the rest of the files
            filename = self.temp_directory + "/" + files[i]
            # Open and load the timestamp file
            f = open(filename, 'rb')
            f.seek(20)      # This is for the header in chopper (should be 20 bytes = 160 bits of header)
            data = np.fromfile(file=f, dtype='uint64')[:-1]     # This -1 thing is for the footer (8 bytes of nothingness)
            loaddata = np.hstack((loaddata, data))
        loaddata = loaddata[1:]     # Clear the initialised zero entry
        self.unread_file_index = last_file_index + 1    # We +1 because the next file to be read is +1 from the last one we currently reading
        
        # --------------------------------------  BEGIN PROCEDURAL LINES OF FAITHFUL BINNER ------------------------------------------------ #
        # Obtained from the program faithful binner v1.00

        # Timing parameters: in terms of ms
        timebin = DATA_TIMEBIN           # The timing window for each bin
        setback = -0.5                   # How long before the trigger to start recording
        setforward = MONITORING_TIME     # How long after the trigger to stop recording

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
        #   print np.binary_repr(values,64)

        # Some magic code to obtain the timing of the detection events. Each time bin in 125 ps
        time_array = np.uint64((loaddata << 32) >> 15) + np.uint64(loaddata >> 47) 

        # Some magic code to obtain the channel of the detection events
        channel_array = np.uint8((loaddata >> 32) & 0xf)

        # ----- Procedures to find the appropriate triggering time -----

        trigsig_index = np.nonzero(channel_array & 0x2)     # Only looking at channel 2 for trigger signal
        lookuptimets = lookuptime * convratio               # Amount of time to look up for trigger (converted to timestamp time)
        timetrig_array = time_array[trigsig_index]          # Obtain the array of times of a detected trigger signal

        # trigcheck_array contains the time difference (normalised to the lookup time) between the first and last trigger signal (determined by trigcounts)
        trigcheck_array = (timetrig_array[trigcounts-1:] - timetrig_array[:-trigcounts+1]) / lookuptimets   # The plus/minus 1 is because you need to compare the events which are spaced trigcounts-1

        # If trigcheck_array is less than 1, that particular index is a successful start of the trigger signal
        trigcheck_array = np.floor(trigcheck_array)         # The values smaller than 1 will be round down to 0.

        # Extract out the index (row number) in the timestamp file that signifies the start of the trigger signal
        trigger_time_index = np.extract(trigcheck_array == 0, trigsig_index)
        trigger_time_array = time_array[trigger_time_index]

        if trigger_time_index.size > 0: 
            # Cutting of trigger time index and trigger time array to select the time window we want to look at (Only cut if there is something... of course
            starttime = startcut * time_array[-1]
            endtime = endcut * time_array[-1] 
            starttime = starttime + convratio * (setback + 5)           # Such that it does not trigger on an unfinished business (+ 5ms for safety)
            endtime = endtime - convratio * (setforward + 5)            # Such that it does not trigger on an unfinished business (+ 5ms for safety)
            trigger_time_index = trigger_time_index[(trigger_time_array > starttime) & (trigger_time_array < endtime)]
            trigger_time_array = trigger_time_array[(trigger_time_array > starttime) & (trigger_time_array < endtime)]
			
        print trigger_time_index
        print "Size " + str(trigger_time_index.size)
        # ----- ADDITION ----- : To handle no triggering case
        if trigger_time_index.size > 0:

            # ----- Procedures to create a 2D binned array of the binned counts for each triggering events -----

            # Get the total number of bins
            nofbins = int((setforward + setback) / timebin)

            # Obtain the timesdata array that contain masked data of signal from channel 1 and 2
            data_sig1 = channel_array & 0x1         # Get a masked array with that particular channel
            data_sig2 = (channel_array & 0x2) >> 1  # Get a masked array in channel 2, and shifting the masked array one bit right

            # Get some basic information from the first triggering event, along with the construction of completed array
            completed_array1, bin_edges = np.histogram(time_array, bins = nofbins, range = (trigger_time_array[0] - setback*convratio, trigger_time_array[0] + setforward*convratio), weights=data_sig1)
            timebin_array = (bin_edges[:-1] - trigger_time_array[0]) / convratio

            # Looping through the rest of the time array
            for i in range(1, len(trigger_time_array)):
                eachtrigger_array1, bin_edges = np.histogram(time_array, bins = nofbins, range = (trigger_time_array[i] - setback*convratio, trigger_time_array[i] + setforward*convratio), weights=data_sig1)
                completed_array1 = np.vstack((completed_array1, eachtrigger_array1))

        # ------------------------------------------------------------- END ---------------------------------------------------------------- #

            # Now processing the obtained data and update the plot 

            if self.trigger_firstdata == 0:
                # Virgin data
                self.data_array = completed_array1
                self.time_array = timebin_array
                self.trigger_firstdata = 1  # Use up the trigger
            else:
                self.data_array = np.vstack((self.data_array, completed_array1))

            # Calculating the averages and standard error
            self.data_array_avg = np.average(self.data_array, axis = 0)
            self.data_array_sterr = np.std(self.data_array, axis = 0) / np.sqrt(len(self.data_array))

            # Getting all the relevant GUI parameters
            if trigger_time_index.size == 1:
                # Handling the cases that there is only one entry (trigger case), as the "length" of the array will automatically be the number of data points.
                self.new_trigger_cases = 1
                self.total_trigger_cases += 1
            else:
                self.new_trigger_cases = len(completed_array1)
                self.total_trigger_cases = len(self.data_array)
            time_elapsed = trigger_time_array[-1]/(convratio*1000)  # Convert time elapsed to s (from the start of ts to the last trigger signal)
            self.trigger_rate = self.total_trigger_cases / time_elapsed
            
            # ----------> PROCEDURE TO PLOT AND DO THE FITTING ON THE DATA
            if self.total_trigger_cases >= 5: 
                # Need at least 3 traces (such that the plotting and fitting can make sense >> blame ystderr). Turns out that we probably need more than 3 (for whatever wierd reasons). Let me just set to 5. 

                # Getting to the plotting program
                self.gui.xdata = self.time_array 
                self.gui.ydata = self.data_array_avg / DATA_TIMEBIN         # Need to divide by data_timebin to get the rate per ms
                self.gui.ystderr = self.data_array_sterr / DATA_TIMEBIN     # Need to divide by data_timebin to get the rate per ms

                # Creating and fitting to the exponentialmodel
                edmod = Model(exp_decay)
                xdata_fit = self.gui.xdata
                ydata_fit = self.gui.ydata
                ystderr_fit = self.gui.ystderr
                # Set parameter hints
                edmod.set_param_hint('yoff', value = 1, min=0)
                edmod.set_param_hint('amp', value = 0, min=-1000, max = 1000)
                edmod.set_param_hint('dec', value = 1, min=0, max=1000)
                pars  = edmod.make_params()
                # Fit now
                fit = edmod.fit(ydata_fit, pars, x=xdata_fit, weights=1/ystderr_fit, verbose=False)
                # print fit.fit_report()

                # Pass the array of best fitted line
                self.gui.xdata_bf = self.time_array
                self.gui.ydata_bf = fit.best_fit

                # Get the values of the fitting
                self.yoff_est = fit.params['yoff'].value
                self.yoff_std = fit.params['yoff'].stderr
                self.amp_est = fit.params['amp'].value
                self.amp_std = fit.params['amp'].stderr
                self.dec_est = fit.params['dec'].value
                self.dec_std = fit.params['dec'].stderr

                self.ext_est = - self.amp_est / self.yoff_est
                self.ext_std = np.abs(self.ext_est * np.sqrt( (self.yoff_std/self.yoff_est)**2 + (self.amp_std/self.amp_est)**2 ))

                self.redchi = fit.redchi

            # <----------

        else:
            self.new_trigger_cases = 0

        # Timing: stop the stopwatch
        process_time = time.time() - startime_proc;
        self.process_time = process_time
        # print("Run time:"+ str(t) +"s")

    def updateParamGui(self):
        # About the triggering events
        new_trigger_case_ds = "New: " + str(self.new_trigger_cases) + " in " + '%.2f'%round(self.acquire_time,2) + " s"
        self.gui.new_trigger_cases_display.set(new_trigger_case_ds)
        total_trigger_case_ds = "Total: " + str(self.total_trigger_cases)
        self.gui.total_trigger_cases_display.set(total_trigger_case_ds)
        trigger_rate_ds = "Rate: " + '%.3f'%round(self.trigger_rate,3) + " tgs/s"
        self.gui.trigger_rate_display.set(trigger_rate_ds)
        process_time_ds = "PROCESS TIME: " + '%.3f'%round(self.process_time,3) + " s"
        self.gui.process_time_display.set(process_time_ds)

        # About the fitting
        redchi_ds = u"Reduced \u03c7 \u00b2 : " + '%.3f'%round(self.redchi,3)
        self.gui.redchi_display.set(redchi_ds)

        if self.ext_std > 1:    # If the standard deviation of ext is larger than 100% ~ result that does not make sense
            ext_ds = u"EXTINCTION: " + "undefined"
        else:  
            ext_ds = u"EXTINCTION: " + '%.2f'%round(self.ext_est*100,2) + u" \u00b1 " + '%.2f'%round(self.ext_std*100,2) + u" \u0025 "
        self.gui.ext_display.set(ext_ds)

        yoff_ds = u"Yoff: " + '%.3f'%round(self.yoff_est,3) + u" \u00b1 " + '%.3f'%round(self.yoff_std,3) + ' /ms'
        self.gui.yoff_display.set(yoff_ds)

        amp_ds = u"Amp: " + '%.3f'%round(self.amp_est,3) + u" \u00b1 " + '%.3f'%round(self.amp_std,3) + ' /ms'
        self.gui.amp_display.set(amp_ds)

        dec_ds = u"Dec: " + '%.3f'%round(self.dec_est,3) + u" \u00b1 " + '%.3f'%round(self.dec_std,3) + ' ms'
        self.gui.dec_display.set(dec_ds)

    def writeToFile(self):
        self.recdir = self.gui.recdir_entry.get()
        if not os.path.exists(self.recdir):
            os.makedirs(self.recdir)
        raw_array = np.vstack((self.time_array, self.data_array))
        np.savetxt(self.recdir+'/raw', raw_array, fmt='%.3e')
        plot_array = np.vstack((self.gui.xdata, self.gui.ydata, self.gui.ystderr))
        np.savetxt(self.recdir+'/plot', plot_array, fmt='%.3e')
        with open(self.recdir+'/fit', "w") as myfile:
            myfile.write('Total trigger :'+ '\t' + str(self.total_trigger_cases) + '\n' +
                         'Trigger rate :' + '\t' + '%.3f'%round(self.trigger_rate,3) + '\n' +
                         'FITTING RESULT' + '\n' +
                         'Yoff :' + '\t' + '\t' + '\t' + '%.3f'%round(self.yoff_est,3) + " pm " + '%.3f'%round(self.yoff_std,3) + '\n' +
                         'Amp :' + '\t' + '\t' + '\t' + '%.3f'%round(self.amp_est,3) + " pm " + '%.3f'%round(self.amp_std,3) + '\n' +
                         'Dec :' + '\t' + '\t' + '\t' + '%.3f'%round(self.dec_est,3) + " pm " + '%.3f'%round(self.dec_std,3) + '\n' +
                         'Red Chisq :' + '\t' + '\t' + '%.3f'%round(self.redchi,3) + '\n' +
                         'Ext :' + '\t' + '\t' + '\t' + '%.2f'%round(self.ext_est*100,2) +" pm " + '%.2f'%round(self.ext_std*100,2) + '\n' 
                         )
            
    def workerThread1_zmq(self):
        """
        This is where we handle the asynchronous I/O. For example, it may be
        a 'select(  )'. One important thing to remember is that the thread has
        to yield control pretty regularly, by select or otherwise.
        """
        task = 0
        # Not yet needed in this program
        while self.running:

            if task == 0: 

                try:
                    self.message = self.socket.recv()
                    print "Received message from the other side :", self.message      

                    try:
                        self.message_a, self.message_b = self.message.split(" ")
                    except:
                        print "MESSAGE ILL DEFINED"
                        # Tell Boss the message is ill defined
                        self.socket.send("Speak Properly")

                    # The reply if it does not satisfy anything below
                    self.message_back = "Whatdahell Boss"

                    try:
                    # A big try

                        if self.message_a == "Please":
                            # Dealing with shutdown
                            if self.message_b == "Annihilate":
                                self.message_back = "Okay Boss"
                                self.endApplication()

                        if self.message_a == "Check":
                            if self.message_b == "Trig":
                                if self.status == 1 or self.status == 2:
                                    trig = str(self.total_trigger_cases)
                                    self.message_back = 'Trig ' + trig
                                else:
                                    self.message_back = 'Not Started'
                            elif self.message_b == "Ext":
                                if self.status == 1 or self.status == 2:
                                    extX = '%.2f'%round(self.ext_est*100,2)
                                    extdX = '%.2f'%round(self.ext_std*100,2)
                                    self.message_back = 'Ext ' + extX + ' ' + extdX
                                else:
                                    self.message_back = 'Not Started'

                        if self.message_a == "Change":
                            if self.message_b == "State":
                                if self.gui.status_button['state'] == 'normal':
                                    task = 1    # Command to press the button once
                                    self.message_back = "Okay Boss"
                                else:
                                    self.message_back = "Unable Boss"

                        if self.message_a == "Restart":
                            if self.message_b == "Please":
                                if (self.gui.status == 0 or self.gui.status == 3 ) and self.gui.status_button['state'] == 'normal':
                                    task = 2    # Command to start the measurement
                                    self.message_back = "Okay Boss"
                                else:
                                    self.message_back = "Unable Boss"

                        if self.message_a == "Reset":
                            if self.message_b == "Please":
                                if self.gui.status == 1 and self.gui.status_button['state'] == 'normal':
                                    task = 3
                                    trig = str(self.total_trigger_cases)
                                    extX = '%.2f'%round(self.ext_est*100,2)
                                    extdX = '%.2f'%round(self.ext_std*100,2)  
                                    yoffX = '%.3f'%round(self.yoff_est,3)
                                    yoffdX = '%.3f'%round(self.yoff_std,3)
                                    decX = '%.3f'%round(self.dec_est,3) 
                                    decdX = '%.3f'%round(self.dec_std,3)                                
                                    self.message_back = "Okay Trig " + trig + " Ext " + extX + " " + extdX + " Yoff " + yoffX + " " + yoffdX + " Dec " + decX + " " + decdX 
                                else:
                                    self.message_back = "Unable Boss"

                        if self.message_a == "Resav":
                            folder = self.message_b
                            self.gui.recdir_entry.delete(0, Tkinter.END)
                            self.gui.recdir_entry.insert(0, folder)
                            if self.gui.status == 1 and self.gui.status_button['state'] == 'normal':
                                task = 4
                                trig = str(self.total_trigger_cases)
                                extX = '%.2f'%round(self.ext_est*100,2)
                                extdX = '%.2f'%round(self.ext_std*100,2)                                    
                                yoffX = '%.3f'%round(self.yoff_est,3)
                                yoffdX = '%.3f'%round(self.yoff_std,3)
                                decX = '%.3f'%round(self.dec_est,3) 
                                decdX = '%.3f'%round(self.dec_std,3)                                
                                self.message_back = "Okay Trig " + trig + " Ext " + extX + " " + extdX + " Yoff " + yoffX + " " + yoffdX + " Dec " + decX + " " + decdX 
                            else:
                                self.message_back = "Unable Boss"

                    except:
                    # The message is ill defined
                        self.message_back = "Speak Properly"

                    # Finally send the message back
                    self.socket.send(self.message_back)

                except:
                    print 'Some error is present. Master please check.'

            else:
                '''
                Task 1: Change state
                Task 2: Restart
                Task 3: Reset
                Task 4: Resav
                '''
                if task == 1:
                    if self.gui.status_button['state'] == 'normal':
                        self.gui.statusChange()
                    else:
                        print 'Inconsistent state. Dont do two things at the same time!!!'
                    task = 0    # Go back to listening mode
                elif task == 2:
                    if (self.gui.status == 0 or self.gui.status == 3 ) and self.gui.status_button['state'] == 'normal':
                        self.gui.statusChange()
                    else:
                        print 'Inconsistent state. Dont do two things at the same time!!!'
                    task = 0
                elif task == 3:
                    if self.gui.status == 1 and self.gui.status_button['state'] == 'normal':
                        self.gui.statusChange() # Press the first time
                        while True:
                            if self.gui.status_button['state'] == 'normal':
                                self.gui.statusChange() # Press the second time
                                break
                            time.sleep(0.1)    
                    else: 
                        print 'Inconsistent state. Dont do two things at the same time!!!'
                    task = 0
                elif task == 4:
                    if self.gui.status == 1 and self.gui.status_button['state'] == 'normal':
                        self.gui.statusChange() # Press the first time
                        while True:
                            if self.gui.rec_button['state'] == 'normal':
                                self.gui.recordData() # Press the record button
                                break
                            time.sleep(0.1)    
                        while True:
                            if self.gui.status_button['state'] == 'normal':
                                self.gui.statusChange() # Press the reset button
                                break
                            time.sleep(0.1)    
                    else: 
                        print 'Inconsistent state. Dont do two things at the same time!!!'
                    task = 0



    def endApplication(self):
        # Kill and wait for the processes to be killed
        if self.status != 0 and self.status != 3:
            print "The temp file is not cleared. If you want to start fresh next time, please clear it manually"
        self.running = 0
        time.sleep(0.1)


if __name__ == '__main__':

    root = Tkinter.Tk(  )
    root.title("Dinosaur Seeker Version 1.03 Branch 1 Pro")

    img = Tkinter.PhotoImage(file='icon_xtc.png')
    root.tk.call('wm', 'iconphoto', root._w, img)

    client = ThreadedClient(root)
    root.mainloop(  )
