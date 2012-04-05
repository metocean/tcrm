#!/usr/bin/env python
"""
    Tropical Cyclone Risk Model (TCRM) - Version 1.0 (beta release)
    Copyright (C) 2011 Commonwealth of Australia (Geoscience Australia)

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

 Title: interpTrack.py
 Author: Craig Arthur, craig.arthur@ga.gov.au
 CreationDate: 2007-10-25 9:51:AM
 Description: Interpolates an historic TC track to a shorter time
 interval.  As an example, the csv data for TC Tracy is included in at
 the bottom of this file.

 Version :$Rev: 685 $

 ModifiedBy: Nicholas Summons
 ModifiedDate: 2011-02-08
 Modification: Replaced lat/lon interpolation with different spline
               algorithm that exhibits less overshoot.
               Pressure and Rmax interpolation was replaced with linear
               interpolation.

 $Id: interpTrack.py 685 2012-03-29 04:22:32Z carthur $
"""
import os, sys, pdb, logging, getopt

import scipy.interpolate
import numpy
import datetime
from matplotlib.dates import date2num, num2date

from files import flConfigFile, flModuleName, flSaveFile, flStartLog
from config import cnfGetIniValue, logger
from columns import colReadCSV
from grid import SampleGrid
from loadData import loadTrackFile


import maputils
import metutils

__version__ = '$Id: interpTrack.py 685 2012-03-29 04:22:32Z carthur $'

def usage():
    print "interpTrack.py:"
    print "Interpolate the observed points of a tropical cyclone temporally"
    print "for use in modelling a scenario event in TCRM"
    print "Example usage:"
    print "interpTrack.py -c <config file> -l <log file> -v"
    print ""
    print "Options:"
    print "-h, --help:   prints this help message"
    print "-c, --config: configuration path (default value is interpTrack.ini)"
    print "-l --logfile: path to log file to record actions (default value is interpTrack.log)"
    print "-v --verbose: True|False - print all logging messages to the screen"
    print ""
    print "Created by Craig Arthur, 2007-10-25 9:51:AM"
    print __version__

def main(argv):
    "Main part of the program"
    gConfigFile = flConfigFile()
    logFile = flConfigFile(".log")
    verbose = False
    logger = logging.getLogger()

    try:
        opts, args = getopt.getopt(argv,"hc:l:v",["help","config=","logfile=","verbose",])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    for opt,arg in opts:
        if opt in ("-h","--help"):
            usage()
            sys.exit(2)
        elif opt in ("-c", "--config"):
            gConfigFile = arg
        elif opt in ("-l","--logfile"):
            logFile = arg
        elif opt in ("-v","--verbose"):
            verbose = True

    flStartLog(cnfGetIniValue(gConfigFile, 'Logging', 'LogFile', flConfigFile('.log')),
               cnfGetIniValue(gConfigFile, 'Logging', 'LogLevel', 'INFO'),
               cnfGetIniValue(gConfigFile, 'Logging', 'Verbose', False))


    inputFile = cnfGetIniValue(gConfigFile, 'Input', 'File')
    logger.info("Processing %s"%inputFile)
    source = cnfGetIniValue(gConfigFile, 'Input', 'Source')
    delta = cnfGetIniValue(gConfigFile, 'Output', 'Delta', 0.1)

    nid, newtime, newdates, nLon, nLat, nthetaFm, nvFm, npCentre, npEnv, nrMax = interpolateTrack(gConfigFile,inputFile,source,delta)
    header=''
    outputFile = cnfGetIniValue(gConfigFile,'Output','File')
    logger.info("Saving interpolated data to %s"%(outputFile))
    fh = open(outputFile,'w')
    for i in xrange(len(newtime)):
        fh.write("%d,%5.1f,%s,%6.2f,%6.2f,%6.2f,%6.2f,%7.2f,%7.2f,%5.1f\n"
                    % (nid[i], newtime[i], newdates[i].strftime("%Y-%m-%d %H:%M"),
                        nLon[i], nLat[i], nthetaFm[i], nvFm[i], npCentre[i],
                        npEnv[i], nrMax[i]) )
    fh.close()
    logger.info("Completed %s"%(sys.argv[0]))

