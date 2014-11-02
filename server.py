import threading
import time
import os
import signal
import uuid
from tornado import gen, ioloop, web, websocket
from tornado.options import define, options, parse_command_line

define("port", default=8888, help="Run Socket Server on the given port", type=int)
BASEDIR = os.path.abspath(os.path.dirname(__file__))
MAX_WAIT = 5 #Seconds, before shutdown in signal
clients = dict() #List of all connections

class UpstreamThread(threading.Thread):
    def run(self):
        print 'Thread', self.getName(), 'started.'
        conc = 0
        for ii in range(1, 10):
            conc = conc + ii
            broadcast(str(conc))
            time.sleep(2)
        print 'Thread', self.getName(), 'ended.'

class DownstreamThread(threading.Thread):
    def run(self):
        print 'Thread', self.getName(), 'started.'
        conc = 0
        for ii in range(1, 10):
            conc = conc + ii
            print self.getName(), 'concentration: %d' % conc
            time.sleep(1)
        measureUpstream.join()
        print 'Thread', self.getName(), 'ended.'

def broadcast(message):
    """
    Pushes a message to all currently connected clients.
    Tests connection before hand just in case a disconnect
    has just occurred.
    """
    for ids, ws in clients.items():
        if not ws.ws_connection.stream.socket:
            del clients[ids]
        else:
            ws.write_message(message)
            
def sig_handler(sig, frame):
    """
    Calls shutdown on the next I/O Loop iteration. Should only be used from a signal handler, unsafe otherwise.
    """
    ioloop.IOLoop.instance().add_callback_from_signal(shutdown)

def shutdown():
    """
    Graceful shutdown of all services. Can be called with kill -2 for example, a CTRL+C keyboard interrupt, 
    or 'shutdown' from the debug console on the panel.
    """
    broadcast("Automation server is shutting down.")
    print "Shutting down Automation server (will wait up to %s seconds to complete running threads ...)" % MAX_WAIT
    
    instance = ioloop.IOLoop.instance()
    deadline = time.time() + MAX_WAIT
 
    def terminate():
        """
        Recursive method to wait for incomplete async callbacks and timeouts
        """
        now = time.time()
        if now < deadline and (instance._callbacks or instance._timeouts):
            instance.add_timeout(now + 1, terminate)
        else:
            instance.stop()
            print "Shutdown."
    terminate()
    
class IndexHandler(web.RequestHandler):
    """
    Serve up the panel
    """
    @web.asynchronous
    def get(self):
        self.render("index.html")

class WebSocketHandler(websocket.WebSocketHandler):
    """
    Descriptions of websocket interactions. What to do when connecting/disconnecting a client and how to handle a client message
    """
    def open(self):
        self.id = uuid.uuid4() #Give client a unique identifier. This may be changed to something more personal in the future if required.
        self.stream.set_nodelay(True)
        clients[self.id] = self
        print "New Client: %s" % (self.id)
        self.write_message("Connected to Automation Server")

    def on_message(self, message):        
        print "Message from Client %s: %s" % (self.id, message)
        
        commands = message.split("&") #complex commands will be of the form command&command&command
       
        #Most of these are now superfluous. Ultimately only Accept case is needed, but will keep them here until the production version.
        if (message == 'base'):
            self.write_message(u"Base Directory: " + BASEDIR)
        elif (message == 'upstream'):
            measureUpstream = UpstreamThread()
            measureUpstream.setName('Upstream')
            measureUpstream.start()
        elif (message == 'test'):
            broadcast('thh&nth')
        elif (message == 'shutdown'):
            self.write_message(u"Shutting down Automation Server...")
            ioloop.IOLoop.instance().add_callback(shutdown)
        elif (len(commands) > 1):
            #Incoming command (for now this is just ACK)
            if (commands[0] == 'Accept'):
                self.write_message(u"Accepted state: " + commands[1])
                #write_accept(commands[1] + '\n')
        else:
            self.write_message(u"Server echoed: " + message)
        
    def on_close(self):
        print "Client %s disconnected." % self.id
        if self.id in clients:
            del clients[self.id]
    
app = web.Application([
    (r'/', IndexHandler),
    (r'/websocket', WebSocketHandler),
    (r'/(favicon.ico)', web.StaticFileHandler, {'path': ''},),
    (r'/static/(.*)', web.StaticFileHandler, {'path': './static'},),
])

if __name__ == '__main__':
    #Set up server
    parse_command_line()
    app.listen(options.port)

    #Signal Register
    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)
    
    #Start the file watcher
    #ioloop.IOLoop.instance().add_callback(status_watcher)
    #Start the server main loop
    ioloop.IOLoop.instance().start()        
        
#tCPC12 = 3 #s
#measureUpstream = UpstreamThread()
#measureDownstream = DownstreamThread()
#measureUpstream.setName('Upstream')
#measureDownstream.setName('Downstream')

#measureUpstream.start()
#time.sleep(tCPC12)
#measureDownstream.start()