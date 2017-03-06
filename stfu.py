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

socket.send("Please Annihilate")
#  Get the reply.
message = socket.recv()
print "Received reply : ", message