def interpolateTrack(configFile,trackFile,source,delta=0.1,interpolation_type=None):
    """
    interpTrack:
    interpolate the data in a track file to the time interval delta hours
    """
    logger = logging.getLogger()
    indicator,year,month,day,hour,minute,lon,lat,pressure,speed,bearing,windspeed,rmax,penv = loadTrackFile(configFile,trackFile,source)

    # Time between observations:
    day_ = [datetime.datetime(year[i], month[i], day[i], hour[i],minute[i]) for i in xrange(year.size)]
    time_ = date2num(day_)
    dt_ = 24.0*numpy.diff(time_)
    dt = numpy.empty(hour.size, 'f')
    dt[1:] = dt_

    # At this stage, convert all times to a time after initial observation:
    timestep = 24.0*(time_ - time_[0])

    newtime = numpy.arange(timestep[0], timestep[-1]+.01, delta)
    newtime[-1] = timestep[-1]
    _newtime = (newtime/24.) + time_[0]
    newdates = num2date(_newtime)

    nid = numpy.ones(newtime.size)

    logger.info("Interpolating data...")
    if len( indicator ) <= 2:
        # Use linear interpolation only (only a start and end point given):
        nLon = scipy.interpolate.interp1d(timestep, lon, kind='linear')(newtime)
        nLat = scipy.interpolate.interp1d(timestep, lat, kind='linear')(newtime)
        npCentre = scipy.interpolate.interp1d(timestep, pressure, kind='linear')(newtime)
        npEnv = scipy.interpolate.interp1d(timestep, penv, kind='linear')(newtime)
        nrMax = scipy.interpolate.interp1d(timestep, rmax, kind='linear')(newtime)

    else:
        if interpolation_type=='akima':
            # Use the Akima interpolation method:
            try:
                import _akima
            except ImportError:
                logger.exception("Akima interpolation module unavailable - default to scipy.interpolate")
                nLon = scipy.interpolate.splev(newtime, scipy.interpolate.splrep(timestep, lon, s=0), der=0)
                nLat = scipy.interpolate.splev(newtime, scipy.interpolate.splrep(timestep, lat, s=0), der=0)
            else:
                nLon = _akima.interpolate(timestep,lon,newtime)
                nLat = _akima.interpolate(timestep,lat,newtime)
        elif interpolation_type=='linear':
            nLon = scipy.interpolate.interp1d(timestep, lon, kind='linear')(newtime)
            nLat = scipy.interpolate.interp1d(timestep, lat, kind='linear')(newtime)
        else:
            nLon = scipy.interpolate.splev(newtime, scipy.interpolate.splrep(timestep, lon, s=0), der=0)
            nLat = scipy.interpolate.splev(newtime, scipy.interpolate.splrep(timestep, lat, s=0), der=0)

        npCentre = scipy.interpolate.interp1d(timestep, pressure, kind='linear')(newtime)
        npEnv = scipy.interpolate.interp1d(timestep, penv, kind='linear')(newtime)
        nrMax = scipy.interpolate.interp1d(timestep, rmax, kind='linear')(newtime)

    bear_, dist_ = maputils.latLon2Azi(nLat, nLon, 1, azimuth=0)
    nthetaFm = numpy.zeros(newtime.size, 'f')
    nthetaFm[:-1] = bear_
    nthetaFm[-1] = bear_[-1]
    dist = numpy.zeros(newtime.size, 'f')
    dist[:-1] = dist_
    dist[-1] = dist_[-1]
    nvFm = dist/delta

    return nid, newtime, newdates, nLon, nLat, nthetaFm, nvFm, npCentre, npEnv, nrMax


# Call the main program:
if __name__ == "__main__":
    main(sys.argv[1:])

"""
Test data for interpTrack:
ID, Age, Lon, Lat, Bearing,Speed, central pressure, Environmental Pressure, rMax, Year, Month, Day, Hour, Minute, Seconds
1,0,132.1,-9.2,360,0,99000,100800,15,1974,12,21,11,30,0
1,6.5,131.5,-9.6,236,12.2,99000,100800,15,1974,12,21,18,0,0
1,12,131.2,-9.9,224.6,8.5,99000,100800,12,1974,12,21,23,30,0
1,18.5,130.9,-10.5,206.2,11.4,98500,100800,12,1974,12,22,6,0,0
1,24,130.6,-10.8,224.5,8.5,98500,100800,12,1974,12,22,11,30,0
1,28.5,130.5,-11.1,198.1,7.8,98500,100800,12,1974,12,22,16,0,0
1,36,130.3,-11.2,243,3.3,98000,100800,12,1974,12,22,23,30,0
1,48,129.9,-11.6,224.5,5.2,97500,100800,12,1974,12,23,11,30,0
1,60,129.9,-11.9,180,2.8,97000,100800,12,1974,12,23,23,30,0
1,64,130.1,-12,117,6.1,96500,100800,10,1974,12,24,3,30,0
1,69.5,130.3,-12.2,135.6,5.7,96000,100800,10,1974,12,24,9,0,0
1,72,130.5,-12.2,90,8.7,95500,100800,10,1974,12,24,11,30,0
1,75.5,130.6,-12.3,135.6,4.4,95000,100800,10,1974,12,24,15,0,0
1,78,130.8,-12.4,117.1,9.8,95000,100800,8,1974,12,24,17,30,0
1,78.5,130.8,-12.4,117.1,0,95000,100800,8,1974,12,24,18,0,0
1,84,131.3,-12.5,101.5,10.1,95000,100800,8,1974,12,24,23,30,0
1,87,131.6,-12.6,108.8,11.5,97000,100800,8,1974,12,25,2,30,0

"""