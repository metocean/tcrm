"""
:mod:`TrackDensity` -- calculate track density
==============================================

.. module:: TrackDensity
   :synopsis: Calculate density of TC tracks over a grid (TCs/degree/year)

.. moduleauthor: Craig Arthur <craig.arthur@ga.gov.au>

"""

import os
import logging

import numpy as np
import numpy.ma as ma

from os.path import join as pjoin
from scipy.stats import scoreatpercentile as percentile
from datetime import datetime

import interpolateTracks

from Utilities.config import ConfigParser
from Utilities.metutils import convert
from Utilities.maputils import bearing2theta
from Utilities.track import Track
from Utilities.nctools import ncSaveGrid
from Utilities.parallel import attemptParallel, disableOnWorkers
from Utilities import pathLocator


from PlotInterface.maps import ArrayMapFigure, saveFigure, FilledContourMapFigure

# Importing :mod:`colours` makes a number of additional colour maps available:
from Utilities import colours

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())



TRACKFILE_COLS = ('CycloneNumber', 'Datetime', 'TimeElapsed', 'Longitude',
                  'Latitude', 'Speed', 'Bearing', 'CentralPressure',
                  'EnvPressure', 'rMax')

TRACKFILE_UNIT = ('', '%Y-%m-%d %H:%M:%S', 'hr', 'degree', 'degree', 'kph', 'degrees',
                  'hPa', 'hPa', 'km')

TRACKFILE_FMTS = ('i', datetime, 'f', 'f', 'f', 'f', 'f', 'f', 'f', 'f')

TRACKFILE_CNVT = {
    0: lambda s: int(float(s.strip() or 0)),
    1: lambda s: datetime.strptime(s.strip(), TRACKFILE_UNIT[1]),
    5: lambda s: convert(float(s.strip() or 0), TRACKFILE_UNIT[5], 'mps'),
    6: lambda s: bearing2theta(float(s.strip() or 0) * np.pi / 180.),
    7: lambda s: convert(float(s.strip() or 0), TRACKFILE_UNIT[7], 'Pa'),
    8: lambda s: convert(float(s.strip() or 0), TRACKFILE_UNIT[8], 'Pa'),
}

def readTrackData(trackfile):
    """
    Read a track .csv file into a numpy.ndarray.

    The track format and converters are specified with the global variables

        TRACKFILE_COLS -- The column names
        TRACKFILE_FMTS -- The entry formats
        TRACKFILE_CNVT -- The column converters

    :param str trackfile: the track data filename.
    """
    try:
        return np.loadtxt(trackfile,
                          comments='%',
                          delimiter=',',
                          dtype={
                          'names': TRACKFILE_COLS,
                          'formats': TRACKFILE_FMTS},
                          converters=TRACKFILE_CNVT)
    except ValueError:
        # return an empty array with the appropriate `dtype` field names
        return np.empty(0, dtype={
                        'names': TRACKFILE_COLS,
                        'formats': TRACKFILE_FMTS})

def readMultipleTrackData(trackfile):
    """
    Reads all the track datas from a .csv file into a list of numpy.ndarrays.
    The tracks are seperated based in their cyclone id. This function calls
    `readTrackData` to read the data from the file.

    :type  trackfile: str
    :param trackfile: the track data filename.
    """
    datas = []
    data = readTrackData(trackfile)
    if len(data) > 0:
        cycloneId = data['CycloneNumber']
        for i in range(1, np.max(cycloneId) + 1):
            datas.append(data[cycloneId == i])
    else:
        datas.append(data)
    return datas

def loadTracks(trackfile):
    """
    Read tracks from a track .csv file and return a list of :class:`Track`
    objects.

    This calls the function `readMultipleTrackData` to parse the track .csv
    file.

    :type  trackfile: str
    :param trackfile: the track data filename.
    """
    tracks = []
    datas = readMultipleTrackData(trackfile)
    n = len(datas)
    for i, data in enumerate(datas):
        track = Track(data)
        track.trackfile = trackfile
        track.trackId = (i, n)
        tracks.append(track)
    return tracks

