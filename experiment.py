# -*- coding: utf-8 -*-
import time
import serial
from threading import Thread, Event
import numpy as np
from datetime import datetime
import logging
import re
import sys
import csv
import json

logging.basicConfig(level=logging.DEBUG,
                    format='[%(levelname)s] (%(threadName)-10s) %(message)s',
                    )

class SerialControl(Thread):
    def __init__(self, machine, connection, start, stop):
        """ Constructor. """
        Thread.__init__(self)
        self.setDaemon(True)
        self.async = Event()
        self.work = 1
        self.result = []
        self.sample = []
        self.startCommand = start
        self.stopCommand = stop
        self.setName(machine)
        self.io = connection

    def run(self):
        logging.debug('Thread %s' % (self.getName()))
        self.io.isOpen()
        self.io.flushInput()
        self.io.flushOutput()
        while 1:
            if self.async.isSet():
                self.async.clear()
                self.work = 1
                self.asyncCommand()

    def reset(self):
        self.work = 1
        self.result = []
        self.sample = []
        self.io.flushOutput()

    def disconnect(self):
        self.io.close()

    def command(self,command):
        """
        Sends a syncronous serial command and prints the response
        Sholudn't be used for ALC, call getPressure for that
        """
        self.io.write(bytearray(command + '\r\n','ascii'))
        out = ''
        time.sleep(0.1)
        while self.io.inWaiting() > 0:
            out += bytes.decode(self.io.read(1))
        if out != '':
            logging.debug('%s>> %s [%s]' % (self.getName(), command, out.rstrip()))

    def commandR(self,command):
        """
        Sends a syncronous serial command and returns the response
        Sholudn't be used for ALC, call getPressure for that
        """
        self.io.write(bytearray(command + '\r\n','ascii'))
        out = ''
        time.sleep(0.1)
        while self.io.inWaiting() > 0:
            out += bytes.decode(self.io.read(1))
        if out != '':
            logging.debug('%s>> %s [%s]' % (self.getName(), command, out.rstrip()))
        return out

    def asyncCommand(self):
        """
        Sends and asynchronous command, returning response
        """
        self.io.flushOutput()
        self.io.write(bytearray(self.startCommand + '\r\n','ascii'))
        self.result = []
        time.sleep(0.3)
        out = ''
        while self.io.inWaiting() > 0:
            out += bytes.decode(self.io.read(1))
        logging.debug('Async %s command %s [%s]' % (self.getName(), self.startCommand, out.rstrip()))
        #TODO: Actually check for OK message before running
        for x in range(0,NOR*tReading):
            time.sleep(tMeasure)
            out = ''
            while self.io.inWaiting() > 0:
                out += bytes.decode(self.io.read(1))
            data = out.rstrip().split(',')
            self.result.append(data)
            if len(self.result) == tReading:
                self.doStats()
            #logging.debug('[%s]' % ', '.join(map(str, data)))

        self.command(self.stopCommand)
        self.work = 0
        time.sleep(0.1)
        self.io.flushOutput()

    def isReady(self,cmd,rpl):
        #Send Command cmd until Reply rpl is recieved
        out = ''
        while out.rstrip() != rpl:
            self.io.write(bytearray(cmd + '\r\n','ascii'))
            out = ''
            time.sleep(1)
            while self.io.inWaiting() > 0:
                out += bytes.decode(self.io.read(1))

    def getPressure(self):
        if self.getName() == 'ALC':
            self.io.write(bytearray('V\r\n','ascii'))
            out = ''
            time.sleep(0.1)
            while self.io.inWaiting() > 0:
                out += bytes.decode(self.io.read(1),'latin1')
            if out != '':
                press = re.search(r"[-+]?[0-9]*\.?[0-9]+(?= Pa)", out)
                rh = re.search(r"[-+]?[0-9]*\.?[0-9]+(?= %rh)", out)
                T = re.search(ur"[-+]?[0-9]*\.?[0-9]+(?= \u00B0C)", out, re.UNICODE)
                if press:
                    self.sample.append([abs(float(press.group(0))), float(rh.group(0)), float(T.group(0))])
                    logging.debug(u'%s>> V [%s Pa, %s %%rh, %s \u00B0C]' % (self.getName(), press.group(0), rh.group(0), T.group(0)))

    def doStats(self):
        #This one can't be general. Has to be different for each instrument. For now {W,B}CPC
        #Put results in a temp variable and clear the main structure for the next reading
        results = self.result
        self.result = []
        name = self.getName()
        conc = []
        count = []
        if name == 'WCPC':
            for data in results:
                conc.append(float(data[3]))
                count.append(float(data[6]))
            ALC.getPressure() #Call pressure log.
        elif name == 'BCPC':
            for data in results:
                conc.append(np.mean(map(float,data[1:10])))
                count.append(np.sum(map(float,data[11:20])))

        reading = [min(conc), max(conc), np.mean(conc), np.std(conc), np.sum(count)]
        self.sample.append(reading)
        logging.debug('Conc min:%.2f,max:%.2f,mean:%.2f,std:%.2f. Count %.2f.' % (reading[0], reading[1], reading[2], reading[3], reading[4]))

    def getJobStats(self):
        #Pulls mean and std for current job
        means = []
        mins = []
        maxs = []
        count = 0
        for reading in self.sample:
            means.append(reading[2])
            mins.append(reading[0])
            maxs.append(reading[1])
            count += reading[3]
        return [np.mean(means), np.std(means), min(mins), max(maxs), count]

