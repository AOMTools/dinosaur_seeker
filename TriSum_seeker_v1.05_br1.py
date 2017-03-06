"""
Created on Thurs Jan 15 2016
@author: Adrian Utama

Dinosaur Seeker v1.04 branch 1 ()
The GUI to monitor the averaged extinction of the atom based on a predefined trigger signal
1.01: Added functionality of fitting on the go and displaying some relevant values on the GUI. Also fixed some bugs, particularly concerning low trigger counts.
1.02: Added functionality to save the files, and to communicate with external program (using port 5558)
1.03: Added a temporary patch to switch off and on the power supply if the memory allocation for the driver fails (branch 1)
1.04: TeFiTi Pattern

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
MONITORING_WINDOW = 200        # Looking at the window of traces of 50 ms in length

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
        Tkinter.Label(self.frame2, font=("Helvetica", 12), text="FIT RESULT (T)", width=16, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
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
        Tkinter.Label(self.frame3, font=("Helvetica", 12), text="FIT PARAMS (T)", width=16, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame3, font=("Helvetica", 12), textvariable=self.yoff_display, width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame3, font=("Helvetica", 12), textvariable=self.amp_display, width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        Tkinter.Label(self.frame3, font=("Helvetica", 12), textvariable=self.dec_display, width=20, anchor=Tkinter.W).pack(side=Tkinter.LEFT, padx=5, pady=5)
        self.frame3.grid(row = 4, columnspan =10, sticky=Tkinter.W)

        # PLOTTING ADD ON--->
        # T
        self.Txdata = np.arange(0, MONITORING_WINDOW, 2)
        self.Tydata = np.array([1.] * len(self.Txdata))
        self.Txdata_bf = np.arange(0, MONITORING_WINDOW, 2)
        self.Tydata_bf = np.array([1.] * len(self.Txdata))
        self.Tystderr = np.array([0.] * len(self.Txdata))
        # F
        self.Fxdata = np.arange(0, MONITORING_WINDOW, 2)
        self.Fydata = np.array([1.] * len(self.Fxdata))
        self.Fystderr = np.array([0.] * len(self.Fxdata))
        # R
        self.Rxdata = np.arange(0, MONITORING_WINDOW, 2)
        self.Rydata = np.array([1.] * len(self.Rxdata))
        self.Rystderr = np.array([0.] * len(self.Rxdata))        

        self.figure = Figure(figsize=(10, 5))
        self.figure_subplot = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=root)
        self.canvas.get_tk_widget().grid(row =5, column = 1, columnspan = 8)

        # T
        self.Tline, (self.Tbottoms, self.Ttops), (self.Tverts,) = self.figure_subplot.errorbar(self.Txdata, self.Tydata, yerr = self.Tystderr, fmt = 'o', ls = '', markersize = 4, color = 'red')
        self.Tline_bf, = self.figure_subplot.plot(self.Txdata_bf, self.Tydata_bf, color = 'red')
        self.figure_subplot.grid()
        # F
        self.Fline, (self.Fbottoms, self.Ftops), (self.Fverts,) = self.figure_subplot.errorbar(self.Fxdata, self.Fydata, yerr = self.Fystderr, fmt = 'o', ls = '', markersize = 4, color = 'blue')
        # F
        self.Rline, (self.Rbottoms, self.Rtops), (self.Rverts,) = self.figure_subplot.errorbar(self.Rxdata, self.Rydata, yerr = self.Rystderr, fmt = 'o', ls = '', markersize = 4, color = 'green')


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
        # T
        self.Tline.set_xdata(self.Txdata)
        self.Tline.set_ydata(self.Tydata)
        Tyerr_top = self.Tydata - self.Tystderr
        Tyerr_bot = self.Tydata + self.Tystderr
        self.Tbottoms.set_ydata(Tyerr_bot)
        self.Ttops.set_ydata(Tyerr_top)
        self.Tbottoms.set_xdata(self.Txdata)
        self.Ttops.set_xdata(self.Txdata)
        # Magic code to get back the missing vertical line in the errorbars
        Tnew_segments_y = [np.array([[x, yt], [x,yb]]) for x, yt, yb in zip(self.Txdata, Tyerr_top, Tyerr_bot)]
        self.Tverts.set_segments(Tnew_segments_y)
        # F
        self.Fline.set_xdata(self.Fxdata)
        self.Fline.set_ydata(self.Fydata)
        Fyerr_top = self.Fydata - self.Fystderr
        Fyerr_bot = self.Fydata + self.Fystderr
        self.Fbottoms.set_ydata(Fyerr_bot)
        self.Ftops.set_ydata(Fyerr_top)
        self.Fbottoms.set_xdata(self.Fxdata)
        self.Ftops.set_xdata(self.Fxdata)
        # Magic code to get back the missing vertical line in the errorbars
        Fnew_segments_y = [np.array([[x, yt], [x,yb]]) for x, yt, yb in zip(self.Fxdata, Fyerr_top, Fyerr_bot)]
        self.Fverts.set_segments(Fnew_segments_y)
        # R
        self.Rline.set_xdata(self.Rxdata)
        self.Rline.set_ydata(self.Rydata)
        Ryerr_top = self.Rydata - self.Rystderr
        Ryerr_bot = self.Rydata + self.Rystderr
        self.Rbottoms.set_ydata(Ryerr_bot)
        self.Rtops.set_ydata(Ryerr_top)
        self.Rbottoms.set_xdata(self.Rxdata)
        self.Rtops.set_xdata(self.Rxdata)
        # Magic code to get back the missing vertical line in the errorbars
        Rnew_segments_y = [np.array([[x, yt], [x,yb]]) for x, yt, yb in zip(self.Rxdata, Ryerr_top, Ryerr_bot)]
        self.Rverts.set_segments(Rnew_segments_y)


        # Limits
        self.figure_subplot.set_xlim([-0.5, MONITORING_WINDOW + 2])
        self.figure_subplot.set_ylim([0, max(np.concatenate([self.Tydata, self.Fydata, self.Rydata]))*1.1])

        # For the best line (T)
        self.Tline_bf.set_xdata(self.Txdata_bf)
        self.Tline_bf.set_ydata(self.Tydata_bf)

        return self.Tline,

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
        # T
        self.gui.Txdata = np.arange(0, MONITORING_WINDOW, 2)
        self.gui.Tydata = np.array([1.] * len(self.gui.Txdata))
        self.gui.Txdata_bf = np.arange(0, MONITORING_WINDOW, 2)
        self.gui.Tydata_bf = np.array([1.] * len(self.gui.Txdata))
        self.gui.Tystderr = np.array([0.] * len(self.gui.Txdata))
        # F
        self.gui.Fxdata = np.arange(0, MONITORING_WINDOW, 2)
        self.gui.Fydata = np.array([1.] * len(self.gui.Fxdata))
        self.gui.Fystderr = np.array([0.] * len(self.gui.Fxdata))
        # R
        self.gui.Rxdata = np.arange(0, MONITORING_WINDOW, 2)
        self.gui.Rydata = np.array([1.] * len(self.gui.Rxdata))
        self.gui.Rystderr = np.array([0.] * len(self.gui.Rxdata))

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
        # Modified from the original program to work with TeFiTi pattern

        # Some parameters of the triggering
        datalength_time = MONITORING_WINDOW
        trig_header = 10
        lookup_header = 0.1     # look for the header: 10 triggers in less than 100 us

        # Conversion ratio (from timestamp to ms)
        convratio = 8 * 1000 * 1000

        # # For debugging
        # for values in loaddata:
        #     print np.binary_repr(values,64)

        # Some magic code to obtain the timing of the detection events. Each time bin in 125 ps
        time_array = np.uint64((loaddata << 32) >> 15) + np.uint64(loaddata >> 47)

        # Some magic code to obtain the channel of the detection events
        channel_array = np.uint8((loaddata >> 32) & 0xf)

        # ----- Procedures to find the appropriate triggering time -----

        trigsig_index = np.nonzero(channel_array & 0x2)     # Only looking at channel 2 for trigger signal
        lookup_headerts = lookup_header * convratio         # Amount of time to look up for trigger heads (converted to timestamp time)
        timetrig_array = time_array[trigsig_index]          # Obtain the array of times of a detected trigger signal

        blah = timetrig_array / convratio *1000

        # trigcheck_array contains the time difference (normalised to the lookup time) between the first and last trigger signal (determined by trigcounts)
        trighead_array = (timetrig_array[trig_header-1:] - timetrig_array[:-trig_header+1]) / lookup_headerts   # The plus/minus 1 is because you need to compare the events which are spaced trigcounts-1

        # If trigcheck_array is less than 1, that particular index is a successful start of the trigger signal
        trighead_array = np.floor(trighead_array)         # The values smaller than 1 will be round down to 0.

        # Extract out the index (row number) in the timestamp file that signifies the start of the trigger signal
        trighead_time_index = np.extract(trighead_array == 0, trigsig_index)
        trighead_time_array = time_array[trighead_time_index]

        if trighead_time_index.size > 0:
            # Cutting of trigger time index and trigger time array to select the time window we want to look at (Only cut if there is something... of course
            endtime = time_array[-1]
            starttime = convratio * 5           # Only trust trigger heads approx 5 ms into the processing block (safety + OCD reason)
            endtime = time_array[-1] - convratio * (datalength_time + 5)            # Only use trigger heads that starts earlier than [last timestamp point - monitoring window (+5ms for safety)]
            trighead_time_index = trighead_time_index[(trighead_time_array > starttime) & (trighead_time_array < endtime)]
            trighead_time_array = trighead_time_array[(trighead_time_array > starttime) & (trighead_time_array < endtime)]

        # print trighead_time_index

        # ----- ADDITION ----- : To handle no triggering case
        if trighead_time_index.size > 0:

            # ----- Procedures to create a 2 2D binned array of the binned counts for each T or F -----

            # Process the first triggered events. Step1: Obtain a data window. Cut from the trighead signal and trighead + datalength_time
            time_array_window = time_array[(time_array>=trighead_time_array[0]) & (time_array<trighead_time_array[0]+convratio*(datalength_time+5))]          # Add 5ms for safety
            channel_array_window = channel_array[(time_array>=trighead_time_array[0]) & (time_array<trighead_time_array[0]+convratio*(datalength_time+5))]    # Add 5ms for safety

            # Step 1: Specifying parameters
            jump_time = 0.05    # Jump 50 us from each switching trigger (eats 20us into trigger + 30us into data)
            tolook_time = time_array_window[0] + (jump_time + 0.020) * convratio  # First tolook_time: add 20us to trigger as the trigger head is 20us longer than other switching trigger

            # Step 3: Iterating through the monitoring time (manually) and counting events
            data_type1 = []     # F pattern
            time_type1 = []     # F startwindow
            data_type2 = []     # T pattern
            time_type2 = []     # T startwindow
            data_type3 = []     # R pattern

            process_type = 1    # Starts with F

            counter1 = 0     # Initialise counter (ch1 ts)
            counter3 = 0     # Initialise counter (ch3 ts)
            for t, c in np.nditer([time_array_window, channel_array_window]):
                if t > tolook_time:
                    if (c & 0x1) == 1:  # Ch1
                        counter1 = counter1 + 1
                    if (c & 0x4) == 1:  # Ch3
                        counter3 = counter3 + 1
                    if (c & 0x2) == 2:
                        if process_type == 1:
                            data_type1.append(counter1) # F pattern
                            time_type1.append(tolook_time)
                            process_type = 2
                        elif process_type == 2:
                            data_type2.append(counter1) # T pattern
                            data_type3.append(counter3) # R pattern
                            time_type2.append(tolook_time)
                            process_type = 1
                        counter1 = 0
                        counter3 = 0
                        tolook_time = t + jump_time * convratio
                else:
                    pass

            # Step 4: Convert to array (for easier process)
            init_time = time_type1[0]
            data_type1_comp = np.array(data_type1)
            time_type1 = np.array(time_type1) - init_time   # Set t = 0 at
            data_type2_comp = np.array(data_type2)
            time_type2 = np.array(time_type2) - init_time
            data_type3_comp = np.array(data_type3)

            # Step 5: Looping through the rest of the events
            for i in range(1, len(trighead_time_array)):

                # Step5a: Obtain the data windows. Cut from the trighead signal and trighead + datalength_time
                time_array_window = time_array[(time_array>=trighead_time_array[i]) & (time_array<trighead_time_array[i]+convratio*(datalength_time+5))]          # Add 5ms for safety
                channel_array_window = channel_array[(time_array>=trighead_time_array[i]) & (time_array<trighead_time_array[i]+convratio*(datalength_time+5))]    # Add 5ms for safety

                # Step 5b: Specifying parameters
                jump_time = 0.05    # Jump 50 us from each switching trigger (eats 20us into trigger + 30us into data)
                tolook_time = time_array_window[0] + (jump_time + 0.020) * convratio  # First tolook_time: add 20us to trigger as the trigger head is 20us longer than other switching trigger

                # Step 5c: Iterating through the monitoring time (manually) and counting events
                data_type1 = []     # F pattern
                # time_type1 = []
                data_type2 = []     # T pattern
                # time_type2 = []
                data_type3 = []     # R pattern

                process_type = 1

                counter1 = 0     # Initialise counter (ch1 ts)
                counter3 = 0     # Initialise counter (ch3 ts)
                for t, c in np.nditer([time_array_window, channel_array_window]):
                    if t > tolook_time:
                        if (c & 0x1) == 1:  # Ch1
                            counter1 = counter1 + 1
                        if (c & 0x4) == 1:  # Ch3
                            counter3 = counter3 + 1
                        if (c & 0x2) == 2:
                            if process_type == 1:
                                data_type1.append(counter1) # F pattern
                                # time_type1.append(tolook_time)
                                process_type = 2
                            elif process_type == 2:
                                data_type2.append(counter1) # T pattern
                                data_type3.append(counter3) # R pattern
                                # time_type2.append(tolook_time)
                                process_type = 1
                            counter1 = 0
                            counter3 = 0
                            tolook_time = t + jump_time * convratio
                    else:
                        pass

                # init_time = time_type1[0]
                # time_type1 = np.array(time_type1) - init_time
                # time_type2 = np.array(time_type2) - init_time

                #print np.array(data_type1), np.array(data_type1_comp)
                # Step 6: Append to existing array
                data_type1_comp = np.vstack((data_type1_comp, np.array(data_type1)))
                data_type2_comp = np.vstack((data_type2_comp, np.array(data_type2)))
                data_type3_comp = np.vstack((data_type3_comp, np.array(data_type3)))

            # Step 7 (almost forgotten): Convert time array back to ms units... he.. he.. he..
            time_type1 = time_type1/convratio
            time_type2 = time_type2/convratio

        # ------------------------------------------------------------- END ---------------------------------------------------------------- #

            # Now processing the obtained data and update the plot

            if self.trigger_firstdata == 0:
                # Virgin data
                self.data1_array = data_type1_comp
                self.time1_array = time_type1
                self.data2_array = data_type2_comp
                self.time2_array = time_type2
                self.data3_array = data_type3_comp
                self.trigger_firstdata = 1  # Use up the trigger
                # Get average of each timeblock
                self.time1_blockavg = np.average(self.time2_array - self.time1_array)
                self.time2_blockavg = np.average(self.time1_array[1:] - self.time2_array[:-1])  # Because didn't get the time of the last switching trigger
            else:
                self.data1_array = np.vstack((self.data1_array, data_type1_comp))
                self.data2_array = np.vstack((self.data2_array, data_type2_comp))
                self.data3_array = np.vstack((self.data3_array, data_type3_comp))

            # Calculating the averages and standard error
            self.data1_array_avg = np.average(self.data1_array, axis = 0)
            self.data1_array_sterr = np.std(self.data1_array, axis = 0) / np.sqrt(len(self.data1_array))
            self.data2_array_avg = np.average(self.data2_array, axis = 0)
            self.data2_array_sterr = np.std(self.data2_array, axis = 0) / np.sqrt(len(self.data2_array))
            self.data3_array_avg = np.average(self.data3_array, axis = 0)
            self.data3_array_sterr = np.std(self.data3_array, axis = 0) / np.sqrt(len(self.data3_array))

            # Getting all the relevant GUI parameters
            if trighead_time_index.size == 1:
                # Handling the cases that there is only one entry (trigger case), as the "length" of the array will automatically be the number of data points.
                self.new_trigger_cases = 1
                self.total_trigger_cases += 1
            else:
                self.new_trigger_cases = len(data_type1_comp)
                self.total_trigger_cases = len(self.data1_array)
            time_elapsed = trighead_time_array[-1]/(convratio*1000)  # Convert time elapsed to s (from the start of ts to the last trigger signal)
            self.trigger_rate = self.total_trigger_cases / time_elapsed

            # ----------> PROCEDURE TO PLOT AND DO THE FITTING ON THE DATA
            if self.total_trigger_cases >= 5:
                # Need at least 3 traces (such that the plotting and fitting can make sense >> blame ystderr). Turns out that we probably need more than 3 (for whatever wierd reasons). Let me just set to 5.

                # Getting to the plotting program

                # For transmission (data2)
                self.gui.Txdata = self.time2_array
                self.gui.Tydata = self.data2_array_avg / (self.time2_blockavg - jump_time)         # Need to divide by data_timebin to get the rate per ms
                self.gui.Tystderr = self.data2_array_sterr / (self.time2_blockavg - jump_time)     # Need to divide by data_timebin to get the rate per ms

                # For fluorescence (data1)
                self.gui.Fxdata = self.time1_array
                self.gui.Fydata = self.data1_array_avg / (self.time1_blockavg - jump_time)         # Need to divide by data_timebin to get the rate per ms
                self.gui.Fystderr = self.data1_array_sterr / (self.time1_blockavg - jump_time)     # Need to divide by data_timebin to get the rate per ms

                # For reflection (data3)
                self.gui.Rxdata = self.time2_array
                self.gui.Rydata = self.data3_array_avg / (self.time2_blockavg - jump_time)         # Need to divide by data_timebin to get the rate per ms
                self.gui.Rystderr = self.data3_array_sterr / (self.time2_blockavg - jump_time)     # Need to divide by data_timebin to get the rate per ms

                # Creating and fitting to the exponentialmodel (only for T)
                edmod = Model(exp_decay)
                xdata_fit = self.gui.Txdata
                ydata_fit = self.gui.Tydata
                ystderr_fit = self.gui.Tystderr
                # Set parameter hints
                edmod.set_param_hint('yoff', value = 1, min=0)
                edmod.set_param_hint('amp', value = 0, min=-1000, max = 1000)
                edmod.set_param_hint('dec', value = 1, min=0, max=1000)
                pars  = edmod.make_params()
                # Fit now
                fit = edmod.fit(ydata_fit, pars, x=xdata_fit, weights=1/ystderr_fit, verbose=False)
                # print fit.fit_report()

                # Pass the array of best fitted line
                self.gui.Txdata_bf = self.time2_array
                self.gui.Tydata_bf = fit.best_fit

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

        # F: data 1
        Fraw_array = np.vstack((self.time1_array, self.data1_array))
        np.savetxt(self.recdir+'/raw_F', Fraw_array, fmt='%.3e')
        Fplot_array = np.vstack((self.gui.Fxdata, self.gui.Fydata, self.gui.Fystderr))
        np.savetxt(self.recdir+'/plot_F', Fplot_array, fmt='%.3e')
        # T : data 2
        Traw_array = np.vstack((self.time2_array, self.data2_array))
        np.savetxt(self.recdir+'/raw_T', Traw_array, fmt='%.3e')
        Tplot_array = np.vstack((self.gui.Txdata, self.gui.Tydata, self.gui.Tystderr))
        np.savetxt(self.recdir+'/plot_T', Tplot_array, fmt='%.3e')
        # R : data 3
        Rraw_array = np.vstack((self.time2_array, self.data3_array))    # Time 2 array cause the same window with T
        np.savetxt(self.recdir+'/raw_R', Rraw_array, fmt='%.3e')
        Rplot_array = np.vstack((self.gui.Rdata, self.gui.Rydata, self.gui.Rystderr))
        np.savetxt(self.recdir+'/plot_R', Rplot_array, fmt='%.3e')


        # Fit (only applies for T)
        with open(self.recdir+'/fit_T', "w") as myfile:
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
    root.title("TriSum Seeker Version 1.05 Branch 1 Pro")

    img = Tkinter.PhotoImage(file='icon_3s.png')
    root.tk.call('wm', 'iconphoto', root._w, img)

    client = ThreadedClient(root)
    root.mainloop(  )