def loadTracksFromFiles(trackfiles):
    for f in trackfiles:
        tracks = loadTracks(f)
        for track in tracks:
            yield track

def loadTracksFromPath(path):
    files = os.listdir(path)
    trackfiles = [pjoin(path, f) for f in files if f.startswith('tracks')]
    msg = 'Processing %d track files in %s' % (len(trackfiles), path)
    log.info(msg)
    return loadTracksFromFiles(sorted(trackfiles))

class TrackDensity(object):
    def __init__(self, configFile):
        """
        Calculate density of TC positions on a grid

        :param str configFile: path to a TCRM configuration file.
        """

        config = ConfigParser()
        config.read(configFile)
        self.configFile = configFile

        # Define the grid:
        gridLimit = config.geteval('Region', 'gridLimit')
        gridSpace = config.geteval('Region', 'GridSpace')

        self.lon_range = np.arange(gridLimit['xMin'],
                                   gridLimit['xMax'] + 0.1,
                                   gridSpace['x'])
        self.lat_range = np.arange(gridLimit['yMin'],
                                   gridLimit['yMax'] + 0.1,
                                   gridSpace['y'])

        outputPath = config.get('Output', 'Path')
        self.trackPath = pjoin(outputPath, 'tracks')
        self.plotPath = pjoin(outputPath, 'plots', 'stats')
        self.dataPath = pjoin(outputPath, 'process')

        # Determine TCRM input directory
        tcrm_dir = pathLocator.getRootDirectory()
        self.inputPath = pjoin(tcrm_dir, 'input')

        self.synNumYears = config.getint('TrackGenerator',
                                         'yearspersimulation')



    def calculate(self, tracks):
        """
        Calculate a histogram of TC occurrences given a set
        of tracks

        :param tracks: Collection of :class:`Track` objects.
        """

        lon = []
        lat = []

        for t in tracks:
            lon = np.append(lon, t.Longitude)
            lat = np.append(lat, t.Latitude)
        histogram, x, y = np.histogram2d(lon, lat,
                                         [self.lon_range,
                                          self.lat_range],
                                          normed=False)
        return histogram

    def calculateMeans(self):
        self.synHist = ma.masked_values(self.synHist, -9999.)
        self.synHistMean = ma.mean(self.synHist, axis=0)
        self.medSynHist = ma.median(self.synHist, axis=0)
        self.synHistVar = ma.std(self.synHist, axis=0)
        self.synHistUpper = percentile(self.synHist, per=95, axis=0)
        self.synHistLower = percentile(self.synHist, per=5, axis=0)

    @disableOnWorkers
    def historic(self):
        """Load historic data and calculate histogram"""
        config = ConfigParser()
        config.read(self.configFile)
        inputFile = config.get('DataProcess', 'InputFile')
        if len(os.path.dirname(inputFile)) == 0:
            inputFile = pjoin(self.inputPath, inputFile)

        source = config.get('DataProcess', 'Source')

        timestep = config.getfloat('TrackGenerator', 'Timestep')

        interpHistFile = pjoin(self.inputPath, "interp_tracks.csv")
        try:
            tracks = interpolateTracks.parseTracks(self.configFile,
                                                   inputFile,
                                                   source,
                                                   timestep,
                                                   interpHistFile, 'linear')
        except (TypeError, IOError, ValueError):
            log.critical("Cannot load historical track file: {0}".format(inputFile))
            raise
        else:
            startYr = 9999
            endYr = 0
            for t in tracks:
                startYr = min(startYr, min(t.Year))
                endYr = max(endYr, max(t.Year))
            numYears = endYr - startYr
            self.hist = self.calculate(tracks) / (numYears - 1)



    def synthetic(self):
        """Load synthetic data and calculate histogram"""

        #config = ConfigParser()
        #config.read(self.configFile)
        #timestep = config.getfloat('TrackGenerator', 'Timestep')

        filelist = os.listdir(self.trackPath)
        trackfiles = [pjoin(self.trackPath, f) for f in filelist
                      if f.startswith('tracks')]
        self.synHist = -9999. * np.ones((len(trackfiles),
                                         len(self.lon_range) - 1,
                                     len(self.lat_range) - 1))

        work_tag = 0
        result_tag = 1
        
        if (pp.rank() == 0) and (pp.size() > 1):
            w = 0
            n = 0
            for d in range(1, pp.size()):
                pp.send(trackfiles[w], destination=d, tag=work_tag)
                log.debug("Processing track file %d of %d" % (w, len(trackfiles)))
                w += 1

            terminated = 0
            while (terminated < pp.size() - 1):
                results, status = pp.receive(pp.any_source, tag=result_tag, 
                                             return_status=True)
                self.synHist[n, :, :] = results
                n += 1
                
                d = status.source
                if w < len(trackfiles):
                    pp.send(trackfiles[w], destination=d, tag=work_tag)
                    log.debug("Processing track file %d of %d" % (w, len(trackfiles)))
                    w += 1
                else:
                    pp.send(None, destination=d, tag=work_tag)
                    terminated += 1

            self.calculateMeans()

        elif (pp.size() > 1) and (pp.rank() != 0):
            while(True):
                trackfile = pp.receive(source=0, tag=work_tag)
                if trackfile is None:
                    break

                log.debug("Processing %s" % (trackfile))
                tracks = loadTracks(trackfile)
                results = self.calculate(tracks) / self.synNumYears
                pp.send(results, destination=0, tag=result_tag)

        elif (pp.size() == 1) and (pp.rank() == 0):
            for n, trackfile in enumerate(trackfiles):
                tracks = loadTracks(trackfile)
                self.synHist[n, :, :] = self.calculate(tracks) / self.synNumYears

            self.calculateMeans()

    @disableOnWorkers
    def save(self):
        dataFile = pjoin(self.dataPath, 'density.nc')

        # Simple sanity check (should also include the synthetic data):
        if not hasattr(self, 'hist'):
            log.critical("No historical data available!")
            log.critical("Check that data has been processed before trying to save data")
            return

        log.info('Saving track density data to {0}'.format(dataFile))
        dimensions = {
            0: {
                'name': 'lat',
                'values': self.lat_range[:-1],
                'dtype': 'f',
                'atts': {
                    'long_name': 'Latitude',
                    'units': 'degrees_north',
                    'axis': 'Y'
                }
            },
            1: {
                'name': 'lon',
                'values': self.lon_range[:-1],
                'dtype': 'f',
                'atts': {
                    'long_name': 'Longitude',
                    'units':'degrees_east',
                    'axis': 'X'
                }
            }
        }

        # Define variables:
        variables = {
            0: {
                'name': 'hist_density',
                'dims': ('lat', 'lon'),
                'values': np.transpose(self.hist),
                'dtype': 'f',
                'atts': {
                    'long_name': 'Historical track density',
                    'units':'observations per 1-degree grid per year'
                }
            },
            1: {
                'name': 'syn_density',
                'dims': ('lat', 'lon'),
                'values': np.transpose(self.synHistMean),
                'dtype': 'f',
                'atts': {
                    'long_name': 'Track density - synthetic events',
                    'units':'observations per 1-degree grid per year'
                }
            },
            2: {
                'name': 'syn_density_upper',
                'dims': ('lat', 'lon'),
                'values': np.transpose(self.synHistUpper),
                'dtype': 'f',
                'atts': {
                    'long_name': ('Track density - upper percentile '
                                  '- synthetic events'),
                    'units':' observations per 1-degree grid per year',
                    'percentile': '95'
                }
            },
            3: {
                'name': 'syn_density_lower',
                'dims': ('lat', 'lon'),
                'values': np.transpose(self.synHistLower),
                'dtype': 'f',
                'atts': {
                    'long_name': ('Track density - lower percentile '
                                  '- synthetic events'),
                    'units': 'observations per 1-degree grid per year',
                    'percentile': '5'
                }
            }
        }

        ncSaveGrid(dataFile, dimensions, variables)


    @disableOnWorkers
    def plotTrackDensity(self):
        """Plot track density information"""

        datarange = (0, self.hist.max())
        figure = ArrayMapFigure()

        map_kwargs = dict(llcrnrlon=self.lon_range[:-1].min(),
                          llcrnrlat=self.lat_range[:-1].min(),
                          urcrnrlon=self.lon_range[:-1].max(),
                          urcrnrlat=self.lat_range[:-1].max(),
                          projection='merc',
                          resolution='i')
        cbarlab = "TC observations/yr"
        xgrid, ygrid = np.meshgrid(self.lon_range[:-1], self.lat_range[:-1])
        figure.add(self.hist.T, xgrid, ygrid, "Historic", datarange, 
                   cbarlab, map_kwargs)
        figure.add(self.synHistMean.T, xgrid, ygrid, "Synthetic",
                    datarange, cbarlab, map_kwargs)
        figure.plot()
        outputFile = pjoin(self.plotPath, 'track_density.png')
        saveFigure(figure, outputFile)


    @disableOnWorkers
    def plotTrackDensityPercentiles(self):
        """
        Plot upper and lower percentiles of track density derived from
        synthetic event sets

        """

        datarange = (0, self.hist.max())
        figure = ArrayMapFigure()

        map_kwargs = dict(llcrnrlon=self.lon_range[:-1].min(),
                          llcrnrlat=self.lat_range[:-1].min(),
                          urcrnrlon=self.lon_range[:-1].max(),
                          urcrnrlat=self.lat_range[:-1].max(),
                          projection='merc',
                          resolution='i')
        cbarlab = "TC observations/yr"
        xgrid, ygrid = np.meshgrid(self.lon_range[:-1], self.lat_range[:-1])
        figure.add(self.synHistUpper.T, xgrid, ygrid, "Upper percentile", 
                   datarange, cbarlab, map_kwargs)
        figure.add(self.synHistLower.T, xgrid, ygrid, "Lower percentile",
                   datarange, cbarlab, map_kwargs)
        figure.plot()
        outputFile = pjoin(self.plotPath, 'track_density_percentiles.png')
        saveFigure(figure, outputFile)

    @disableOnWorkers
    def plotTrackDensityZScore(self):
        """
        Plot the Z-score of track density

        """
        levels = np.arange(-5, 5.1, 1.)
        figure = FilledContourMapFigure()

        map_kwargs = dict(llcrnrlon=self.lon_range[:-1].min(),
                          llcrnrlat=self.lat_range[:-1].min(),
                          urcrnrlon=self.lon_range[:-1].max(),
                          urcrnrlat=self.lat_range[:-1].max(),
                          projection='merc',
                          resolution='i')
        cbarlabel = ""
        xgrid, ygrid = np.meshgrid(self.lon_range[:-1], self.lat_range[:-1])
        zscore = (self.hist - self.synHistMean) / self.synHistVar

        figure.add(zscore.T, xgrid, ygrid, "Z-score", levels, 
                   cbarlabel, map_kwargs)
        figure.plot()
        outputFile = pjoin(self.plotPath, 'track_density_zscore.png')
        saveFigure(figure, outputFile)

    def run(self):
        """Run the track density evaluation"""
        global pp
        pp = attemptParallel()

        self.historic()

        pp.barrier()

        self.synthetic()
        
        pp.barrier()

        self.plotTrackDensity()
        self.plotTrackDensityPercentiles()
        self.plotTrackDensityZScore()

        self.save()