class JobResults:
    def __init__(self):
        """ Constructor. """
        self.reset()

    def reset(self):
        self.tStart =''
        self.tStop =''
        self.faceVel = 0
        self.partSize = 0
        self.upConc = []
        self.downConc = []
        self.penetration = []
        self.pressure = [] #Pa
        self.rh = [] #%
        self.temperature = [] #ºC

    def printStats(self):
        penmean = np.mean(self.penetration)
        penstd = np.std(self.penetration)
        penserr = penstd/penmean
        fom = -np.log(penmean)/np.mean(self.pressure)
        fomerr = penserr*fom
        logging.debug('Statistics for Job')
        logging.debug(u'Average Pressure: %.2f Pa, Average Tempurature: %.2f \u00B0C, Average RH: %.2f %%' % (np.mean(self.pressure), np.mean(self.temperature),np.mean(self.rh)))
        logging.debug('Penetration Mean: %.2f, Standard Deviation: %.2f, SErr: %.2f' % (penmean,penstd,penserr))
        logging.debug('Figure of Merit: %.2f 1/kPa, Err: %.2f' % (fom,fomerr))

    def writeToDisk(self):
        """
        Write data to a CSV file
        """
        umu = []
        #usig = []
        umin = []
        umax = []
        ucount = 0
        for row in self.upConc:
            umu.append(row[0])
            #usig.append(row[1])
            umin.append(row[2])
            umax.append(row[3])
            ucount += row[4]
        dmu = []
        #dsig = []
        dmin = []
        dmax = []
        dcount = 0
        for row in self.downConc:
            dmu.append(row[0])
            #dsig.append(row[1])
            dmin.append(row[2])
            dmax.append(row[3])
            dcount += row[4]

        ucounterr = np.sqrt(ucount)
        dcounterr = np.sqrt(dcount)
        pencnt = dcount/ucount
        feu = ucounterr/ucount #Fractional error
        fed = dcounterr/dcount
        pencnterr = pencnt*np.sqrt(feu*feu+fed*fed)
        fomcnt = -np.log(pencnt)/np.mean(self.pressure)
        fomcnterr = pencnterr*fomcnt
        penmean = np.mean(self.penetration)
        penstd = np.std(self.penetration)
        penserr = penstd/penmean
        fom = -np.log(penmean)/np.mean(self.pressure)
        fomerr = penserr*fom

        writer = csv.writer(csv_file, delimiter=',')
        writer.writerow(['Start Time', self.tStart])
        writer.writerow(['Stop Time', self.tStop])
        writer.writerow(['Aerosol Challenge', 'NaCl'])
        writer.writerow(['Swatch Material', 'PAN'])
        if self.partSize == 0:
            writer.writerow(['Aerosol Modality', 'Polydisperse'])
        else:
            writer.writerow(['Aerosol Modality', 'Monodisperse'])
        if sampleMode == 0:
            writer.writerow(['Sampling Mode', 'Concentration'])
        else:
            writer.writerow(['Sampling Mode', 'Count'])
        writer.writerow(['Measurement Time (s)', tMeasure])
        writer.writerow(['Reading Time (s)', tReading])
        writer.writerow(['Sample Time (s)', tSample])
        writer.writerow(['Up/Down Delay (s)', tCPCDelay])
        writer.writerow(['Num Samples', NOS])
        writer.writerow(['Num Readings', NOR])
        writer.writerow(['Face Velovity (cm/s)', self.faceVel])
        if self.partSize == 0:
            writer.writerow(['Particle Size', 'Polydisperse'])
        else:
            writer.writerow(['Particle Size', self.partSize])
        writer.writerow(['Swatch Inline', 'No'])
        writer.writerow(['Temperature (avg) C', np.mean(self.temperature)])
        writer.writerow(['Rel. Humidity (avg) %', np.mean(self.rh)])
        writer.writerow(['Total Upstream Particle Count (pm Err)', ucount, ucounterr])
        writer.writerow(['Total Downstream Particle Count (pm Err)', dcount, dcounterr])
        writer.writerow(['Value', 'Mean', 'Sigma', 'Min', 'Max'])
        writer.writerow(['Pressure Drop (Pa)', np.mean(self.pressure), np.std(self.pressure), min(self.pressure), max(self.pressure)])
        writer.writerow(['Upstream Concentration (#/cm^3)', np.mean(umu), np.std(umu), min(umin), max(umax)])
        writer.writerow(['Downstream Concentration (#/cm^3)', np.mean(dmu), np.std(dmu), min(dmin), max(dmax)])
        writer.writerow(['Penetration (count)', pencnt, pencnterr, '-', '-'])
        writer.writerow(['F.O.M. (count)', fomcnt, fomcnterr, '-', '-'])
        writer.writerow(['Penetration (conc)', penmean, penstd, min(self.penetration), max(self.penetration)])
        writer.writerow(['F.O.M. (conc)', fom, fomerr, '-', '-'])
        if runType == 1:
            p100 = dict(zip(map(str,faceVel),self.penetration))
            writeP100()
        else:
            writer.writerow(['Swatch Penetration (conc)', penmean/p100[str(self.faceVel)], '-', '-', '-'])


