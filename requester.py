''' 
PROTOCOL TO COMMUNICATE WITH THE DINOSAUR SEEKER
The command is given in two words, but the reply can be in a few words, depending on context.
Please respect this convention, as ill-defined messages will get burned into hell.

List of commands:
- Please Annihilate
    List of reply: "Okay Boss"
- Check Trig
    List of reply: "Trig X", "Not Started"
- Check Ext
    List of reply: "Ext Y dY", "Not Started"
- Reset Please
    List of reply: "Okay Trig X Ext Y dY Yoff Z dZ Dec A dA", "Unable Boss"
- Resav /home/...
    List of reply: "Okay Trig X Ext Y dY Yoff Z dZ Dec A dA", "Unable Boss"
- Restart Please
    List of reply: "Okay Boss", "Unable Boss"
- Change State
    List of reply: "Okay Boss", "Unable Boss"
'''


import zmq
import time

context = zmq.Context()

#  Socket to talk to server
print "Connecting to the retreat controller server"
socket = context.socket(zmq.REQ)
socket.connect("tcp://localhost:5558")

i = 0
while i < 100:
    i += 1
    print "Trying...", i

    while True:
        socket.send("Restart Please")
        time.sleep(0.1)
        #  Get the reply.
        message = socket.recv()
        print "Received reply : ", message
        if message!="Unable Boss":
	    time.sleep(0.5)
            break

    while True:
        socket.send("Check Trig")
        time.sleep(0.1)
        #  Get the reply.
	try:
    	    message = socket.recv()
	    m = message.split()
    	    trig_num = int(m[1])
	    if trig_num > 10:
	        print 'Enough trigger cases'
	        break
	except:
	    pass

    while True:
    	send = "Reset " + "/home/qitlab/programs/dinosaur_seeker/data/try" + str(i)
	send = "Reset " + "Please"
        socket.send(send)
        time.sleep(0.1)
        #  Get the reply.
        message = socket.recv()
        print "Received reply : ", message
        if message!="Unable Boss":
            break

time.sleep(5)
socket.send("Please Annihilate")
#  Get the reply.
message = socket.recv()
print "Received reply : ", message