def setBWCPCFlowRate(flowRate):
    if flowRate == '0.3':
        return 'X7'
    else:
        return 'X8'

def rampFlow(new):
    res = SDPROC.commandR('SD')
    #1=   0.6%I  #2=   1.1%I  #3=   0.2%I
    cur = re.findall(r'([-+]?[0-9]*\.?[0-9]+)(?=%I)', res) #now [0] is one, [1] is two
    num = 10
    old = float(cur[0])
    step = abs(old - new)/num
    while num > 0:
        if old > new:
            old = old - step
        else:
            old = old + step
        num = num-1
        SDPROC.command('SP 1 %.2f' % old)
        time.sleep(1)

def getP100():
    with open('P100.json', 'r') as p100_read:
        data = json.load(p100_read)
        return data

def writeP100():
    with open('P100.json', 'wb') as p100_write:
        json.dump(p100, p100_write)

def printSampleStats(up,down,sample,FV):
    #Prints sample statistics. Up and Down come from WCPC and BCPC, first value is mean, second is std
    serrup = up[1]/up[0]
    serrdown = down[1]/down[0]
    pen = down[0]/up[0]
    jobResults.penetration.append(pen)
    pr = []
    rh = []
    te = []
    for row in ALC.sample:
        pr.append(row[0])
        rh.append(row[1])
        te.append(row[2])
    pressmean = np.mean(pr)
    jobResults.pressure.append(pressmean)
    jobResults.temperature.append(np.mean(te))
    jobResults.rh.append(np.mean(rh))
    jobResults.upConc.append(up)
    jobResults.downConc.append(down)
    logging.debug('Statistics for Sample %d' % s)
    logging.debug('Face Velocity: %d cm/s, Make Up Flow: %.2f lpm' % (faceVel[FV], makeUpAir[FV]))
    logging.debug('Upstream Mean Concentration: %.2f #/cm^3, Standard Deviation: %.2f, SErr: %.2f' % (up[0], up[1], serrup))
    logging.debug('Downstream Mean Concentration: %.2f #/cm^3, Standard Deviation: %.2f, SErr: %.2f' % (down[0], down[1], serrdown))
    logging.debug('Penetration: %.2f' % (pen))
    logging.debug('Pressure Drop Mean: %.2f, Standard Deviation: %.2f, Min: %.2f, Max: %.2f' % (pressmean, np.std(pr), min(pr), max(pr)))
    #if serrup > 0.3 or serrdown > 0.3:
        #sys.exit('Standard error of sample too large. Aborting. (Up: %.2f, Down: %.2f)' % (serrup,serrdown))

"""
These are values that will be set by the user in the future
"""
tMeasure = 1 #s
tReading = 3 #s
tSample = 9 #s should be 30
tCPCDelay = 3 #s
tWaitSample = 3 #s
tEQ = 10 #s Should be 30, but 1 for testing
faceVel = [5.0,10.0]#[1.0,3.0,5.0,10.0] #cm/s
makeUpAir = [2.27, 6.04]#[0.45, 0.76, 2.27, 6.04] #lpm
BCPCFlowRate = [1.5, 1.5]#[0.3, 1.5, 1.5, 1.5] #lpm
partSize = [0]#np.logspace(2,3,2)/2
NOS = 3 #Number of samples per job
NOR = tSample/tReading #Number of readings per sample
sampleMode = 0 #0 = conc, 1 = count
runType = 0 #0 for swatch, 1 for P100
p100 = None
if __name__ == '__main__':
    threads = []

    if len(sys.argv) > 1:
        # Get the arguments list
        if sys.argv[1]=='-P100':
            logging.debug('This is a P100% Calibration Run')
            runType = 1

    if runType == 0:
        logging.debug('Reading P100% parameters from file')
        p100 = getP100()

    # Declare objects of SerialControl class
    #WCPC 3782
    WCPC = SerialControl('WCPC',serial.Serial(
        port='COM14',
        baudrate=115200,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS
    ),'SM,2,10','SM,0')
    threads.append(WCPC)
    #BCPC 3775
    BCPC = SerialControl('BCPC',serial.Serial(
        port='COM11',
        baudrate=115200,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS
    ),'SSTART,2','SSTART,0')
    threads.append(BCPC)
    #Pressure ALC8710, only command is "V" needs latin1
    ALC = SerialControl('ALC',serial.Serial(
        port='COM12',
        baudrate=9600,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS
    ),'','') #No async needed
    threads.append(ALC)
    #SDPROC Command Module
    SDPROC = SerialControl('SDPROC',serial.Serial(
        port='COM13',
        baudrate=9600,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_TWO,
        bytesize=serial.EIGHTBITS
    ),'','') #No async needed
    threads.append(SDPROC)
    #EC 3080
    EC = SerialControl('EC',serial.Serial(
        port='COM22',
        baudrate=9600,
        parity=serial.PARITY_EVEN,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.SEVENBITS
    ),'','') #No async needed
    threads.append(EC)

    #Start running the threads
    WCPC.start()
    BCPC.start()
    ALC.start()
    SDPROC.start()
    EC.start()

    #Create results container
    jobResults = JobResults()


    logging.debug('Starting EC')
    EC.command('SFMS')
    EC.command('SQB0')
    EC.command('SQS3.0')

    logging.debug('Starting WCPC')
    WCPC.command('SM,0')
    WCPC.command('SL,1')
    WCPC.command('SP,1')

    logging.debug('Starting BCPC')
    BCPC.command('SCM,0')
    BCPC.command('X3')

    logging.debug('Starting Flow Meters')
    SDPROC.command('VM 1 1')
    SDPROC.command('VM 2 0') #Close valve
    SDPROC.command('FF 1 10.0') #Meter 1 maximum of 5 lpm
    SDPROC.command('FF 2 30.0') #Meter 2 maximum of 30 lpm - currently controls make up air TODO: Fix this assumption
    with open('output.csv', 'wb') as csv_file:
        for fvidx in range(0, len(faceVel)):
            fv = faceVel[fvidx] #Current face velocity
            mua = makeUpAir[fvidx] #Current make up air
            bfr = BCPCFlowRate[fvidx] #BCPC Flow rate

            jobResults.faceVel = fv

            logging.debug('')
            logging.debug('')
            #Set flow rates
            logging.debug('Setting Flow Rates. BCPC: %.2f lpm, Make up air: %.2f lpm' % (bfr,mua))
            BCPC.command(setBWCPCFlowRate(bfr))
            fs = ((mua/10)*100) #using the 10 lpm meter
            rampFlow(fs)

            logging.debug('Waiting for equilibrium conditions (%d seconds)' % (tEQ))
            time.sleep(tEQ)

            #Wait for BCPC to warm up
            BCPC.isReady('R5','READY')
            jobResults.tStart = datetime.now()
            #Particle size loop
            for particle in partSize:
                jobResults.partSize = particle
                if particle == 0:
                    logging.debug('Polydisperse Particles')
                else:
                    logging.debug('Particle size: %.2f' % particle)
                    EC.command('SPD%.2f' % particle)

                logging.debug('Starting Job. Face Velocity: %d cm/s, %d Samples' % (fv, NOS))
                for s in range(1, NOS+1):
                    logging.debug('Sample %d' % s)
                    #Start logging
                    WCPC.async.set()
                    time.sleep(2)
                    BCPC.async.set()

                    while WCPC.work == 1 or BCPC.work == 1:
                        #Spool main thread until async work is done
                        time.sleep(1)

                    printSampleStats(WCPC.getJobStats(), BCPC.getJobStats(),s,fvidx)
                    #Reset For new sampling run
                    WCPC.reset()
                    BCPC.reset()
                    ALC.reset()
                    time.sleep(tWaitSample)

                jobResults.tStop = datetime.now()
                jobResults.writeToDisk()
                jobResults.printStats()
                jobResults.reset()

    logging.debug('Shutting down WCPC')
    rampFlow(0)
    time.sleep(1)
    SDPROC.command('VM 1 0') #Close Valve
    time.sleep(1)
    WCPC.command('SM,0')
    WCPC.command('SL,0')
    WCPC.command('SP,0')

    logging.debug('Shutting down BCPC')
    BCPC.command('SSTART,0')
    BCPC.command('X2')

    logging.debug('Shutting down EC')
    EC.command('SQS0')

    WCPC.disconnect()
    BCPC.disconnect()

    print('Mission Completed...')
